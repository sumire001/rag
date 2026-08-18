"""飞书长连接运行器：独立进程启动，不依赖网页端。

启动方式（在 backend 目录下）：
    python -m services.feishu.longpoll

前置：.env 中配置 FEISHU_APP_ID / FEISHU_APP_SECRET（以及可选 ENCRYPT_KEY / VERIFICATION_TOKEN）。
飞书开放平台需开启「机器人」能力并申请 im 相关权限；长连接模式无需配置事件回调地址。
"""

import logging

from dotenv import load_dotenv

load_dotenv()  # 必须在 import config 之前加载 .env，否则独立进程读不到环境变量

from config import Config
from models import store
from services import runtime_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("feishu")


def main() -> None:
    if not Config.FEISHU_APP_ID or not Config.FEISHU_APP_SECRET:
        print("[飞书] 未配置 FEISHU_APP_ID / FEISHU_APP_SECRET，无法启动。请在 .env 中填写后重试。")
        return

    # 准备运行环境：建表 + 加载 LLM 运行时配置（api_key 等）
    store.init_db()
    runtime_config.load()

    # 构建 RAG 文档检索索引（加载 document_chunks 到内存）
    from services.rag import retriever as rag_retriever

    rag_retriever.rebuild()

    from services.feishu.dispatcher import build_dispatcher

    dispatcher = build_dispatcher()

    import lark_oapi as lark
    import lark_oapi.ws as lark_ws

    client = lark_ws.Client(
        app_id=Config.FEISHU_APP_ID,
        app_secret=Config.FEISHU_APP_SECRET,
        event_handler=dispatcher,
        log_level=lark.LogLevel.DEBUG,
    )
    logger.info("飞书长连接已启动，等待事件（Ctrl+C 退出）...")
    client.start()  # 阻塞运行，直到进程被终止


if __name__ == "__main__":
    main()
