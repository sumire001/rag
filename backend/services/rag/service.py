"""RAG 回答服务：检索相关分块 -> 回溯到父块取上下文 -> 按「回复模式」生成答案。

回复模式（全局，可用飞书命令切换，默认见 config.RAG_MODE）：
- strict（严格）   ：只依据《通用IT知识》回答；资料里没有就明确拒绝，绝不编造。
- rag_first（优先）：优先用资料回答；资料没有时回落到模型自身的通用知识，并标注来源。

引文格式：
- 命中资料：末尾统一 `📚 来源：通用IT知识（#分块1, #分块2）`，正文不夹括号引用；
- 回落通用：末尾 `💡 来源：模型预训练的通用知识`；
- 严格无命中：给出说明，不附来源标签。

echo 离线模式 / 模型调用失败时降级为「命中的 parent 全文 + 同一份末尾引用」，
保证端到端可用；回落通用知识在无真实模型时也会给出明确说明。
"""
import logging

from config import Config
from models import store
from services import llm_provider
from services import runtime_config
from services.rag import retriever

logger = logging.getLogger("rag.service")

# 通用知识库的统一来源名（用户要求：通用知识提醒来自通用知识）
SOURCE_LABEL = "通用IT知识"

# 资料回答的系统提示
DOC_SYSTEM_PROMPT = (
    "你是严谨的企业 IT 知识助手。回答问题要简洁直接，只依据给你的资料回答。"
    "如果资料中没有提到，明确说「不知道」，不要编造。"
    "用你自己的话归纳即可，不要把资料整段抄进回答。"
    "不要在正文里出现任何「（来源…）」之类的括号引用——末尾会自动加上来源标签。"
)

# 回落「模型通用知识」时的系统提示（不依赖任何资料）
GENERAL_SYSTEM_PROMPT = (
    "你是一个企业 IT 知识助手。请使用你自己的通用知识，简洁、准确地回答用户的问题。"
    "不要编造不确定的事实；如果确实不知道，就如实说明。"
)


# ----------------------------------------------------------------------------
# 模式读取 / 切换（持久化到 runtime_config，重启后仍生效）
# ----------------------------------------------------------------------------
def get_rag_mode() -> str:
    m = str(runtime_config.get("rag_mode") or "rag_first").strip().lower()
    return m if m in ("strict", "rag_first") else "rag_first"


def set_rag_mode(mode: str) -> str:
    mode = (mode or "").strip().lower()
    if mode not in ("strict", "rag_first"):
        raise ValueError("回复模式只能是 strict 或 rag_first")
    runtime_config.update({"rag_mode": mode})
    return mode


def mode_description(mode: str) -> str:
    return {
        "strict": "严格（仅基于《通用IT知识》回答，资料没有就拒绝）",
        "rag_first": "优先（先用资料回答，资料没有时用模型通用知识）",
    }.get(mode, mode)


def rebuild_index() -> None:
    retriever.rebuild()


# ----------------------------------------------------------------------------
# 内部工具
# ----------------------------------------------------------------------------
def _dedup_parents(hits: list):
    """把 child 命中按 (doc_id, parent_idx) 去重，每个 parent 取其命中的【最高分】。

    返回 parents 按 best_score 降序，再按 doc_id/parent_idx 升序稳定排序。
    returns:
      parents    : list[(ref_idx, doc_id, parent_idx, filename, parent_content, best_score)]
      citations  : list[{"ref_idx", "doc_id", "parent_idx", "filename"}]
    """
    score_map = {}   # (doc_id, parent_idx) -> best_score

    for h in hits:
        if h.get("granularity") == "parent":
            pidx = h["idx"]
        else:
            pidx = h.get("parent_idx")
        if pidx is None:
            continue
        key = (h["doc_id"], pidx)
        s = float(h.get("score", 0.0))
        prev = score_map.get(key)
        if prev is None or s > prev:
            score_map[key] = s

    if not score_map:
        return [], []

    pending = [{"doc_id": k[0], "parent_idx": k[1]} for k in score_map.keys()]
    parent_map = store.get_parent_chunks_for_items(pending)

    # 按 best_score 降序、稳定（同分则按 doc_id, parent_idx）排序
    sorted_keys = sorted(score_map.keys(), key=lambda k: (-score_map[k], k[0], k[1]))
    parents = []
    citations = []
    for ref_idx, key in enumerate(sorted_keys, 1):
        doc_id, pidx = key
        filename = next((h["filename"] for h in hits
                          if h["doc_id"] == doc_id and (
                              (h.get("granularity") == "parent" and h["idx"] == pidx)
                              or (h.get("granularity") == "child" and h.get("parent_idx") == pidx)
                          )), "")
        parents.append((
            ref_idx, doc_id, pidx, filename,
            parent_map.get(key, ""),
            score_map[key],
        ))
        citations.append({
            "ref_idx": ref_idx, "doc_id": doc_id, "parent_idx": pidx, "filename": filename,
        })
    return parents, citations


def _format_context(parents: list) -> str:
    parts = []
    for ref_idx, _doc_id, _pidx, _fname, content, _score in parents:
        parts.append(f"[{ref_idx}] {content}")
    return "\n\n".join(parts)


def _build_history(conversation_id: str = None, limit: int = None) -> str:
    """取同一会话的历史消息（不含当前这一条待回答的用户消息），拼成可读上下文。

    用于把多轮对话历史喂给模型，让 RAG 问答能理解代词与前文指代
    （例如用户先问「VPN 怎么配」，再问「它支持哪些系统」时，模型知道「它」指什么）。
    """
    if not conversation_id:
        return ""
    if limit is None:
        limit = getattr(Config, "HISTORY_LIMIT", 12)
    msgs = store.recent_messages(conversation_id, limit)
    # 去掉最后一条（即本次正在回答的用户消息），只保留此前的轮次
    if msgs and msgs[-1]["role"] == "user":
        msgs = msgs[:-1]
    if not msgs:
        return ""
    lines = []
    for m in msgs:
        who = "用户" if m["role"] == "user" else "助手"
        lines.append(f"{who}：{m['content']}")
    return "\n".join(lines)


def _citations_label(citations: list) -> str:
    """末尾的统一引用：`（#分块1, #分块2）`。按 ref_idx 升序。"""
    if not citations:
        return ""
    nums = sorted({c["ref_idx"] for c in citations})
    return "（#分块" + ", #分块".join(str(n) for n in nums) + "）"


def _fallback_body(parents: list) -> str:
    """echo 模式：直接把 parent 原文拼接（每段一个 ref 号，方便对照末尾引用）。"""
    parts = ["以下是与您问题相关的资料片段："]
    for ref_idx, _doc_id, _pidx, _fname, content, _score in parents:
        parts.append(f"[{ref_idx}] {content}")
    return "\n\n".join(parts)


# ----------------------------------------------------------------------------
# 两种回答构造
# ----------------------------------------------------------------------------
def _answer_from_rag(question: str, hits: list, top_k: int, max_parents: int, conversation_id: str = None) -> dict:
    """命中资料：用资料内容回答，末尾附统一来源标签（📚）。"""
    parents, citations = _dedup_parents(hits)
    parents = parents[:max_parents]
    citations = citations[:max_parents]
    ctx = _format_context(parents)
    provider = llm_provider.get_provider()
    is_real = not isinstance(provider, llm_provider.EchoProvider)
    history = _build_history(conversation_id)

    if is_real:
        user_parts = [f"参考资料：\n{ctx}"]
        if history:
            user_parts.append(
                "以下是你此前与用户的对话，请结合上下文理解当前问题"
                "（特别留意代词与前文指代）：\n" + history
            )
        user_parts.append(f"问题：{question}\n\n请直接给出回答：")
        user = "\n\n".join(user_parts)
        try:
            body = provider.complete([
                {"role": "system", "content": DOC_SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ])
        except Exception:
            logger.exception("RAG 调用模型失败，降级为 parent 全文")
            body = _fallback_body(parents)
    else:
        body = _fallback_body(parents)

    label = _citations_label(citations)
    src = f"📚 来源：{SOURCE_LABEL}{label}" if label else f"📚 来源：{SOURCE_LABEL}"
    answer = f"{body.strip()}\n\n{src}"
    return {
        "answer": answer,
        "citations": citations,
        "source": SOURCE_LABEL,
        "source_type": "document",
        "found": True,
        "mode": get_rag_mode(),
    }


def _answer_from_general(question: str, conversation_id: str = None) -> dict:
    """资料未命中 + 优先模式：回落到模型自身通用知识，标注💡 来源。"""
    provider = llm_provider.get_provider()
    is_real = not isinstance(provider, llm_provider.EchoProvider)

    if not is_real:
        # 没有真实模型，无法产生通用知识回答
        answer = (
            "未在「{}」中找到相关内容，且当前处于 Echo 离线回声模式，未接入真实大模型，"
            "无法调用模型通用知识补充回答。\n"
            "请在「模型设置」中将「模型类型」切换为 OpenAI 兼容并填写有效 API Key 后重试。"
        ).format(SOURCE_LABEL)
        return {
            "answer": answer,
            "citations": [],
            "source": SOURCE_LABEL,
            "source_type": "none",
            "found": False,
            "mode": "rag_first",
        }

    history = _build_history(conversation_id)
    if history:
        question_full = "此前对话：\n" + history + "\n\n当前问题：" + question
    else:
        question_full = question

    try:
        body = provider.complete([
            {"role": "system", "content": GENERAL_SYSTEM_PROMPT},
            {"role": "user", "content": question_full},
        ])
    except Exception:
        logger.exception("RAG 通用知识回落失败")
        body = "调用模型失败，暂时无法回答。"

    answer = f"{body.strip()}\n\n💡 来源：模型预训练的通用知识"
    return {
        "answer": answer,
        "citations": [],
        "source": "模型预训练的通用知识",
        "source_type": "general",
        "found": False,
        "mode": "rag_first",
    }


# ----------------------------------------------------------------------------
# 对外入口
# ----------------------------------------------------------------------------
def rag_answer(question: str, top_k: int = 8, max_parents: int = 2, mode: str = None, conversation_id: str = None) -> dict:
    """返回 {answer, citations, source, source_type, found, mode}。

    - 命中资料：无论哪种模式都基于资料回答（source_type=document）。
    - 未命中 + strict：明确拒绝（source_type=none）。
    - 未命中 + rag_first：回落模型通用知识（source_type=general）。
    - conversation_id：传入后，问答会带上该会话的历史轮次（多轮上下文）。
    """
    effective_mode = mode or get_rag_mode()
    hits = retriever.search(question, top_k=top_k)

    if hits:
        return _answer_from_rag(question, hits, top_k, max_parents, conversation_id)

    # ---- 资料未命中 ----
    if effective_mode == "strict":
        if runtime_config.get("provider") == "echo":
            answer = (
                f"未在「{SOURCE_LABEL}」中找到相关内容。\n\n"
                f"当前为【严格】模式，且处于 Echo 离线回声模式（未接入真实大模型），"
                f"无法调用模型通用知识补充回答。\n"
                f"如需测试真实模型，请在「模型设置」中将「模型类型」切换为 OpenAI 兼容并填写有效 API Key。"
            )
        else:
            answer = (
                f"未在「{SOURCE_LABEL}」中找到与您问题相关的内容。"
                f"当前为【严格】模式，只能依据资料回答，无法回答该问题。"
            )
        return {
            "answer": answer,
            "citations": [],
            "source": SOURCE_LABEL,
            "source_type": "none",
            "found": False,
            "mode": "strict",
        }

    # rag_first：回落模型通用知识
    return _answer_from_general(question, conversation_id)
