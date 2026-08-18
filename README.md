# RAG 智能问答系统

面向教育场景的智能问答系统：以《通用IT知识》文档为知识库的 **RAG 问答**，
同时提供 **Web 对话界面**与**飞书机器人**两个入口，二者共用同一套会话、知识库与回复模式。

- 后端：Python / Flask + waitress，SQLite 持久化（WAL 模式）
- 前端：原生 HTML / CSS / JS（无构建步骤），SSE 流式输出
- 飞书：lark-oapi 长连接模式，无需配置回调地址

## 功能特性

- **RAG 问答**：基于知识库文档检索作答，末尾自动附「📚 来源」引用
  - 纯本地词法检索（词袋 + 特征哈希），**断网可用**，无需任何 embedding 模型
  - 父子两级切块：检索命中子块、回溯父块作为模型上下文
- **两种回复模式**（页面开关 / `/mode` 命令均可切换）
  - `strict`（严格）：只依据资料回答，资料缺失直接拒答
  - `rag_first`（优先）：优先资料，缺失时回落模型通用知识（标注💡来源）
- **LLM 适配层**（`services/llm_provider.py`）
  - `echo`：离线回声模式，无需任何 Key，开箱即用
  - `openai`：任意 OpenAI 兼容接口（DeepSeek / 通义百炼 / 混元 / 本地 Ollama 等）
- **记忆系统**：层1 会话内早期摘要 + 层2 跨会话向量召回（支持 local / openai / lexical 三种 embedding 来源）
- **文档管理**：上传 PDF / Word / Excel / CSV / TXT / MD，自动解析与父子切块入库
- **飞书机器人**：群聊（@机器人）与私聊均可，与 Web 端共用会话与知识库
- **命令路由**：`/mode`、`/help`、`/clear`（中英文等价），Web 与飞书行为一致

## 快速开始

### 方式一：命令行

```bash
# 1. 后端（Python 3.10+）
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env
python app.py                   # http://127.0.0.1:5000

# 2. 前端（另开终端）
cd frontend
python -m http.server 5500      # 浏览器打开 http://127.0.0.1:5500
```

### 方式二：启动脚本（Windows）

| 脚本 | 作用 |
| --- | --- |
| `start_all.bat` | 一键启动 后端 + 前端 + 飞书（三个独立窗口） |
| `start_backend.bat` | 仅后端（自动清理 5000 端口残留进程） |
| `start_frontend.bat` | 仅前端静态服务器 |
| `start_feishu.bat` | 仅飞书长连接通道 |

> 前端必须通过静态服务器访问（双击 `index.html` 会触发 `file://` 跨域限制）。

## 配置

### `.env` 环境变量（backend/.env）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_HOST` / `APP_PORT` | 127.0.0.1 / 5000 | 服务监听地址 |
| `CORS_ORIGINS` | `*` | 允许跨域来源，逗号分隔 |
| `LLM_PROVIDER` | `echo` | `echo` 离线 / `openai` 兼容接口 |
| `LLM_BASE_URL` | https://api.openai.com/v1 | OpenAI 兼容 Base URL |
| `LLM_API_KEY` | 空 | API Key |
| `LLM_MODEL` | gpt-4o-mini | 模型名 |
| `LLM_TEMPERATURE` | 0.7 | 采样温度 |
| `RAG_MODE` | rag_first | 回复模式 strict / rag_first |
| `MEMORY_EMBEDDING_PROVIDER` | local | 记忆向量来源 local / openai / lexical |
| `FEISHU_ENABLED` | 0 | 是否随后端启用飞书 |
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | 空 | 飞书开放平台应用凭证 |
| `FEISHU_ENCRYPT_KEY` / `FEISHU_VERIFICATION_TOKEN` | 空 | 事件加密 / 校验令牌（可选） |

### 页面设置面板

Web 界面左下角「设置」可动态修改模型配置（**无需重启**），保存后持久化到
`backend/data/config.json`，运行优先级高于 `.env`：

- 模型类型：Echo（离线回声）/ OpenAI 兼容
- API Base URL / API Key / 模型名称 / 温度
- 严格按知识库回答（对应 `RAG_MODE`）

## 知识库入库

- 通过 API 上传：`POST /api/documents/upload`（multipart，字段名 `file`），支持
  `.pdf .docx .xlsx .xls .csv .txt .md`，上传后自动解析切块并进入检索索引
- 内置知识库（《通用IT知识.docx》）可用脚本导入：

```bash
cd backend
.venv\Scripts\python.exe _ingest_doc.py
```

> 知识库数据位于 `backend/data/`（已加入 `.gitignore`，不进版本库），
> 新环境首次部署需重新入库。

## 飞书机器人

1. 在飞书开放平台创建应用，开启「机器人」能力，申请 `im:message` 相关权限；
2. 在 `backend/.env` 填写 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`；
3. 启动：`start_all.bat` 或 `start_feishu.bat`（长连接模式，无需配置回调地址）；
4. 群聊中 @机器人 提问，或与机器人私聊。

支持命令：`/mode strict`、`/mode rag_first`、`/mode`（查询）、`/help`、`/clear`
（中文等价：模式 严格 / 模式 优先 / 模式 / 帮助 / 清除）。

## 目录结构

```
MyProject/
├── backend/
│   ├── app.py                    # Flask 入口（waitress 生产服务器）
│   ├── config.py                 # 配置集中管理（环境变量覆盖）
│   ├── requirements.txt          # Python 依赖
│   ├── .env.example              # 环境变量模板
│   ├── api/                      # 路由层（chat / config / documents）
│   ├── models/store.py           # SQLite 持久化
│   ├── services/
│   │   ├── chat_service.py       # Web 端业务编排（RAG + 记忆索引）
│   │   ├── llm_provider.py       # 模型适配：echo / OpenAI 兼容
│   │   ├── command_router.py     # /mode /help /clear 命令路由
│   │   ├── runtime_config.py     # 运行时配置（页面可改，落盘 config.json）
│   │   ├── rag/                  # RAG：词法检索 + 父子回溯 + 回复模式
│   │   ├── documents/            # 文档解析（PDF/Word/Excel/CSV/TXT/MD）+ 切块
│   │   ├── memory/               # 记忆：会话摘要 + 跨会话向量召回
│   │   └── feishu/               # 飞书长连接：dispatcher / sessions / client
│   └── data/                     # SQLite、config.json、uploads（不入库）
├── frontend/                     # 原生 HTML/CSS/JS，SSE 流式对话
├── start_all.bat / start_backend.bat / start_frontend.bat / start_feishu.bat
├── LICENSE                       # MIT 许可
├── THIRD_PARTY_NOTICES.md        # 第三方组件许可声明
└── README.md
```

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查（返回当前模型模式） |
| GET/PUT | `/api/config` | 读取 / 保存模型配置（api_key 脱敏） |
| GET/POST | `/api/conversations` | 会话列表 / 新建 |
| PATCH/DELETE | `/api/conversations/<id>` | 重命名 / 删除会话 |
| GET/DELETE | `/api/conversations/<id>/messages` | 消息列表 / 清空 |
| POST | `/api/chat` | 发送消息（一次性返回） |
| POST | `/api/chat/stream` | 发送消息（SSE 流式） |
| POST | `/api/documents/upload` | 上传并解析文档 |
| GET | `/api/documents` | 文档列表 |
| GET/DELETE | `/api/documents/<id>` | 文档详情 / 删除 |
| GET | `/api/documents/<id>/chunks` | 文档切片列表 |

统一响应体：`{ "code": 0, "msg": "ok", "data": {} }`（`code` 非 0 即失败）。

## 测试

```bash
cd backend
.venv\Scripts\python.exe test_documents.py       # 文档解析 / 切块测试
.venv\Scripts\python.exe test_chain_memory.py    # 记忆召回链路测试
```

## 许可

- 本项目采用 **MIT 许可**，详见 [LICENSE](./LICENSE)；
- 第三方组件许可见 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)。
