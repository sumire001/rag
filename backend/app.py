"""应用入口：python app.py 即可启动。"""

from dotenv import load_dotenv

load_dotenv()  # 必须在 import config 之前，保证 .env 生效

from flask import Flask  # noqa: E402
from flask_cors import CORS  # noqa: E402

from api.chat import bp as api_bp  # noqa: E402
from api.config import bp as config_bp  # noqa: E402
from api.documents import bp as documents_bp  # noqa: E402
from config import Config  # noqa: E402
from models import store  # noqa: E402
from services import runtime_config  # noqa: E402
from utils.response import fail  # noqa: E402


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    app.json.ensure_ascii = False

    origins = [o.strip() for o in Config.CORS_ORIGINS.split(",") if o.strip()]
    CORS(app, resources={r"/api/*": {"origins": origins or "*"}})

    store.init_db()
    runtime_config.load()
    app.register_blueprint(api_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(documents_bp)

    @app.errorhandler(404)
    def not_found(_):
        return fail("接口不存在", code=404, http_status=404)

    @app.errorhandler(405)
    def method_not_allowed(_):
        return fail("请求方法不被允许", code=405, http_status=405)

    @app.errorhandler(Exception)
    def internal_error(e):
        app.logger.exception(e)
        return fail(f"服务器内部错误: {e}", code=500, http_status=500)

    return app


app = create_app()

if __name__ == "__main__":
    print(f" * 模型模式: {Config.LLM_PROVIDER}")
    print(f" * API 地址: http://{Config.HOST}:{Config.PORT}/api")
    try:
        from waitress import serve

        # waitress 是纯 Python 生产级 WSGI 服务器：不做反向 DNS、不 fork 子进程，
        # 在受限/沙箱环境下比 Werkzeug 开发服务器稳定，且多线程可并发处理流式请求
        serve(app, host=Config.HOST, port=Config.PORT, threads=16)
    except ImportError:
        app.run(
            host=Config.HOST,
            port=Config.PORT,
            debug=Config.DEBUG,
            use_reloader=False,
            threaded=True,
        )
