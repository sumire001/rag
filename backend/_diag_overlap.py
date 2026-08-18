"""诊断：每个 query 对 top 分块的「命中 token 数（共享桶数）」+ cosine。"""
from dotenv import load_dotenv
load_dotenv()

import numpy as np
from services.rag import retriever as R
from services.rag.retriever import _embed, _DIM, _tokenize

R.rebuild()
vecs = R._retriever._vecs
chunks = R._retriever._chunks

queries = [
    "zxcvbnm",
    "zxcvbnm qwertyuiop asdfghjkl",
    "数据库索引有什么用",
    "VPN 怎么配置",
    "怎么重置路由器密码",
]

for q in queries:
    qv = _embed(q)
    q_toks = set(_tokenize(q))
    # 该 query 实际命中的桶（非零维度）
    q_nonzero = set(np.where(qv != 0)[0].tolist())
    sims = vecs @ qv
    order = sorted(range(len(sims)), key=lambda i: -sims[i])[:3]
    print(f"\nQUERY: {q!r}  (query tokens={len(q_toks)})")
    for i in order:
        cvec = vecs[i]
        c_nonzero = set(np.where(cvec != 0)[0].tolist())
        shared = q_nonzero & c_nonzero
        snippet = chunks[i]["content"][:24].replace("\n", " ")
        print(f"  cos={sims[i]:.4f}  shared_buckets={len(shared):<3} gran={chunks[i]['granularity']:<6} idx={chunks[i]['idx']:<3} {snippet!r}")
