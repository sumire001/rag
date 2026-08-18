# RAG 智能问答系统

一个飞书问答系统：可以解析文档为知识库的 **RAG 问答**，
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
- **文档管理**：上传 PDF / Word / Excel / CSV / TXT / MD，自动解析与父子切块入库；支持**目录自动导入**（把文档丢进 `data/import/` 即自动处理入库）
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

### 方式二：启动脚本（Windows，推荐）

**直接双击 `start_all.bat` 即可**：首次运行会自动完成环境准备
（检测 Python → 创建 `backend\.venv` → 安装依赖 → 从 `.env.example` 生成 `.env`，
全程约 2~5 分钟），随后弹出三个窗口分别启动后端、前端、飞书通道；再次启动秒过。

| 脚本 | 作用 |
| --- | --- |
| `start_all.bat` | 一键：自动装依赖 + 启动 后端 + 前端 + 飞书（三个独立窗口） |
| `start_backend.bat` | 仅后端（自动清理 5000 端口残留进程） |
| `start_frontend.bat` | 仅前端静态服务器 |
| `start_feishu.bat` | 仅飞书长连接通道 |
| `start_ingest.bat` | 文档目录自动入库监听（`data/import/`） |
| `setup_env.bat` | 环境准备（被上面脚本自动调用；也可单独运行） |

> 前端必须通过静态服务器访问（双击 `index.html` 会触发 `file://` 跨域限制）。
>
> 启动脚本（`.bat`）提示均为**英文（纯 ASCII）**，与系统代码页/编码无关，任意环境双击均正常。

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
| `MEMORY_EMBEDDING_MODEL_DIR` | 空 | local 模型目录：留空自动从魔搭(HF)下载到 `backend/data/models`；指定则用本地目录（离线） |
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

### 方式一：目录自动导入（推荐）

把文档丢进一个目录，自动解析、切块、入库：

```bash
mkdir backend\data\import        # 首次需手动创建投放目录
# 把 PDF / Word / Excel / CSV / TXT / MD 丢进去，然后：
cd backend
.venv\Scripts\python.exe _ingest_dir.py      # 一次性批量导入
# 或常驻监听（新文件放进去即自动入库，约 5 秒一轮）：
.venv\Scripts\python.exe _watch_ingest.py
# Windows 下也可直接运行 start_ingest.bat 启动监听
```

目录约定（均在 `backend/data/` 下）：

| 目录 | 作用 |
| --- | --- |
| `import/` | 投放目录：把文档放进来即可被处理 |
| `imported/` | 成功入库的文档自动归档到这里 |
| `import_failed/` | 解析失败 / 不支持格式的文件移到这里（附原因） |

特性：按文件内容 md5 幂等去重（重复放置不会产生脏数据）、跳过 `~$` 临时文件与隐藏文件、
入库后自动重建 RAG 索引（问答立即可检索到新文档）。

### 方式二：API 上传

`POST /api/documents/upload`（multipart，字段名 `file`），支持
`.pdf .docx .xlsx .xls .csv .txt .md`，上传后自动解析切块并重建检索索引。

### 方式三：内置知识库脚本

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
│   ├── _ingest_doc.py            # 内置知识库（通用IT知识）入库脚本
│   ├── _ingest_dir.py            # 目录批量导入（一次性）
│   ├── _watch_ingest.py          # 目录自动监听（常驻）
│   ├── services/
│   │   ├── chat_service.py       # Web 端业务编排（RAG + 记忆索引）
│   │   ├── llm_provider.py       # 模型适配：echo / OpenAI 兼容
│   │   ├── command_router.py     # /mode /help /clear 命令路由
│   │   ├── runtime_config.py     # 运行时配置（页面可改，落盘 config.json）
│   │   ├── rag/                  # RAG：词法检索 + 父子回溯 + 回复模式
│   │   ├── documents/            # 文档解析切块 + 目录自动导入（ingester）
│   │   ├── memory/               # 记忆：会话摘要 + 跨会话向量召回
│   │   └── feishu/               # 飞书长连接：dispatcher / sessions / client
│   └── data/                     # SQLite、config.json、import、uploads（不入库）
├── frontend/                     # 原生 HTML/CSS/JS，SSE 流式对话
├── start_all.bat / start_backend.bat / start_frontend.bat / start_feishu.bat / start_ingest.bat / setup_env.bat
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
