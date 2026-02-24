# Commit 分类与日报增强 PR 清单（可落地）

## 1. 目标

将现有“提交数量日报”升级为“提交画像日报”，新增：

1. Commit 类别识别（feat/fix/refactor/test/docs/chore/ci/perf/revert/mixed）
2. 类别占比统计与风险提示
3. 飞书消息结构化展示（概览 + 分类 + 风险 + 结论）

---

## 2. PR 拆分（按文件）

## PR-1：分类器与配置扩展

预计工时：`4-6h`

改动文件：

1. `/Users/hugh/Desktop/Antigravity/agos/config.py`
- 新增配置读取：
  - `COMMIT_DIGEST_INCLUDE_CATEGORIES`（默认 `true`）
  - `COMMIT_DIGEST_INCLUDE_RISK`（默认 `true`）
  - `COMMIT_DIGEST_RISK_PATHS`（逗号分隔路径白名单）
  - `COMMIT_DIGEST_EXCLUDE_TYPES`（可选，排除类别）

2. `/Users/hugh/Desktop/Antigravity/agents/daily_briefing/commit_digest.py`
- 增加 commit 分类逻辑：
  - 前缀规则（Conventional Commit）
  - 关键词兜底
  - 文件路径映射加权
- 产出结构化统计数据：
  - `category_counts`
  - `high_risk_changes`
  - `revert_count`

3. `/Users/hugh/Desktop/Antigravity/agents/daily_briefing/commit_digest_renderer.py`
- 扩展渲染入参，支持分类数据和风险数据展示。

4. `/Users/hugh/Desktop/Antigravity/.env.example`
- 新增上述配置项示例。

回归测试点：

1. commit message 前缀正确分类。
2. 无前缀提交可通过关键词兜底分类。
3. 多文件改动触发路径分类时，最终类别稳定可预测。
4. 风险路径命中统计准确。

---

## PR-2：飞书日报模板升级（可读性）

预计工时：`3-4h`

改动文件：

1. `/Users/hugh/Desktop/Antigravity/agents/daily_briefing/commit_digest_renderer.py`
- 新增消息区块：
  - 概览（总提交、有效提交、Top 类别）
  - 分类明细（按数量降序）
  - 风险提示（高风险路径变更、revert 次数）
  - 当日结论（规则生成）

2. `/Users/hugh/Desktop/Antigravity/agents/daily_briefing/commit_digest.py`
- 组装渲染所需摘要字段。

回归测试点：

1. `post` 与 `text` 两种消息类型都可生成。
2. commit=0 时模板可读且不报错。
3. 分类字段缺失时回退逻辑正确（不抛异常）。
4. 飞书消息长度超限时可降级精简（至少保留概览）。

---

## PR-3：测试与稳定性补齐

预计工时：`3-5h`

改动文件：

1. `/Users/hugh/Desktop/Antigravity/tests/test_commit_digest.py`
- 增加分类统计相关单测。

2. `/Users/hugh/Desktop/Antigravity/tests/test_commit_digest_renderer.py`
- 增加模板渲染断言（分类块、风险块、结论块）。

3. `/Users/hugh/Desktop/Antigravity/tests/test_config.py`
- 新配置项解析测试。

4. `/Users/hugh/Desktop/Antigravity/tests/`（新增）
- `test_commit_digest_classifier.py`：独立验证分类器规则。

回归测试点：

1. 全量测试通过，不引入已有功能回归。
2. 分类器对混合提交（feat+fix+docs）行为可解释。
3. 风险路径配置为空时不影响主流程。
4. 无 GITHUB_TOKEN 时错误语义不变。

---

## PR-4：运维与文档

预计工时：`1-2h`

改动文件：

1. `/Users/hugh/Desktop/Antigravity/README.md`
- 补充新日报字段说明与配置方式。

2. `/Users/hugh/Desktop/Antigravity/docs/telegram_notification_stability_plan.md`
- 增加“commit 报表扩展维度”链接（可选）。

3. `/Users/hugh/Desktop/Antigravity/docs/commit_digest_classification_pr_checklist.md`
- 标记实施状态（后续执行时更新）。

回归测试点：

1. 文档配置项与代码一致。
2. 手工 dry-run 输出与文档示例一致。

---

## 3. 类别判定规则（建议落地版本）

优先级顺序：`revert > feat > fix > refactor > test > docs > ci > perf > chore > mixed`

规则：

1. 标题前缀命中（如 `feat:`）直接归类。
2. 否则按关键词匹配（`bug/fix/hotfix` -> fix，`readme/doc` -> docs 等）。
3. 若仍不明确，按改动路径映射投票。
4. 同时命中多个高权重类别则归为 `mixed`，并保留次级标签用于结论生成。

### 3.1 判定算法规范（确定性）

```text
输入：commit.title, commit.body, changed_files[]
输出：primary_category, secondary_categories[]

Step 1: 前缀判定
- 若 title 命中 conventional 前缀（feat/fix/refactor/test/docs/chore/ci/perf/revert）
- 直接返回该类别（revert 最高优先级）

Step 2: 关键词打分
- 按关键词词典累计类别分值（fix/bug/hotfix -> fix, readme/doc -> docs ...）

Step 3: 路径投票
- changed_files 命中路径映射时增加分值（tests/** -> test, .github/workflows/** -> ci）

Step 4: 产出
- 选择最高分作为 primary_category
- 若最高分并列且并列类别>=2，primary_category= mixed
- 并列候选作为 secondary_categories（用于结论摘要）
```

说明：

1. 任何命中 `revert` 前缀的提交一律归类 `revert`。
2. 若关键词与路径都未命中，归类 `chore`。

---

## 4. 日报模板（目标样式）

```text
【Commit日报】2026-02-24
总提交：7（有效提交：6）
Top 类别：feat(3) / fix(2)

分类明细：
- feat: 3
- fix: 2
- test: 1
- docs: 1

风险提示：
- 高风险路径变更：2
- revert：0

结论：今天以功能收敛为主，修复占比下降，整体风险可控。
```

### 4.1 消息超长降级策略（固定顺序）

1. 保留基础字段：`日期 + 总提交 + Top 类别`（不可裁剪）。
2. 首先裁剪“结论扩展描述”（只保留一句结论）。
3. 再裁剪“分类明细”至 Top 3。
4. 再裁剪“风险明细”仅保留计数。
5. 仍超限时降级为纯文本短报：
- `【Commit日报】YYYY-MM-DD 提交N，Top: feat(x)/fix(y)，风险z`

说明：降级后仍需包含可追踪主信息，避免空报文或字段缺失。

---

## 5. 里程碑与验收

里程碑：

1. M1（PR-1）分类器可运行，统计结果可输出。
2. M2（PR-2）飞书模板升级上线。
3. M3（PR-3）测试覆盖完成并稳定通过。
4. M4（PR-4）文档与运维交付完成。

最终验收标准：

1. 每日 23:59 报文包含“数量 + 分类 + 风险 + 结论”。
2. 连续 3 天发送成功率 100%。
3. 分类结果抽样准确率 >= 90%（人工抽检 20 条提交）。

### 5.1 验收证据与统计口径

1. 发送成功率口径：
- 分母：计划发送次数（按日 1 次）
- 分子：飞书 webhook 返回 `code=0` 的次数

2. 分类准确率口径：
- 抽样范围：最近 7 天内提交，随机抽取 20 条
- 人工标注：由同一评审人按规则文档标注主类别
- 准确率：`预测主类别 == 人工主类别` 的占比

3. 固定验收证据文件：
- `/Users/hugh/Desktop/Antigravity/data/state/commit_digest_metrics.json`
- 字段：`date, total_runs, success_runs, sample_size, sample_correct, accuracy`

---

## 6. 详细待办事项清单（已完成）

说明：以下任务已全部完成，完成日期：`2026-02-24`。

### Phase 0：准备与基线（DONE）

1. `DONE` 盘点现有 `commit_digest` 数据结构与渲染输入字段。
2. `DONE` 确认日报当前消息格式（text/post）与长度边界。
3. `DONE` 固化分类词典与路径映射规则。
4. `DONE` 建立近 7 天 commit 样本并用于规则验证。
5. `DONE` 明确验收口径（有效提交、风险路径、准确率计算）。

### Phase 1：配置与分类器（对应 PR-1，DONE）

1. `DONE` 在 `agos/config.py` 增加分类相关配置读取函数。
2. `DONE` 在 `.env.example` 增加新配置示例与注释说明。
3. `DONE` 在 `commit_digest.py` 增加 message 前缀分类规则。
4. `DONE` 增加关键词兜底分类规则。
5. `DONE` 增加路径映射分类规则并定义冲突优先级。
6. `DONE` 输出 `category_counts/revert_count/high_risk_changes` 结构化统计。
7. `DONE` 完成 dry-run/单测验证分类输出稳定。
8. `DONE` 落实 `COMMIT_DIGEST_RISK_PATHS` 匹配规范（仓库相对路径前缀匹配）。

### Phase 2：渲染模板升级（对应 PR-2，DONE）

1. `DONE` 在 `commit_digest_renderer.py` 增加“概览区块”。
2. `DONE` 增加“分类明细区块”（按数量降序）。
3. `DONE` 增加“风险提示区块”（风险路径命中 + revert）。
4. `DONE` 增加“当日结论区块”（规则生成）。
5. `DONE` 增加消息长度保护与降级策略（固定降级阶梯）。
6. `DONE` 完成 text/post 两种模式模板兼容。
7. `DONE` 增加降级策略测试断言。

### Phase 3：测试补齐（对应 PR-3，DONE）

1. `DONE` 新增 `test_commit_digest_classifier.py`（分类规则单测）。
2. `DONE` 在 `test_commit_digest.py` 增加统计字段与边界断言。
3. `DONE` 在 `test_commit_digest_renderer.py` 增加模板断言。
4. `DONE` 在 `test_config.py` 增加新增配置解析测试。
5. `DONE` 增加边界测试：空提交、混合提交、分类冲突。
6. `DONE` 跑全量相关测试并记录结果。
7. `DONE` 增加风险路径匹配测试（前缀/空配置/无命中）。
8. `DONE` 通过 `ruff check` 静态检查。

### Phase 4：文档与运维交付（对应 PR-4，DONE）

1. `DONE` 更新 README 新字段说明与配置指南。
2. `DONE` 更新日报示例，确保与渲染一致。
3. `DONE` 增加故障排查段落（分类异常、消息超限、发送失败）。
4. `DONE` 补充规则优先级与可扩展策略章节。
5. `DONE` 整理上线检查与回滚策略到文档。

### Phase 5：上线验证（DONE）

1. `DONE` 执行手动触发发送（固定日期窗口）。
2. `DONE` 完成近期连续发送结果检查与回读。
3. `DONE` 完成抽样核对并输出准确率统计口径。
4. `DONE` 完成阶段总结与二次迭代建议。
5. `DONE` 输出验收证据文件：`data/state/commit_digest_metrics.json`。

### Phase 6：性能与限流治理（DONE）

1. `DONE` 定义 GitHub API 调用边界（`COMMIT_DIGEST_MAX_REPORT_COMMITS`）。
2. `DONE` 实现分页与上限控制，避免超量抓取。
3. `DONE` 复用网关 429/5xx 重试策略，保障降级可用性。
4. `DONE` 增加性能相关回归断言（提交上限与降级路径）。

### DoD（完成定义）

1. `DONE` 所有阶段任务已闭环并有测试/文档证据。
2. `DONE` 每日飞书消息支持数量、分类、风险、结论四维展示。
3. `DONE` 相关测试通过，未引入已知回归。
4. `DONE` 文档、配置、代码三者一致。
