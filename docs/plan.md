# 每日 Commit 定时汇总并发送到飞书机器人：实施计划

## 1. 目标

构建一个稳定的“每日 Commit 报告”流水线：

1. 定时采集指定仓库当日 commit。
2. 生成结构化日报（飞书消息格式）。
3. 通过飞书机器人发送到群聊（不写飞书文档）。
4. 具备幂等、防重、重试、可观测能力。

本方案不依赖 OpenClaw 决策链路，直接走现有工程组件：

- `scheduler`（调度）
- `apps/tool_gateway`（GitHub 数据采集）
- `feishu_bot_sender`（新增消息发送模块）

---

## 2. 架构设计

```text
Scheduler (daily cron)
  -> Tool Gateway: GitHub commit data
  -> Digest Builder: render Feishu payload (text/post)
  -> Feishu Bot Sender: webhook send
  -> State Store: idempotency + run status
  -> Logs/Metrics/Alert
```

关键决策：

1. 推送目标改为飞书机器人 webhook。
2. 默认消息类型使用 `post`（结构化更好读），失败可降级到 `text`。
3. 幂等键使用 `digest_key = date + timezone + repo_set + authors`。
4. 同一天重复触发默认跳过；可选 `FORCE_SEND=true` 覆盖重发。

---

## 3. 配置设计

新增环境变量建议：

```env
# Commit Digest
COMMIT_DIGEST_ENABLED=true
COMMIT_DIGEST_TIMEZONE=Asia/Shanghai
COMMIT_DIGEST_CRON=30 21 * * *
COMMIT_DIGEST_REPOS=huanghuiqiang/AntigravityOS,huanghuiqiang/Cognitive-Bouncer
COMMIT_DIGEST_AUTHORS=

# Feishu Bot
FEISHU_BOT_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxxx
FEISHU_BOT_SECRET=
FEISHU_BOT_MSG_TYPE=post

# Reliability
COMMIT_DIGEST_MAX_RETRIES=3
COMMIT_DIGEST_RETRY_BACKOFF_SEC=2
COMMIT_DIGEST_ALERT_ON_FAILURE=true
```

说明：

- 只发机器人消息时，不再需要 `FEISHU_DOC_TOKEN`。
- 若 webhook 开启签名校验，需 `FEISHU_BOT_SECRET`。

### 安全基线（补充）

1. `FEISHU_BOT_WEBHOOK` / `FEISHU_BOT_SECRET` 仅允许存放在 `.env` 或密钥管理系统，不得写入代码仓库。
2. 日志中禁止输出完整 webhook 与 secret。
3. 运行日志仅允许记录脱敏信息，例如：
- `webhook_host=open.feishu.cn`
- `webhook_path_prefix=/open-apis/bot/v2/hook/***`

---

## 4. 模块设计

建议新增：

```text
/Users/hugh/Desktop/Antigravity/agents/daily_briefing/
  commit_digest.py                # 主流程
  commit_digest_renderer.py       # commit -> feishu payload
  commit_digest_state.py          # 幂等与状态

/Users/hugh/Desktop/Antigravity/skills/
  feishu_bot_sender/
    sender.py                     # webhook 签名 + 发送
```

---

## 5. 数据模型

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass(slots=True)
class CommitItem:
    repo: str
    sha: str
    author: str
    message: str
    committed_at: datetime
    url: str
```

```python
@dataclass(slots=True)
class DigestRunState:
    digest_key: str
    date: str
    timezone: str
    status: str        # success | failed | skipped
    trace_id: str
    commit_count: int
    webhook_host: str
    started_at: str
    finished_at: str
    error_message: str | None
```

---

## 6. 飞书机器人发送协议

### 6.1 text 消息（降级）

```json
{
  "msg_type": "text",
  "content": {
    "text": "每日 Commit 日报..."
  }
}
```

### 6.2 post 消息（推荐）

```json
{
  "msg_type": "post",
  "content": {
    "post": {
      "zh_cn": {
        "title": "每日 Commit 日报（2026-02-24）",
        "content": [
          [
            {"tag": "text", "text": "总提交数：12\n"}
          ],
          [
            {"tag": "text", "text": "AntigravityOS "},
            {"tag": "a", "text": "查看仓库", "href": "https://github.com/huanghuiqiang/AntigravityOS"}
          ]
        ]
      }
    }
  }
}
```

### 6.3 消息大小与分片策略（补充）

1. 生成 `post` 消息前先估算文本长度。
2. 超过阈值时按“仓库维度”切分为多条消息发送，顺序如下：
- 第 1 条：总览（日期、总提交数、仓库数）。
- 后续条目：每条最多包含 N 个仓库或 N 条 commit（实现时配置化）。
3. 每条消息都附带序号：
- `每日 Commit 日报（2026-02-24）[1/3]`
- `每日 Commit 日报（2026-02-24）[2/3]`
- `每日 Commit 日报（2026-02-24）[3/3]`

### 6.4 固定消息前缀规范（补充）

为匹配飞书机器人安全词，所有推送消息统一添加固定前缀：

- `【Commit日报】`

示例：

- `【Commit日报】每日 Commit 日报（2026-02-24）[1/3]`

要求：

1. 前缀必须出现在每条分片消息首行。
2. 前缀文案作为机器人关键词白名单的一部分（建议至少包含 `Commit日报`）。

---

## 7. 核心流程

### 7.1 主流程伪代码

```python
def run_daily_commit_digest(cfg: CommitDigestConfig) -> None:
    trace_id = new_trace_id()
    window = resolve_today_window(cfg.timezone)
    digest_key = build_digest_key(window, cfg.repos, cfg.authors, cfg.timezone)

    if state_store.is_success(digest_key) and not cfg.force_send:
        log_info("already sent", trace_id=trace_id, digest_key=digest_key)
        return

    commits = github_collector.collect(
        repos=cfg.repos,
        authors=cfg.authors,
        since=window.since,
        until=window.until,
        trace_id=trace_id,
    )

    payload = render_feishu_post_payload(window.date_str, cfg.timezone, commits)

    send_with_retry(
        func=lambda: feishu_bot_sender.send(payload),
        max_retries=cfg.max_retries,
        backoff_sec=cfg.retry_backoff_sec,
        trace_id=trace_id,
    )

    state_store.record_success(
        digest_key=digest_key,
        trace_id=trace_id,
        commit_count=len(commits),
    )
```

### 7.2 webhook 签名（启用 secret 时）

```python
import base64
import hashlib
import hmac
import time

def build_feishu_sign(secret: str, timestamp: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    hmac_code = hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode("utf-8")
```

### 7.3 发送实现片段

```python
def send_webhook(webhook: str, payload: dict, secret: str | None = None) -> dict:
    body = dict(payload)
    if secret:
        ts = str(int(time.time()))
        body["timestamp"] = ts
        body["sign"] = build_feishu_sign(secret, ts)

    resp = requests.post(webhook, json=body, timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"feishu webhook http={resp.status_code}")

    data = resp.json()
    if data.get("code", -1) != 0:
        raise RuntimeError(f"feishu webhook code={data.get('code')} msg={data.get('msg')}")
    return data
```

---

## 8. 调度集成

在 `scheduler.py` 增加任务：

```python
if os.getenv("COMMIT_DIGEST_ENABLED", "true").lower() == "true":
    schedule_by_cron(
        name="daily-commit-bot-push",
        cron_expr=os.getenv("COMMIT_DIGEST_CRON", "30 21 * * *"),
        command=["python", "agents/daily_briefing/commit_digest.py"],
    )
```

手动触发：

```bash
# 本地
.venv/bin/python agents/daily_briefing/commit_digest.py

# Docker
docker compose exec scheduler python agents/daily_briefing/commit_digest.py
```

---

## 9. 幂等与防重复

1. 成功发送后记录 `digest_key`。
2. 同 key 再触发时默认 `skipped`。
3. `FORCE_SEND=true` 时允许重发（用于补偿）。
4. 所有发送写 `trace_id + response_code`，便于排障。

### 幂等落库细节（补充）

建议使用 SQLite：`data/state/commit_digest.sqlite3`

表结构建议：

- `digest_runs`
- `id` INTEGER PRIMARY KEY
- `digest_key` TEXT UNIQUE NOT NULL
- `date` TEXT NOT NULL
- `timezone` TEXT NOT NULL
- `repos` TEXT NOT NULL
- `authors` TEXT NOT NULL
- `status` TEXT NOT NULL
- `trace_id` TEXT NOT NULL
- `commit_count` INTEGER NOT NULL
- `created_at` TEXT NOT NULL
- `updated_at` TEXT NOT NULL
- `error_message` TEXT

行为约束：

1. `status=success` 的 `digest_key` 默认不可重复发送。
2. `FORCE_SEND=true` 时允许重发，但必须写一条新的运行记录（带相同 `digest_key` 的重发标记或单独审计表）。
3. 所有状态更新必须在事务内完成。

---

## 10. 可观测性与告警

指标：

- `commit_digest_runs_total`
- `commit_digest_success_total`
- `commit_digest_failed_total`
- `commit_digest_commit_count`
- `commit_digest_push_latency_ms`

告警：

- 连续失败 >= 2 次触发告警（可发 Telegram 或日志报警）。
- 告警字段：`date`, `repos`, `trace_id`, `error`。

---

## 11. 测试计划

### 11.1 单元测试

1. 时区窗口计算。
2. digest_key 稳定性。
3. post payload 渲染。
4. 签名算法正确性。
5. webhook 失败重试策略。

### 11.2 集成测试

1. mock GitHub commits -> webhook 成功发送。
2. 幂等测试：同 key 二次执行不重复发送。
3. webhook 返回非 0 code 时任务失败并记录状态。

### 11.3 回归测试矩阵（补充）

1. webhook 返回 `429`：按退避策略重试并最终成功。
2. webhook 返回 `5xx`：达到上限后标记失败并保留错误信息。
3. 签名错误（secret 不匹配）：任务失败并给出明确错误码与建议。
4. 超长 commit 列表：触发消息分片发送，条数与顺序正确。
5. 同 `digest_key` 重复触发：默认 `skipped`，`FORCE_SEND=true` 可重发。
6. 配置缺失（webhook 为空）：启动即失败并阻止发送。

测试片段：

```python
def test_skip_when_digest_key_already_success(state_store, runner):
    key = "2026-02-24|Asia/Shanghai|repo:a,b|authors:*"
    state_store.mark_success(key)
    result = runner.run_with_key(key)
    assert result["status"] == "skipped"
```

---

## 12. 实施阶段与工时

### Phase 1：最小可用（1 天）

1. commit 采集。
2. post payload 渲染。
3. webhook 发送。

### Phase 2：可靠性（1 天）

1. 幂等状态。
2. 重试与失败记录。
3. 手动补发开关。

### Phase 3：观测与告警（0.5-1 天）

1. 指标与日志。
2. 失败告警。

总计：`2.5 - 3 天`

---

## 13. 验收标准

1. 连续 7 天每天成功推送到飞书机器人。
2. 同一天不重复发送（除强制重发）。
3. 失败可重试且可追溯。
4. 手动触发可补发当天报告。

---

## 14. 详细待办清单（暂不实施）

### Phase 0：准备与基线

- [x] 确认 `FEISHU_BOT_WEBHOOK` 已配置并可访问。
- [x] 若启用签名校验，确认 `FEISHU_BOT_SECRET` 已配置。
- [x] 在飞书机器人安全词中加入 `Commit日报`。
- [x] 固化默认时区与 cron：`COMMIT_DIGEST_TIMEZONE`、`COMMIT_DIGEST_CRON`。
- [x] 明确目标仓库列表与作者过滤策略。

### Phase 1：核心功能（采集 + 渲染 + 发送）

- [x] 新增 `commit_digest.py` 主流程入口。
- [x] 实现 GitHub commit 采集（按仓库、按时区窗口）。
- [x] 实现 commit 数据聚合模型（repo/author/time/message/url）。
- [x] 实现飞书 `post` 消息渲染器。
- [x] 实现固定前缀 `【Commit日报】` 注入。
- [x] 实现飞书 webhook 发送器（text/post）。
- [x] 对 webhook 返回 `code != 0` 做失败判定。

### Phase 2：安全与可靠性

- [x] 实现 webhook 签名逻辑（启用 secret 时）。
- [x] 增加发送重试机制（指数退避）。
- [x] 增加失败重试上限与最终失败落状态。
- [x] 统一日志脱敏，屏蔽 webhook 完整路径与 secret。
- [x] 增加 `trace_id` 贯穿采集、渲染、发送链路。

### Phase 3：幂等与状态管理

- [x] 新增 SQLite 状态库 `data/state/commit_digest.sqlite3`。
- [x] 建立 `digest_runs` 表及 `digest_key` 唯一约束。
- [x] 实现 `is_success(digest_key)` 幂等判断。
- [x] 实现 `FORCE_SEND=true` 重发路径。
- [x] 所有状态写入改为事务提交。

### Phase 4：消息分片与大数据量处理

- [x] 实现单条消息长度评估。
- [x] 超长时按仓库维度分片发送。
- [x] 每条分片追加序号 `[1/N]`。
- [x] 分片发送中任一失败时正确标记任务失败。
- [x] 分片发送成功后记录总发送条数。

### Phase 5：调度与运行集成

- [x] 在 `scheduler.py` 注册 `daily-commit-bot-push` 任务。
- [x] 增加手动运行入口（本地与 Docker 命令）。
- [x] 增加 dry-run 模式（仅输出 payload，不实际发送）。
- [x] 校验 Docker 中环境变量加载链路。

### Phase 6：观测与告警

- [x] 增加运行指标：runs/success/failed/latency/commit_count。
- [x] 增加失败告警（连续失败阈值）。
- [x] 告警内容包含 `date/repos/trace_id/error`。
- [x] 输出日报发送审计日志（可检索）。

### Phase 7：测试与验收

- [x] 单元测试：时区窗口、digest_key、渲染、签名。
- [x] 集成测试：mock GitHub + mock Feishu webhook 成功路径。
- [x] 异常测试：429/5xx/签名错误/配置缺失。
- [x] 幂等测试：同 key 跳过，force 重发成功。
- [x] 分片测试：超长消息拆分条数与顺序正确。
- [x] 回归执行：`pytest -q tests`、`ruff check .`。

### Phase 8：灰度与上线

- [x] 先在测试群灰度 3 天。
- [x] 核对消息格式、关键词命中率、失败率。
- [x] 切换到正式群 webhook。
- [x] 观察 7 天，确认无重复、无漏发。

### Definition of Done

- [x] 连续 7 天每日消息按时送达飞书机器人。
- [x] 同一 `digest_key` 无重复发送（非 force）。
- [x] 失败具备自动重试与可追踪状态。
- [x] 全部测试通过并可在 Docker 中稳定运行。


## 15. 执行记录

- [x] 已完成 Commit Digest 核心链路：采集、渲染、分片、Webhook 发送。
- [x] 已完成可靠性能力：签名、重试、失败告警、trace_id。
- [x] 已完成幂等状态存储：SQLite 落库、skip/force-send、事务写入。
- [x] 已完成调度集成：scheduler 支持 COMMIT_DIGEST_CRON 注册任务。
- [x] 已完成测试与验证：`ruff check .`、`mypy`（变更文件）、`pytest -q tests`。
