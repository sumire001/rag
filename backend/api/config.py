"""模型配置接口：页面左下角「设置」面板读写 LLM 配置。

接口：
    GET  /config    返回当前配置（api_key 已脱敏）
    PUT  /config    合并更新配置并落盘；api_key 为 "__CLEAR__" 表示清空，
                    缺省不传则保持原值
"""

from flask import Blueprint, request

from services import runtime_config
from utils.response import fail, ok

bp = Blueprint("config_api", __name__, url_prefix="/api")


@bp.get("/config")
def get_config():
    return ok(runtime_config.to_public())


@bp.put("/config")
def put_config():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return fail("请求体格式错误")
    try:
        cfg = runtime_config.update(data)
    except ValueError as e:
        return fail(str(e), http_status=400)
    except OSError as e:
        return fail(
            "保存配置失败：配置文件被其他程序占用，请先关闭打开 config.json 的编辑器"
            "（尤其是记事本）后重试。底层错误：" + str(e),
            http_status=500,
        )

    return ok(cfg)
