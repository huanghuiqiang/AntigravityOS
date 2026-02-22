---
name: feishu_bridge
description: 飞书文档桥接技能。提供本地 FastAPI 服务（127.0.0.1:8001）与 Python API，统一为 Agent 提供飞书文档读写能力：追加 Markdown、读取文档全文、健康检查，并内置 token 自动刷新与率限重试。
---

# Feishu Bridge

## 触发条件

- 用户要求“把开发进度自动写入飞书文档”
- 用户要求“通过本地 HTTP 接口读写飞书文档”
- 用户提到“Document Bridge Agent / 飞书文档桥接服务”

## 设计原则（基于 PRD）

- 单点桥接：所有 Agent 仅调用本地接口，不直接管理飞书认证。
- 本地优先：只监听 `127.0.0.1`，默认端口 `8001`。
- 最小闭环：MVP 先覆盖 `append_markdown`、`read_doc`、`health`。
- 扩展能力：支持 `update_bitable` 更新多维表格记录。
- 扩展能力：支持 `create_sub_doc` 创建周报/里程碑子文档。
- 容错优先：401/403 自动刷新 token，429 自动重试（3 次，1s 间隔）。

## 开发步骤（可落地）

1. 环境准备

```bash
pip install fastapi uvicorn python-dotenv httpx lark-oapi
```

2. 配置凭证

```bash
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxx"
# 可选，不填则使用固定项目文档 token
export FEISHU_DOC_TOKEN="H6ZfwwCcGiTMC2k5YgBcTBO3nKe"
```

3. 启动服务

```bash
uvicorn skills.feishu_bridge.main:app --host 127.0.0.1 --port 8001 --reload
```

4. 回归验证

```bash
curl -s -X POST http://127.0.0.1:8001/health

curl -s -X POST http://127.0.0.1:8001/append_markdown \
  -H 'Content-Type: application/json' \
  -d '{"section_title":"每日进度日志","markdown":"## 2026-02-22\n- 完成桥接服务 MVP"}'

curl -s -X POST http://127.0.0.1:8001/read_doc \
  -H 'Content-Type: application/json' \
  -d '{"format":"markdown"}'

curl -s -X POST http://127.0.0.1:8001/update_bitable \
  -H 'Content-Type: application/json' \
  -d '{"app_token":"app_x","table_id":"tbl_x","record_id":"rec_x","fields":{"Status":"Done"}}'

curl -s -X POST http://127.0.0.1:8001/create_sub_doc \
  -H 'Content-Type: application/json' \
  -d '{"title":"周报 - 2026-02-22"}'
```

## Python API

```python
from skills.feishu_bridge import build_bridge_from_env

bridge = build_bridge_from_env()
print(bridge.health())
print(bridge.append_markdown("- 自动写入一条日志", section_title="每日进度日志"))
print(bridge.read_doc("markdown"))
print(bridge.update_bitable("app_x", "tbl_x", "rec_x", {"Status": "Done"}))
print(bridge.create_sub_doc("周报 - 2026-02-22"))
bridge.close()
```

## 文件说明

- `skills/feishu_bridge/bridge.py`: 飞书 API 交互核心（认证、重试、文档读写）
- `skills/feishu_bridge/main.py`: FastAPI 接口层
- `skills/feishu_bridge/__init__.py`: 对外导出
