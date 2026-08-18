# 第三方组件许可声明（Third-Party Notices）

本项目（RAG · 问答系统）基于 MIT 许可开源（见 `LICENSE`）。
以下是本项目直接依赖的第三方组件及其许可证。完整许可文本以各上游仓库/发行包为准。

## Python 后端依赖（backend/requirements.txt）

| 组件 | 版本 | 许可证 | 项目主页 |
| --- | --- | --- | --- |
| Flask | 3.0.3 | BSD-3-Clause | https://github.com/pallets/flask |
| flask-cors | 4.0.1 | MIT | https://github.com/corydolphin/flask-cors |
| requests | 2.32.3 | Apache-2.0 | https://github.com/psf/requests |
| python-dotenv | 1.0.1 | BSD-3-Clause | https://github.com/theskumar/python-dotenv |
| numpy | >=1.26 | BSD-3-Clause | https://github.com/numpy/numpy |
| sentence-transformers | >=2.3 | Apache-2.0 | https://github.com/UKPLab/sentence-transformers |
| lark-oapi（飞书开放平台 SDK） | >=1.7.2 | MIT | https://github.com/larksuite/oapi-sdk-python |
| pypdf | >=4.0 | BSD-3-Clause | https://github.com/py-pdf/pypdf |
| python-docx | >=1.1 | MIT | https://github.com/python-openxml/python-docx |
| openpyxl | >=3.1 | MIT | https://github.com/CPernet/openpyxl |
| waitress | >=3.0 | ZPL-2.1 | https://github.com/Pylons/waitress |

## 前端

前端为原生 HTML / CSS / JavaScript 实现，**无第三方运行时依赖**（未使用 npm 包）。

## 数据与模型

- 知识库文档《通用IT知识.docx》：项目内置内容，随仓库分发。
- 记忆向量检索默认使用 `lexical` 模式（词袋 + 特征哈希，纯标准库实现），无需下载模型；
  如开启 `local` 模式（`MEMORY_EMBEDDING_PROVIDER=local`），将使用
  `BAAI/bge-small-zh-v1.5` 模型，其遵循
  [MIT 许可](https://huggingface.co/BAAI/bge-small-zh-v1.5)（以模型卡片为准）。

## 使用说明

- 如需以二进制/整体形式再分发本项目，请保留本文件与 `LICENSE`；
- 各依赖的完整许可证文本可在上表项目主页中获取；
- 本声明仅覆盖本项目直接依赖；间接依赖（传递依赖）以各自上游许可为准。
