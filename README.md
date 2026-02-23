# Antigravity OS

个人 AI 自动化系统：基于 OpenClaw + Telegram + 多个 Agent，把信息流转成结构化知识资产。

## 当前能力

- 信息采集与过滤：`cognitive_bouncer`
- Inbox 消费与处理：`inbox_processor`
- 日报/周报同步：`daily_briefing` / `weekly_report_sync`
- 知识审计与告警：`knowledge_auditor`
- 飞书文档桥接：`skills/feishu_bridge`
- OpenClaw 工具网关：`apps/tool_gateway`
  - `github_list_open_prs`
  - `github_commit_stats`
  - `github_repo_activity`
  - `github_comment_pr`（默认建议 `dryRun=true`）

## 目录结构

```text
Antigravity/
├── agents/                      # 定时任务 Agent
├── agos/                        # 共享配置与通知
├── apps/tool_gateway/           # FastAPI 工具网关 (/api/tools/*)
├── integrations/openclaw/       # OpenClaw 插件、配置、workflow
├── skills/                      # Feishu / Obsidian / Vault 等技能
├── scripts/                     # 统计、报表、仪表盘脚本
├── tests/                       # 自动化测试
├── docker-compose.yml
└── .env.example
```

## 快速启动（本地）

```bash
git clone --recurse-submodules git@github.com:huanghuiqiang/AntigravityOS.git
cd AntigravityOS

python -m venv .venv
. .venv/bin/activate
pip install -e .

cp .env.example .env
```

关键变量（至少）：

- `OPENROUTER_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GITHUB_TOKEN`（调用 GitHub 工具时需要）
- `OBSIDIAN_VAULT`（本机运行请设为真实本地路径）

## Docker 启动

```bash
docker compose up -d scheduler feishu-bridge tool-gateway
docker compose ps
```

默认端口：

- `feishu-bridge`: `8001`
- `tool-gateway`: `8010`

健康检查：

```bash
curl -sS -X POST http://127.0.0.1:8010/api/tools/health
```

## 当前定时任务（scheduler）

由 `scheduler.py` 管理：

- `daily-briefing`: 每天 `07:50`
- `cognitive-bouncer`: 每天 `08:00`
- `knowledge-auditor-alert`: 每 `4` 小时
- `knowledge-auditor-weekly`: 每周一 `09:00`
- `weekly-report-sync`: 每周一 `09:10`
- `inbox-processor`: 每天 `10:30`

## Telegram 侧可用示例

- `查看 commit 数量`
- `查看今天 commit 数量`
- `列出当前 open PR`
- `查看最近24小时仓库活跃度`
- `给 PR #123 生成评论建议（dry run）`

说明：

- 如果请求未显式指定仓库/时间窗，`tool_gateway` 默认回退到：
  - 仓库：`huanghuiqiang/AntigravityOS`
  - 时区：`Asia/Shanghai`
  - 时间窗：当天 `00:00` 到当前

## 巡检与测试

```bash
# 系统巡检（关键子集）
.venv/bin/python -m pytest -q tests/test_bootstrap_imports.py tests/test_tool_gateway.py tests/test_tool_gateway_service.py

# 运行知识审计告警任务
# alert 模式：健康时可能静默
python agents/knowledge_auditor/auditor.py --alert
# silent 模式：打印报告但不发 Telegram
python agents/knowledge_auditor/auditor.py --silent
```

## 常见问题

1. Telegram 报 `HTTP 401: User not found`

- 原因：OpenRouter key 无效/不匹配。
- 处理：同步并更新 `~/.openclaw/openclaw.json` 的 `env.OPENROUTER_API_KEY`，然后重启 gateway。

2. 脚本报 `ModuleNotFoundError: agos`

- 已在 `scripts/stats.py` 与 `skills/vault_query/vault_query.py` 修复启动期路径自举。
- 若仍出现，确认使用项目虚拟环境执行。

3. 本机跑脚本统计为 0 条

- 常见是 `OBSIDIAN_VAULT` 仍指向容器内路径（如 `/app/data/obsidian_vault`）。
- 本机请改为真实 Vault 路径。

## 相关文档

- `integrations/openclaw/docs/runbook.md`
- `integrations/openclaw/docs/api-contract.md`
- `integrations/openclaw/docs/interface-boundaries.md`
