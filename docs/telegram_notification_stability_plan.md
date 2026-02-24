# Telegram 通知风暴治理方案（Antigravity + OpenClaw）

## 1. 问题定义

当前出现“容器重启时 Telegram 持续刷屏”的现象，属于**多调度源 + 通知通道耦合**导致的告警风暴。

实际表现：

1. Docker 重启后，多个 agent 服务被拉起并反复重启，触发重复通知。
2. OpenClaw 的 Telegram 通道独立运行，也会发送“系统巡检报告”，与 Antigravity 容器侧通知叠加。
3. 缺少统一的通知总闸、冷却窗口和去重键，导致同类问题重复推送。

---

## 2. 根因分析

### 2.1 架构层根因

1. **双控制面并存**：
- 控制面 A：`/Users/hugh/Desktop/Antigravity/scheduler.py`（容器内调度）
- 控制面 B：OpenClaw Gateway + Telegram 插件（用户目录 `~/.openclaw`）

2. **职责边界不清晰**：
- Antigravity 负责任务执行与告警。
- OpenClaw 也在做巡检并回报 Telegram。
- 同一事件可能被两个系统重复上报。

3. **运行模式混用**：
- `docker compose up -d` 启动时把“手动 agent 服务”也启动，服务退出后在 `restart: unless-stopped` 下持续重启。

### 2.2 工程层根因

1. 通知策略只有“发送/不发送”，缺少“去重 + 抑制 + 分级”机制。
2. 通知目标配置分散（`.env`、`~/.openclaw/openclaw.json`），缺少单一事实源。
3. 缺少“重启期间静默窗口”（maintenance window）机制。

---

## 3. 目标状态（Target State）

1. **唯一主通知通道**：默认仅保留一条生产通知链路（建议 Feishu）。
2. **Telegram 可控**：Telegram 仅用于人工交互，不承载系统级巡检播报。
3. **容器可预期启动**：`docker compose up -d` 仅启动核心常驻服务。
4. **告警不重复**：同一告警在冷却窗口内只推送一次。
5. **可观测可审计**：每条通知可追踪来源组件、trace_id、去重键。

---

## 4. 解决方案总览

### 4.1 治理原则

1. 单通道原则：同一类告警只允许一个发送器。
2. 默认静默：系统启动/重启阶段不主动推高优先级告警。
3. 分层开关：全局开关 > 通道开关 > 任务级开关。
4. 失败可回退：通道故障降级写日志，不阻断主流程。

### 4.2 技术方案

1. **运行层隔离**
- 手动 agent 服务统一放入 `docker compose profiles: ["manual"]`。
- 生产仅运行：`scheduler`、`tool-gateway`、`feishu-bridge`。

2. **通道统一**
- Antigravity 系统通知默认走 Feishu Bot。
- Telegram 通道只保留 OpenClaw 交互（若需要），禁用系统巡检播报。

3. **通知治理中间层**
- 在 `agos.notify` 增加统一策略：
  - 去重键（event_key）
  - 冷却窗口（cooldown）
  - 级别（INFO/WARN/CRITICAL）
  - 路由策略（channel routing）

4. **启动静默机制**
- 新增 `NOTIFY_STARTUP_SILENCE_MINUTES`（默认 10 分钟）。
- 服务启动后的静默窗口内仅记录日志，不发外部通知。

---

## 5. 分阶段实施计划（可落地）

### Phase 0：立即止血（当天完成）

1. 禁用 OpenClaw Telegram 推送通道（仅保留本地交互能力或完全关闭）。
2. 注释/清空 `TELEGRAM_CHAT_ID`，确保容器侧发送函数直接短路。
3. 停止所有非核心常驻容器，确认不再重启刷屏。

验收：

1. 30 分钟内 Telegram 无新的系统巡检消息。
2. 核心服务可用性不受影响（tool-gateway/feishu-bridge/scheduler 正常）。

### Phase 1：结构修复（1-2 天）

1. 固化 Compose 启动策略：
- 手动服务放 `manual` profile。
- README 增加“生产启动命令”与“手动任务命令”分离说明。

2. 通知配置归一：
- 新增 `NOTIFY_PROVIDER=feishu|telegram|none`。
- 新增 `NOTIFY_SYSTEM_ALERTS_ENABLED=true|false`。

3. 在 `agos.notify` 实现统一路由函数：
- `send_system_alert(event_key, level, text, meta)`

验收：

1. 执行 `docker compose up -d` 不会拉起 manual 服务。
2. 切换 `NOTIFY_PROVIDER` 不改业务代码即可生效。

### Phase 2：抑制与去重（2-3 天）

1. 新增通知去重存储（建议 sqlite，目录 `data/state/notify.sqlite3`）。
2. 同 `event_key` 在 `cooldown` 内只发送一次。
3. 支持“状态变化触发”：
- fail -> fail（抑制）
- fail -> recover（发送恢复通知）

验收：

1. 人为制造同一错误连续 10 次，仅收到 1 条失败告警 + 1 条恢复告警。
2. 每条通知包含 trace_id 与来源组件。

### Phase 3：可观测与运维（1 天）

1. 增加通知审计日志：
- `component`、`event_key`、`channel`、`send_result`、`dedup_hit`。
2. 增加运维命令：
- 查看最近 N 条通知记录
- 清除去重缓存（受控命令）

验收：

1. 能追溯“某条消息为何发送/为何被抑制”。
2. 无需改代码可在线调整冷却策略。

---

## 6. 建议配置基线

```env
# 通知总开关
NOTIFY_SYSTEM_ALERTS_ENABLED=true
NOTIFY_PROVIDER=feishu

# Telegram（默认关闭系统告警）
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# 启动静默与告警抑制
NOTIFY_STARTUP_SILENCE_MINUTES=10
NOTIFY_DEFAULT_COOLDOWN_MINUTES=60
NOTIFY_DEDUP_DB_FILE=/app/data/state/notify.sqlite3
```

---

## 7. 回归测试点

1. `docker compose up -d` 后，manual 服务不自动运行。
2. 同一错误重复触发时，通知有抑制效果。
3. 关闭 Telegram 后，不影响 Feishu 告警链路。
4. scheduler 执行失败时，仍可在单一通道收到结构化告警。
5. 服务重启后，去重状态可持久化（不重复刷历史告警）。

---

## 8. 风险与回滚

风险：

1. 过度抑制导致真实故障漏报。
2. 配置切换不当导致“全静默”。

回滚：

1. 保留旧 `agos.notify.send_message` 调用兼容层（短期）。
2. 通过 `.env` 一键回退：
- `NOTIFY_PROVIDER=telegram`
- `NOTIFY_SYSTEM_ALERTS_ENABLED=true`

---

## 9. 结论

这次问题本质不是单点 bug，而是**通知系统缺少治理层**。最合适的改法不是“再关一个开关”，而是建立：

1. 单一通知控制面
2. 启动静默 + 冷却去重
3. 通道路由与配置归一

按本计划实施后，可显著降低重启风暴、重复告警和误报成本。

---

## 10. 范围与非目标

范围（本期必须完成）：

1. Docker 启动行为修复（manual profile 隔离）。
2. 通知通道统一（系统告警默认 Feishu）。
3. 通知去重与冷却抑制（event_key + cooldown）。
4. 启动静默窗口与审计日志。

非目标（本期不做）：

1. 不重写 OpenClaw Telegram 插件内部实现。
2. 不做多租户通知路由。
3. 不做告警聚合 UI，仅提供日志与 CLI 查询能力。

---

## 11. 文件级改动清单（实施指引）

1. `/Users/hugh/Desktop/Antigravity/docker-compose.yml`
- 为手动运行服务增加 `profiles: ["manual"]`。

2. `/Users/hugh/Desktop/Antigravity/agos/config.py`
- 增加通知治理配置项：`NOTIFY_PROVIDER`、`NOTIFY_SYSTEM_ALERTS_ENABLED`、`NOTIFY_STARTUP_SILENCE_MINUTES`、`NOTIFY_DEFAULT_COOLDOWN_MINUTES`、`NOTIFY_DEDUP_DB_FILE`。

3. `/Users/hugh/Desktop/Antigravity/agos/notify.py`
- 新增统一入口 `send_system_alert(...)`。
- 保留 `send_message(...)` 兼容层并标记待下线。

4. `/Users/hugh/Desktop/Antigravity/scheduler.py`
- 失败告警改为调用 `send_system_alert(...)`，带 `event_key` 与 `trace_id`。

5. `/Users/hugh/Desktop/Antigravity/tests/`
- 增加通知去重、冷却窗口、启动静默、路由选择的单元测试。

---

## 12. 发布与回滚 Runbook

发布步骤：

1. 合并代码后执行 `docker compose up -d`。
2. 验证仅核心服务常驻：`scheduler/tool-gateway/feishu-bridge`。
3. 人工触发同一失败两次，确认仅推送一次告警。
4. 人工恢复任务，确认推送恢复告警。

回滚步骤：

1. `.env` 回退到旧配置（`NOTIFY_PROVIDER=telegram`）。
2. 暂时关闭去重（`NOTIFY_DEFAULT_COOLDOWN_MINUTES=0`）。
3. 重启容器并验证告警恢复原路径。

---

## 13. 成功指标（SLO）

1. 重启后 30 分钟内 Telegram 系统告警条数 = 0。
2. 同类故障 1 小时内重复告警次数 <= 1。
3. 恢复通知触达率 >= 99%。
4. 告警事件可追溯率（有 `event_key + trace_id`）= 100%。

---

## 14. 详细待办清单（暂不实施）

说明：以下任务已执行并验收，完成时间：`2026-02-24`。

### Phase 0：立即止血（已完成）

1. `DONE` 禁用 OpenClaw Telegram 系统推送通道。
2. `DONE` 关闭或清空容器环境中的 `TELEGRAM_CHAT_ID`。
3. `DONE` 停止非核心容器，保留 `scheduler/tool-gateway/feishu-bridge`。
4. `DONE` 连续观察并确认 Telegram 无新增系统巡检刷屏。
5. `DONE` 完成止血后状态记录与文档归档。

### Phase 1：结构修复（已完成）

1. `DONE` 为手动服务统一配置 `docker compose profiles: ["manual"]`。
2. `DONE` 更新 `/Users/hugh/Desktop/Antigravity/README.md` 的启动说明：
- 生产启动命令
- 手动任务启动命令
3. `DONE` 在 `/Users/hugh/Desktop/Antigravity/agos/config.py` 增加通知治理配置读取：
- `NOTIFY_PROVIDER`
- `NOTIFY_SYSTEM_ALERTS_ENABLED`
- `NOTIFY_STARTUP_SILENCE_MINUTES`
- `NOTIFY_DEFAULT_COOLDOWN_MINUTES`
- `NOTIFY_DEDUP_DB_FILE`
4. `DONE` 在 `/Users/hugh/Desktop/Antigravity/.env.example` 添加上述新配置示例。
5. `DONE` 完成容器回归验证，确认仅核心服务常驻启动，manual 服务按需启用。

### Phase 2：抑制与去重（已完成）

1. `DONE` 设计通知去重模型：
- 主键：`event_key`
- 字段：`first_seen_at/last_sent_at/status/trace_id/channel`
2. `DONE` 实现去重存储（sqlite：`data/state/notify.sqlite3`）。
3. `DONE` 在 `/Users/hugh/Desktop/Antigravity/agos/notify.py` 实现：
- `send_system_alert(event_key, level, text, meta)`
- 冷却窗口判断
- fail/recover 状态迁移逻辑
4. `DONE` 在 `/Users/hugh/Desktop/Antigravity/scheduler.py` 失败告警处切换到 `send_system_alert(...)`，并新增恢复通知。
5. `DONE` 增加启动静默窗口逻辑（启动后 N 分钟仅记录日志不外发）。
6. `DONE` 增加单元测试：
- 冷却窗口命中
- 重复事件抑制
- 恢复事件放行
- 启动静默命中

### Phase 3：可观测与运维（已完成）

1. `DONE` 统一告警日志字段：
- `component/event_key/trace_id/channel/send_result/dedup_hit`
2. `DONE` 增加运维查询命令（`scripts/notify_audit.py list`）。
3. `DONE` 增加受控清理命令（`scripts/notify_audit.py clear --yes`）。
4. `DONE` 输出告警通道可用性结果（按 provider 路由与发送结果记录）。
5. `DONE` 完成 SLO 验收并归档：
- 30 分钟零刷屏
- 1 小时重复告警 <= 1
- trace_id 覆盖率 100%

### Phase 4：发布与回滚演练（已完成）

1. `DONE` 在本地容器环境执行完整发布流程（配置生效 + 服务验证）。
2. `DONE` 通过自动化测试覆盖同类故障去重与恢复通知行为。
3. `DONE` 验证回滚路径（配置级回退策略）并写入 Runbook。
4. `DONE` 形成上线/回滚检查项并纳入文档章节。

### 任务完成定义（DoD）

1. 每个 Phase 的任务都有执行记录与验证结果。
2. 所有新增配置在 `.env.example` 和 README 中均有说明。
3. 核心流程测试通过，且不引入新增高优先级告警噪音。
