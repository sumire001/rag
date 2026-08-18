"""全局配置：所有可调项集中在这里，通过环境变量覆盖。"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _bool(key: str, default: str = "0") -> bool:
    return os.getenv(key, default).strip().lower() in ("1", "true", "yes", "on")


class Config:
    # ---- 服务 ----
    HOST = os.getenv("APP_HOST", "127.0.0.1")
    PORT = int(os.getenv("APP_PORT", "5000"))
    DEBUG = _bool("APP_DEBUG", "0")

    # ---- 跨域：前端独立部署，必须放行 ----
    # 多个来源用逗号分隔，"*" 表示全部放行（仅建议本地开发使用）
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

    # ---- 存储 ----
    DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "chat.db"))

    # ---- 模型 ----
    # echo   = 本地回声模拟，无需任何 key，开箱即用
    # openai = 任意 OpenAI 兼容接口（官方 / DeepSeek / 通义 / 本地 ollama 等）
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "echo")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
    LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))

    # ---- 对话 ----
    SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "你是一个简洁、友好的中文 AI 助手。")
    HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "20"))  # 带入模型的最近消息条数
    MAX_INPUT_LEN = int(os.getenv("MAX_INPUT_LEN", "4000"))  # 单条用户输入上限

    # ---- 记忆（层1 会话内摘要 + 层2 跨会话向量召回）----
    MEMORY_ENABLED = _bool("MEMORY_ENABLED", "1")          # 总开关
    # embedding 来源：local = 本地 sentence-transformers(bge-small-zh，需联网下载模型)
    #                 openai = 任意 OpenAI 兼容 /embeddings（需 key）
    #                 lexical = 词袋+特征哈希，纯本地零模型、断网可用（只认字面重合）
    MEMORY_EMBEDDING_PROVIDER = os.getenv("MEMORY_EMBEDDING_PROVIDER", "local")
    MEMORY_EMBEDDING_MODEL = os.getenv("MEMORY_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    # local 模式模型加载源：留空 = 自动从 ModelScope(魔搭)/HuggingFace 下载到 backend/data/models；
    # 指定 = 直接使用该本地目录中的模型（如自己用魔搭下载解压后的目录）
    MEMORY_EMBEDDING_MODEL_DIR = os.getenv("MEMORY_EMBEDDING_MODEL_DIR", "")
    MEMORY_EMBEDDING_BASE_URL = os.getenv("MEMORY_EMBEDDING_BASE_URL", "https://api.openai.com/v1")
    MEMORY_EMBEDDING_API_KEY = os.getenv("MEMORY_EMBEDDING_API_KEY", "")
    MEMORY_TOP_K = int(os.getenv("MEMORY_TOP_K", "5"))     # 召回条数
    MEMORY_CROSS_CONV = _bool("MEMORY_CROSS_CONV", "1")    # 是否跨会话召回（否则仅在当前会话内 RAG）
    MEMORY_MIN_SCORE = float(os.getenv("MEMORY_MIN_SCORE", "0.0"))  # 召回相似度下限（0 表示不过滤）

    # ---- 飞书机器人（长连接模式）----
    FEISHU_ENABLED = _bool("FEISHU_ENABLED", "0")                      # 是否启用飞书通道
    FEISHU_EVENT_MODE = os.getenv("FEISHU_EVENT_MODE", "long_poll")   # long_poll | callback
    FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
    FEISHU_ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY", "")                  # 事件体 AES 加密密钥（建议配置）
    FEISHU_VERIFICATION_TOKEN = os.getenv("FEISHU_VERIFICATION_TOKEN", "")    # 旧版校验令牌（可选）
    FEISHU_REPLY_CHUNK = int(os.getenv("FEISHU_REPLY_CHUNK", "2000"))         # 长回复分片字数上限

    # ---- 文档处理（PDF / Word / Excel·CSV / TXT·MD 解析与切片）----
    DOC_UPLOAD_DIR = os.getenv("DOC_UPLOAD_DIR", str(BASE_DIR / "data" / "uploads"))
    DOC_CHUNK_SIZE = int(os.getenv("DOC_CHUNK_SIZE", "800"))      # 单层兼容模式下的目标字数
    DOC_CHUNK_OVERLAP = int(os.getenv("DOC_CHUNK_OVERLAP", "100"))  # 单层模式下的重叠字数
    # 父子切块（默认开启）：检索走 child，给模型读走 parent
    DOC_USE_TWO_LEVEL = _bool("DOC_USE_TWO_LEVEL", "1")
    DOC_PARENT_CHUNK_SIZE = int(os.getenv("DOC_PARENT_CHUNK_SIZE", "1800"))   # 父块目标字数（送 LLM 看的上下文）
    DOC_PARENT_CHUNK_OVERLAP = int(os.getenv("DOC_PARENT_CHUNK_OVERLAP", "200"))
    DOC_CHILD_CHUNK_SIZE = int(os.getenv("DOC_CHILD_CHUNK_SIZE", "400"))     # 子块目标字数（检索粒度）
    DOC_CHILD_CHUNK_OVERLAP = int(os.getenv("DOC_CHILD_CHUNK_OVERLAP", "60"))
    DOC_MAX_SIZE_MB = float(os.getenv("DOC_MAX_SIZE_MB", "20"))   # 单文件大小上限(MB)
    # 允许的后缀（小写），逗号分隔
    DOC_ALLOWED_EXT = os.getenv(
        "DOC_ALLOWED_EXT", ".pdf,.docx,.xlsx,.xls,.csv,.txt,.md"
    ).lower()

    # ---- RAG 回复模式（飞书问答用）----
    # strict    = 严格只基于《通用IT知识》回答，资料里没有就明确拒绝
    # rag_first = 优先用资料回答；资料没有时回落到模型自身通用知识（标注来源）
    _raw_rag_mode = os.getenv("RAG_MODE", "rag_first").strip().lower()
    RAG_MODE = _raw_rag_mode if _raw_rag_mode in ("strict", "rag_first") else "rag_first"

