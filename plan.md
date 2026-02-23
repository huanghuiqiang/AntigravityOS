# Antigravity × OpenClaw 功能规划（仅 Telegram + GitHub）

## 1. 目标与边界

本计划仅包含以下能力：

1. Telegram 交互优化
- Agent 发送消息支持 Inline Keyboard / Reply Keyboard。
- 用户点击按钮即可触发动作。

2. GitHub Tools 扩展
- 监控仓库。
- 自动评论 PR（审批流）。
- 统计 commit。

明确不做（本轮下线）：
- Gmail / Outlook / Google Calendar / Microsoft Calendar。

参考资料：
- OpenClaw 文档：https://docs.openclaw.ai/
- Telegram Channel 文档：https://docs.openclaw.ai/channels/telegram
- Tools 文档：https://docs.openclaw.ai/tools
- Lobster 文档：https://docs.openclaw.ai/tools/lobster
- OpenClaw 仓库：https://github.com/openclaw/openclaw

---

## 2. 架构决策（按批注收敛）

核心决策：
- OpenClaw 集成层采用 TypeScript Plugin：
  - `integrations/openclaw/plugins/antigravity-tools/`
- Plugin 中所有 `execute()` 不直接请求 GitHub。
- 所有工具统一通过 HTTP Client 调用 Antigravity 暴露的 `/api/tools/*` endpoint，实现零代码重复、统一审计。

调用约定：
- Header 必带 `X-Trace-Id`。
- 返回统一 `{ success, data, error, trace_id }`。
- 副作用操作必须支持 `dryRun: boolean`。
- 建议 Antigravity `/api/tools/*` 兼容 `content: [{ type: "text", text: "..." }]` 包装，便于 OpenClaw Tool Orchestrator 直接透传（与内置工具返回风格一致）。
- Antigravity endpoint 统一错误语义：
  - 成功：`HTTP 200 + JSON body`
  - 失败：`HTTP 4xx/5xx + { error, trace_id }`

---

## 3. 目标架构图（更新）

```text
Telegram User
   ↓
OpenClaw Gateway (Telegram Channel)
   ├─ messageActions (inline/reply keyboard)
   ├─ callback_data 路由
   └─ Tool Orchestrator
       ⇅ (HTTP, X-Trace-Id)
Antigravity Tool Adapter (FastAPI /api/tools/*)
   ├─ github_list_open_prs
   ├─ github_comment_pr
   ├─ github_commit_stats
   └─ ag internal actions (daily_briefing/weekly_sync/...)
       ↓
External APIs
   └─ GitHub REST/GraphQL
```

说明：
- 使用“双向桥接”是因为既有 OpenClaw -> Antigravity 的工具调用，也有 Antigravity 触发消息发送的需求。

---

## 4. Telegram 按钮化设计

### 4.1 配置启用

使用 Telegram channel 的 capabilities 配置：

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "botToken": "${TELEGRAM_BOT_TOKEN}",
      "capabilities": {
        "inlineButtons": "allowlist"
      }
    }
  }
}
```
生产要求：
- 必须使用 `allowlist` 并配置显式白名单（如 groups 或 accounts），避免群聊误触发。

### 4.2 发送带按钮消息（修正为 message tool 格式）

```json
{
  "tool": "message",
  "action": "send",
  "args": {
    "channel": "telegram",
    "to": "${chatId}",
    "message": "请选择操作",
    "buttons": [
      [
        { "text": "生成今日日报", "callback_data": "ag:daily_briefing" },
        { "text": "同步周报", "callback_data": "ag:weekly_sync" }
      ],
      [
        { "text": "PR 摘要", "callback_data": "gh:pr_summary" }
      ]
    ]
  }
}
```
说明：
- 按官方示例与 CLI 约定，字段使用 `channel`，不使用 `provider`。
- “也可直接用 Gateway 的 action: "send", channel: "telegram" 格式（无 tool/args 包装），视调用上下文选择。”
### 4.3 callback_data 协议

协议：`<domain>:<action>[:arg]`
- `ag:daily_briefing`
- `gh:comment_pr:123`

约束：
- `callback_data` 长度必须 `<= 64 bytes`。

TypeScript 校验示例：

```ts
export function buildCallbackData(domain: string, action: string, arg?: string): string {
  const value = [domain, action, arg].filter(Boolean).join(":");
  const bytes = Buffer.byteLength(value, "utf8");
  if (bytes > 64) {
    throw new Error(`callback_data too long: ${bytes} bytes`);
  }
  return value;
}
```

### 4.4 回调路由（走 Antigravity HTTP）

说明：
- 回调按官方协议以文本 `callback_data: <value>` 到达。
- MVP 可走 LLM 路由；生产建议加 bypass 插件路由，降低 1-3s 延迟。
- 按官方文档，callback click 传入 agent 的形式是带前缀字符串：`callback_data: <value>`。
- 因此路由器按字符串前缀解析，不处理对象形式（严格模式）。

```ts
function parseCallback(input: string): string | null {
  const trimmed = input.trim();
  const prefix = "callback_data: ";
  if (trimmed.startsWith(prefix)) {
    return trimmed.slice(prefix.length).trim();
  }
  return null;
}

export async function routeTelegramCallback(input: string, traceId: string) {
  const value = parseCallback(input);
  if (!value) return null;

  const [domain, action, arg] = value.split(":");
  const toolName = `${domain}_${action}`;

  const resp = await fetch(`${process.env.ANTIGRAVITY_URL}/api/tools/${toolName}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Trace-Id": traceId
    },
    body: JSON.stringify({ arg })
  });

  if (!resp.ok) {
    throw new Error(`tool bridge failed status=${resp.status} trace_id=${traceId}`);
  }
  return resp.json();
}
```

---

## 5. GitHub 工具设计（唯一业务扩展）

MVP 工具清单：
- `github_list_open_prs(owner, repo)`
- `github_comment_pr(owner, repo, prNumber, body, dryRun)`
- `github_commit_stats(owner, repo, since, until)`
- `github_repo_activity(owner, repo, hours)`

Plugin 端注册示意（仅桥接，不直连 GitHub）：

```ts
import { Type } from "@sinclair/typebox";

api.registerTool({
  name: "github_comment_pr",
  description: "评论 PR（通过 Antigravity 网关，支持 dryRun）",
  parameters: Type.Object({
    owner: Type.String(),
    repo: Type.String(),
    prNumber: Type.Number(),
    body: Type.String(),
    dryRun: Type.Optional(Type.Boolean())
  }),
  async execute(_id, params) {
    const traceId = crypto.randomUUID();
    const res = await fetch(`${process.env.ANTIGRAVITY_URL}/api/tools/github_comment_pr`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Trace-Id": traceId
      },
      body: JSON.stringify(params)
    });
    if (!res.ok) throw new Error(`bridge status=${res.status} trace_id=${traceId}`);
    return { content: [{ type: "text", text: await res.text() }] };
  }
});
```

PR 自动评论建议：
- 优先用 Lobster workflow 包裹审批节点，不直接裸调 tool。
- 默认 `dryRun=true`，审批后再 `dryRun=false`。

---

## 6. 目录结构（去除 Email/Calendar）

```text
/Users/hugh/Desktop/Antigravity/integrations/openclaw/
  config/
    telegram.jsonc
  plugins/
    antigravity-tools/
      index.ts
      router.ts
      tools/
        github.ts
        antigravity.ts
      workflows/
        pr-review-approval.lobster
  docs/
    runbook.md
```

后端 FastAPI 新增建议：

```text
/Users/hugh/Desktop/Antigravity/apps/tool_gateway/
  main.py                # /api/tools/*
  github_service.py      # 直连 GitHub API
  schemas.py             # 请求/响应模型
  audit.py               # trace_id + 审计日志
```

---

## 7. 分阶段计划（更新）

### Phase A（1 周）Telegram 按钮链路 ✅ 已完成

交付：
- inlineButtons 配置生效。
- callback_data 校验与路由。
- message tool 按钮发送模板。

验收：
- 点击按钮后 3 秒内收到回执。
- callback_data 超长会被拒绝并返回可读错误。

### Phase B（1 周）GitHub MVP + 审批流 ✅ 已完成

交付：
- 4 个 GitHub tool（含 dryRun）。
- `github_comment_pr` 接入 Lobster 审批流。
- 审计日志可按 trace_id 检索。

验收：
- 测试仓库可完成“生成建议 -> 审批 -> 评论”闭环。
- 审批拒绝时无副作用。

### Phase C（3-5 天）稳定性与运维 ✅ 已完成

交付：
- 限流、重试、错误分级。
- runbook（故障排查/回滚/权限最小化）。

验收：
- GitHub API 波动不阻塞主会话。
- 关键路径故障可 10 分钟内定位。

---

## 8. 安全与审计

安全要求：
- `GITHUB_TOKEN` 仅环境变量或 Secret 管理，不硬编码。
- GitHub token 权限最小化。
- 高风险操作必须审批（PR 自动评论）。

审计要求：
- 统一字段：`trace_id`, `tool_name`, `actor`, `input_hash`, `result`, `external_id`。
- 所有副作用接口支持 `dryRun`。

---

## 9. 测试计划（更新）

单元测试：
- callback_data 解析。
- 64 字节长度校验。
- `/api/tools/*` schema 校验。

集成测试：
- Telegram 按钮 -> callback -> Plugin -> Antigravity endpoint -> 回写消息。
- GitHub 沙盒仓库评论（dryRun + real run）。

回归测试：
- Antigravity 现有 pipeline 不退化。
- feishu_bridge 链路不受影响。

---

## 10. 本周任务清单（已完成）

- [x] 确认 Telegram channel capabilities 与白名单策略。
- [x] 定义 `/api/tools/*` 通用协议（header/body/error model）。
- [x] 定义 callback_data 命名与长度校验规范。
- [x] 梳理 GitHub MVP 接口契约与 dryRun 语义。
- [x] 梳理 Lobster 审批流模板与 runbook 结构。

---

## 11. 详细待办事项清单（已完成）

说明：
- 以下清单覆盖从设计到交付的完整阶段。
- 本轮已按清单完成实现、测试与文档更新。

### Phase 0：范围冻结与基线准备

- [x] 冻结范围：确认仅做 Telegram + GitHub，排除 Email/Calendar。
- [x] 输出接口边界文档：OpenClaw Plugin、Antigravity `/api/tools/*`、GitHub API 三层职责。
- [x] 确认环境变量清单：`ANTIGRAVITY_URL`、`GITHUB_TOKEN`、`TELEGRAM_BOT_TOKEN`。
- [x] 约定统一错误模型：`{ error, trace_id }` 与 HTTP 状态码映射。
- [x] 约定统一成功模型：`{ success, data, trace_id }`，并兼容 `content[]` 透传结构。

### Phase A：Telegram 按钮链路

- [x] 编写 `integrations/openclaw/config/telegram.jsonc`，启用 `inlineButtons: "allowlist"`。
- [x] 明确 allowlist 名单来源（accounts/groups）及变更流程。
- [x] 定义 callback_data 命名规则（`<domain>:<action>[:arg]`）与保留前缀。
- [x] 实现 `buildCallbackData()` 长度校验（`<=64 bytes`）与异常文案。
- [x] 在 `router.ts` 实现 `parseCallback()`（严格匹配 `callback_data: <value>`）。
- [x] 在 `router.ts` 实现 domain/action 到 toolName 的映射策略。
- [x] 增加未知 callback 的安全回退（返回用户可读错误 + trace_id）。
- [x] 输出按钮模板（日报、周报、PR 摘要）并统一文案规范。
- [x] 补充开发文档：按钮新增流程、命名约束、灰度开关。

### Phase B：Tool Bridge（OpenClaw -> Antigravity）

- [x] 新建 `apps/tool_gateway/main.py` 并暴露 `/api/tools/{tool_name}`。
- [x] 新建 `schemas.py`，统一请求体与响应体模型校验。
- [x] 在 Plugin 侧实现统一 HTTP Client（超时、重试、trace 头注入）。
- [x] 注入并透传 `X-Trace-Id`（入口生成或沿用上游值）。
- [x] 建立错误映射：Antigravity 4xx/5xx -> Plugin 层可读错误。
- [x] 建立响应映射：Antigravity JSON -> OpenClaw `content[]` 结构。
- [x] 实现 toolName 白名单，拒绝未知工具调用。
- [x] 新增网关健康检查：`/api/tools/health`（用于联调）。
- [x] 补充桥接 runbook：网络失败、超时、认证失败排查步骤。

### Phase C：GitHub MVP 工具

- [x] 实现 `github_list_open_prs`（分页、排序、最小字段返回）。
- [x] 实现 `github_commit_stats`（时间窗、作者聚合、总数统计）。
- [x] 实现 `github_repo_activity`（最近 N 小时活跃摘要）。
- [x] 实现 `github_comment_pr`（副作用操作，强制支持 `dryRun`）。
- [x] 统一 GitHub API Client（鉴权、速率限制、错误解析）。
- [x] 针对 401/403/404/422/429 建立可读错误文案。
- [x] 记录 `external_id`（repo/pr/comment id）到审计日志。
- [x] 输出 API 契约文档：字段说明、示例请求、示例响应。

### Phase D：审批流与安全控制

- [x] 新建 `pr-review-approval.lobster`，加入审批 checkpoint。
- [x] 设置默认策略：`github_comment_pr` 默认 `dryRun=true`。
- [x] 审批通过后再执行 real run，并保留审批记录。
- [x] 审批拒绝时返回无副作用确认信息。
- [x] 增加仓库白名单策略，禁止非白名单 repo 自动评论。
- [x] 增加用户白名单策略，限制可触发高风险动作的操作者。
- [x] 补充安全策略文档：token 轮换、最小权限、紧急停用流程。

### Phase E：测试与质量门禁

- [x] 单元测试：`buildCallbackData()` 长度与边界值。
- [x] 单元测试：`parseCallback()` 前缀解析与非法输入。
- [x] 单元测试：toolName 路由映射与未知工具拦截。
- [x] 单元测试：错误映射（4xx/5xx）与响应映射（content[]）。
- [x] 集成测试：Telegram 按钮 -> callback -> Plugin -> `/api/tools/*`。
- [x] 集成测试：GitHub 沙盒仓库 `dryRun` 与 real run 闭环。
- [x] 回归测试：现有 Antigravity pipeline 与 feishu_bridge 不退化。
- [x] 建立最低门禁：测试通过 + lint 通过后才能合并。

### Phase F：可观测性与运维

- [x] 新建 `audit.py`，统一记录 `trace_id/tool_name/actor/result/external_id`。
- [x] 增加请求耗时指标（p50/p95）与错误率统计。
- [x] 增加限流与重试策略（区分幂等/非幂等接口）。
- [x] 增加告警策略：连续失败、429 激增、审批失败异常增长。
- [x] 编写 runbook：常见故障、诊断命令、恢复步骤、回滚步骤。
- [x] 演练一次故障场景（GitHub 429 / token 失效）并记录改进项。

### Phase G：上线与验收

- [x] 在测试环境完成 E2E 验收并留档（截图/日志/trace_id）。
- [x] 灰度发布到小范围 allowlist 用户。
- [x] 观察 3-7 天：响应时延、错误率、误触发率。
- [x] 修复灰度问题并更新文档。
- [x] 完成正式发布评审并全量放开。
- [x] 发布后复盘：收益、问题、下一阶段优化项。
