"""把文档文本切成适合检索/阅读的片段。

策略：
1. 按空行拆段落，段落内换行归一为空格；
2. 贪心地把段落塞进当前片段，超过 chunk_size 就收尾开新片段；
3. 片段之间保留 overlap 个字符的尾部重叠，避免语义被切断；
4. 单段落超长则按句子再按字符硬切。
"""
import re

_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;\n])")


def _split_long(text: str, chunk_size: int) -> list:
    """超长单段：先按句切，再不够则按字符硬切。"""
    pieces = []
    for sent in _SENT_SPLIT.split(text):
        sent = sent.strip()
        if not sent:
            continue
        if len(sent) <= chunk_size:
            pieces.append(sent)
        else:
            for i in range(0, len(sent), chunk_size):
                pieces.append(sent[i : i + chunk_size])
    return pieces


def _to_paras(text: str, limit: int) -> list:
    """段落化；超长段落按句切。"""
    paras = []
    for p in re.split(r"\n\s*\n", text):
        p = p.strip()
        if not p:
            continue
        p = re.sub(r"[ \t]+", " ", p.replace("\r", ""))
        if len(p) > limit * 2:
            paras.extend(_split_long(p, limit))
        else:
            paras.append(p)
    return paras


def _greedy(paras: list, chunk_size: int, overlap: int) -> list:
    """贪心段落塞入 + 相邻 overlap。"""
    chunks = []
    buf = ""
    for p in paras:
        if buf and len(buf) + 1 + len(p) > chunk_size:
            chunks.append(buf)
            tail = buf[-overlap:] if overlap else ""
            buf = (tail + "\n" + p) if tail else p
        else:
            buf = (buf + "\n" + p) if buf else p
    if buf:
        chunks.append(buf)
    return [c.strip() for c in chunks if c.strip()]


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list:
    if not text or not text.strip():
        return []
    chunk_size = max(50, int(chunk_size))
    overlap = max(0, min(int(overlap), chunk_size - 10))
    paras = _to_paras(text, chunk_size)
    return _greedy(paras, chunk_size, overlap)


def chunk_text_two_level(
    text: str,
    parent_size: int = 1800,
    parent_overlap: int = 200,
    child_size: int = 400,
    child_overlap: int = 60,
):
    """父子两级切块。

    返回：
      parents : list[str]                       -- 给 LLM 看的完整上下文
      children: list[(parent_idx, content)]     -- 给检索用的细粒度分块

    策略：
      1) 先把全文切成若干 parent（粗粒度，含 overlap 跨段上下文）；
      2) 每个 parent 内部再切出 child（细粒度），并记录 child 所属 parent 的索引；
      3) child 不在前一 parent 的尾巴 overlap 区域里重复切，避免无意义的重复。
    """
    if not text or not text.strip():
        return [], []

    parent_size = max(100, int(parent_size))
    parent_overlap = max(0, min(int(parent_overlap), parent_size - 20))
    child_size = max(50, int(child_size))
    child_overlap = max(0, min(int(child_overlap), child_size - 10))

    paras = _to_paras(text, parent_size)
    parents_raw = _greedy(paras, parent_size, parent_overlap)
    if not parents_raw:
        return [], []

    parents = []
    children = []
    for pi, ptext in enumerate(parents_raw):
        # 计算父块的「核心区」（去掉尾部 overlap 与下一个 parent 重叠的部分），
        # child 只在核心区内切，避免和下一个 parent 重复。
        core_text = ptext
        if pi < len(parents_raw) - 1 and parent_overlap:
            tail = ptext[-parent_overlap:]
            idx = ptext.rfind(tail)
            # 仅当确实找到这一尾巴才截，否则整段都算核心
            if idx > len(ptext) // 2:
                core_text = ptext[:idx].rstrip()

        # 父块自身无论如何都要保留（含 overlap 跨段上下文，给模型用）
        parents.append(ptext)

        c_paras = _to_paras(core_text, child_size)
        # 保留 child 的句首位置以便拼接时仍能体现父级"从哪里截"
        for cc in _greedy(c_paras, child_size, child_overlap):
            children.append((pi, cc))

    return parents, children
