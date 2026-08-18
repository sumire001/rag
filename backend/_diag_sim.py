"""诊断：打印各 query 对文档分块的原始 cosine 相似度（绕过 min_score 过滤）。"""
from dotenv import load_dotenv
load_dotenv()

from services.rag import retriever as R
from services.rag.retriever import _embed, _DIM

R.rebuild()
vecs = R._retriever._vecs
chunks = R._retriever._chunks
print(f"分块数={len(chunks)}  向量形状={vecs.shape}")

queries = [
    "zxcvbnm",
    "zxcvbnm qwertyuiop asdfghjkl",
    "数据库索引有什么用",
    "VPN 怎么配置",
]

for q in queries:
    qv = _embed(q)
    sims = vecs @ qv
    top = sorted(((float(s), i) for i, s in enumerate(sims)), reverse=True)[:3]
    print(f"\nQUERY: {q!r}")
    for s, i in top:
        c = chunks[i]
        snippet = c["content"][:30].replace("\n", " ")
        print(f"  score={s:.4f}  gran={c['granularity']:<6} idx={c['idx']:<3} pidx={c['parent_idx']}  {snippet!r}")
    print(f"  -> max_score={top[0][0]:.4f}  (阈值 0.12)")
