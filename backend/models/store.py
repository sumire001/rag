"""SQLite 持久化层：只负责读写，不含业务判断。

每次操作新建连接，避免 Flask 多线程下的 check_same_thread 问题。
"""

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from config import Config

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL DEFAULT '新对话',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    summary       TEXT NOT NULL DEFAULT '',
    summary_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS embeddings (
    message_id      INTEGER PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    vector          BLOB NOT NULL,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS feishu_sessions (
    channel          TEXT NOT NULL,
    peer_id          TEXT NOT NULL,
    conversation_id  TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (channel, peer_id)
);

CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    file_type   TEXT NOT NULL,
    size        INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'done',
    error       TEXT NOT NULL DEFAULT '',
    text        TEXT NOT NULL DEFAULT '',
    meta_json   TEXT NOT NULL DEFAULT '',
    chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id      TEXT NOT NULL,
    idx         INTEGER NOT NULL,        -- 同一 doc 内单调递增
    content     TEXT NOT NULL,
    granularity TEXT NOT NULL DEFAULT 'parent',  -- 'parent' | 'child'
    parent_idx  INTEGER,                  -- child 指向其所属 parent
    created_at  TEXT NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);
CREATE INDEX IF NOT EXISTS idx_emb_conv ON embeddings(conversation_id);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks(doc_id, idx);
"""


def _migrate_chunks_columns(conn) -> None:
    """旧库兼容：document_chunks 表可能缺 granularity / parent_idx 列，补齐。"""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(document_chunks)").fetchall()}
    if "granularity" not in cols:
        conn.execute(
            "ALTER TABLE document_chunks ADD COLUMN granularity TEXT NOT NULL DEFAULT 'parent'"
        )
    if "parent_idx" not in cols:
        conn.execute("ALTER TABLE document_chunks ADD COLUMN parent_idx INTEGER")



def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def get_conn():
    os.makedirs(os.path.dirname(Config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(Config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # 网页端与飞书端可能作为两个进程同时读写，开 WAL 降低写锁冲突
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
        # 存量库迁移：新增列/表在老库上不会自动出现，这里做幂等补齐
        _migrate(conn)
        _migrate_chunks_columns(conn)


def _migrate(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(conversations)")}
    if "summary" not in cols:
        conn.execute("ALTER TABLE conversations ADD COLUMN summary TEXT NOT NULL DEFAULT ''")
    if "summary_count" not in cols:
        conn.execute("ALTER TABLE conversations ADD COLUMN summary_count INTEGER NOT NULL DEFAULT 0")
    # embeddings 表若不存在则创建（executescript 已含 IF NOT EXISTS，这里仅兜底）
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            message_id      INTEGER PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role            TEXT NOT NULL,
            content         TEXT NOT NULL,
            vector          BLOB NOT NULL,
            created_at      TEXT NOT NULL,
            FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feishu_sessions (
            channel          TEXT NOT NULL,
            peer_id          TEXT NOT NULL,
            conversation_id  TEXT NOT NULL,
            created_at       TEXT NOT NULL,
            PRIMARY KEY (channel, peer_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id          TEXT PRIMARY KEY,
            filename    TEXT NOT NULL,
            file_type   TEXT NOT NULL,
            size        INTEGER NOT NULL DEFAULT 0,
            status      TEXT NOT NULL DEFAULT 'done',
            error       TEXT NOT NULL DEFAULT '',
            text        TEXT NOT NULL DEFAULT '',
            meta_json   TEXT NOT NULL DEFAULT '',
            chunk_count INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS document_chunks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id      TEXT NOT NULL,
            idx         INTEGER NOT NULL,        -- 同一 doc 内单调递增；parent 段连续编号，child 跟随其所属 parent 编号
            content     TEXT NOT NULL,
            granularity TEXT NOT NULL DEFAULT 'parent',  -- 'parent' | 'child'
            parent_idx  INTEGER,                  -- 仅 child 有值，指向其所属 parent；parent 自身为 NULL
            created_at  TEXT NOT NULL,
            FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
        )
        """
    )


# ---------------- conversations ----------------

def create_conversation(title: str = "新对话") -> dict:
    cid = uuid.uuid4().hex
    ts = now_iso()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (cid, title, ts, ts),
        )
    return {"id": cid, "title": title, "created_at": ts, "updated_at": ts}


def list_conversations() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
            FROM conversations c
            ORDER BY c.updated_at DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def get_conversation(cid: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM conversations WHERE id = ?", (cid,)).fetchone()
    return dict(row) if row else None


def rename_conversation(cid: str, title: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, now_iso(), cid),
        )
    return cur.rowcount > 0


def touch_conversation(cid: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now_iso(), cid))


def delete_conversation(cid: str) -> bool:
    with get_conn() as conn:
        conn.execute("DELETE FROM embeddings WHERE conversation_id = ?", (cid,))
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (cid,))
        # 同步清掉飞书会话映射，防止残留孤儿映射导致外键失败
        conn.execute("DELETE FROM feishu_sessions WHERE conversation_id = ?", (cid,))
        cur = conn.execute("DELETE FROM conversations WHERE id = ?", (cid,))
    return cur.rowcount > 0


def update_conversation_summary(cid: str, summary: str, count: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE conversations SET summary = ?, summary_count = ? WHERE id = ?",
            (summary, count, cid),
        )


# ---------------- messages ----------------

def add_message(cid: str, role: str, content: str) -> dict:
    ts = now_iso()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (cid, role, content, ts),
        )
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (ts, cid))
    return {
        "id": cur.lastrowid,
        "conversation_id": cid,
        "role": role,
        "content": content,
        "created_at": ts,
    }


def list_messages(cid: str) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (cid,),
        ).fetchall()
    return [dict(r) for r in rows]


def recent_messages(cid: str, limit: int) -> list:
    """取最近 limit 条，按时间正序返回，用于拼模型上下文。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
            (cid, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def clear_messages(cid: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM embeddings WHERE conversation_id = ?", (cid,))
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (cid,))
        conn.execute("UPDATE conversations SET summary = '', summary_count = 0, updated_at = ? WHERE id = ?", (now_iso(), cid))


# ---------------- embeddings（层2 向量召回） ----------------

def add_embedding(message_id: int, conversation_id: str, role: str, content: str, vector: bytes) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO embeddings
                (message_id, conversation_id, role, content, vector, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message_id, conversation_id, role, content, vector, now_iso()),
        )


def delete_embeddings_by_conversation(cid: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM embeddings WHERE conversation_id = ?", (cid,))


def list_embeddings(exclude_conv_id: str = None) -> list:
    """取出全部向量用于本地余弦计算。exclude_conv_id 用于跨会话召回时排除当前会话。"""
    with get_conn() as conn:
        if exclude_conv_id:
            rows = conn.execute(
                "SELECT message_id, conversation_id, role, content, vector "
                "FROM embeddings WHERE conversation_id != ? ORDER BY message_id ASC",
                (exclude_conv_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT message_id, conversation_id, role, content, vector "
                "FROM embeddings ORDER BY message_id ASC"
            ).fetchall()
    return [dict(r) for r in rows]


# ---------------- feishu_sessions（飞书群/私聊 → 本地会话映射） ----------------

def get_feishu_session(channel: str, peer_id: str):
    """按 渠道+对端ID 取已绑定的本地会话 id；无则返回 None。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT conversation_id FROM feishu_sessions WHERE channel=? AND peer_id=?",
            (channel, peer_id),
        ).fetchone()
    return dict(row)["conversation_id"] if row else None


def create_feishu_session(channel: str, peer_id: str, conversation_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO feishu_sessions (channel, peer_id, conversation_id, created_at) "
            "VALUES (?, ?, ?, ?)",
            (channel, peer_id, conversation_id, now_iso()),
        )


# ---------------- documents（文档解析与切片） ----------------

def create_document(doc_id: str, filename: str, file_type: str, size: int,
                    status: str, error: str, text: str, meta_json: str,
                    parents: list = None, children: list = None,
                    chunks: list = None) -> dict:
    """写入文档元信息与切片（同一连接内完成，保证原子性）。

    两种用法二选一：
      A) 两层切块：parents=list[str], children=list[(parent_idx, content)]
      B) 单层兼容：chunks=list[str]（旧用法，视为全部为 parent 粒度）
    """
    parents = list(parents or [])
    children = list(children or [])
    use_two_level = bool(parents) or bool(children)

    if not use_two_level:
        chunks = list(chunks or [])
        total = len(chunks)
    else:
        total = len(parents) + len(children)

    ts = now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO documents
                (id, filename, file_type, size, status, error, text, meta_json, chunk_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (doc_id, filename, file_type, size, status, error, text, meta_json,
             total, ts),
        )
        if use_two_level:
            rows = []
            for i, p in enumerate(parents):
                rows.append((doc_id, i, p, "parent", None, ts))
            for c_idx, (p_idx, content) in enumerate(children):
                row_idx = len(parents) + c_idx
                rows.append((doc_id, row_idx, content, "child", p_idx, ts))
            if rows:
                conn.executemany(
                    "INSERT INTO document_chunks "
                    "(doc_id, idx, content, granularity, parent_idx, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    rows,
                )
        elif chunks:
            conn.executemany(
                "INSERT INTO document_chunks "
                "(doc_id, idx, content, granularity, parent_idx, created_at) "
                "VALUES (?, ?, ?, 'parent', NULL, ?)",
                [(doc_id, i, c, ts) for i, c in enumerate(chunks)],
            )
    return {
        "id": doc_id, "filename": filename, "file_type": file_type, "size": size,
        "status": status, "error": error, "chunk_count": total, "created_at": ts,
    }


def get_document(doc_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return dict(row) if row else None


def list_documents() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, filename, file_type, size, status, error, chunk_count, created_at "
            "FROM documents ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_document_chunks(doc_id: str) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT idx, content FROM document_chunks WHERE doc_id = ? ORDER BY idx ASC",
            (doc_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def all_document_chunks() -> list:
    """返回全库所有分块（含两层粒度），附带所属文档的文件名，供 RAG 检索建索引用。

    返回行：(doc_id, idx, content, filename, granularity, parent_idx)
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.doc_id, c.idx, c.content, d.filename,
                   c.granularity, c.parent_idx
            FROM document_chunks c
            JOIN documents d ON d.id = c.doc_id
            ORDER BY c.doc_id, c.idx ASC
            """
        ).fetchall()
    return [tuple(r) for r in rows]


def all_child_chunks_for_index() -> list:
    """返回所有 child 粒度分块（含所属 parent_idx + 文件名），专供 RAG 内存索引用。

    返回行：(doc_id, idx, content, filename, parent_idx)
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.doc_id, c.idx, c.content, d.filename, c.parent_idx
            FROM document_chunks c
            JOIN documents d ON d.id = c.doc_id
            WHERE c.granularity = 'child'
            ORDER BY c.doc_id, c.idx ASC
            """
        ).fetchall()
    return [tuple(r) for r in rows]


def get_parent_chunks_for_items(items: list) -> dict:
    """按 [(doc_id, parent_idx), ...] 批量取对应的 parent 文本。

    items: [{"doc_id": str, "parent_idx": int}, ...]
    返回 {(doc_id, parent_idx): content}。
    """
    if not items:
        return {}
    # 用 OR 拼一个统一查询
    clauses = []
    params = []
    for it in items:
        clauses.append("(c.doc_id = ? AND c.idx = ? AND c.granularity = 'parent')")
        params.extend([it["doc_id"], it["parent_idx"]])
    sql = (
        "SELECT c.doc_id, c.idx, c.content "
        "FROM document_chunks c WHERE " + " OR ".join(clauses)
    )
    out = {}
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    for r in rows:
        out[(r[0], r[1])] = r[2]
    return out


def delete_document(doc_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    return cur.rowcount > 0
