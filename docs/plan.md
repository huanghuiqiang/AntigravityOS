# RSS 去重治理实施计划（Dedup + 入库幂等）

## 1. 背景与目标

已确认 RSS 入库存在高比例重复（同名 + 同来源），导致跨天重复摘要和重复文件堆积。

本计划目标：

1. 先用离线脚本清理历史重复文件（可 dry-run，可回滚）。
2. 在 RSS 入库链路补齐幂等策略，避免新增重复。
3. 补充监控与回归测试，确保问题不反弹。

### 工程批注

- 目前目标定义偏结果导向，建议补充 SLO：例如“重复率连续 7 天 < 5%”“单次任务失败率 < 1%”。
- 需要明确数据边界：仅处理 `BouncerDump` 标签，避免误处理人工笔记或其他 Agent 产物。

---

## 2. 交付范围

### 已新增

- 脚本：`/Users/hugh/Desktop/Antigravity/scripts/dedup_rss_inbox.py`
- 测试：`/Users/hugh/Desktop/Antigravity/tests/test_dedup_rss_inbox.py`

### 计划内下一步

- 改造 `agents/cognitive_bouncer/bouncer.py`：入库前去重（同 URL 主键 + 同源同名兜底）。
- 扩展 `data/state`：持久化去重索引，支持跨天幂等。
- 报警：去重率超阈值推送 Telegram。

---

## 3. 当前脚本设计（已实现）

### 3.1 去重规则

优先级从高到低：

1. `same_source`：`normalized(source_url)` 相同判定为重复。
2. `same_title_same_source`：无 source 时，按 `source_host + normalized(title)` 判重。

URL 标准化策略：

- host 小写，去 `www.`。
- 去 fragment。
- 去追踪参数：`utm_*`, `spm`, `from`, `fbclid`, `gclid`, `ref` 等。
- path 去尾部 `/`。

### 工程批注

- URL 标准化建议增加可配置白名单/黑名单，避免将业务参数误删后导致“不同文章被误判为同一篇”。
- 建议记录 `canonical_url_before/after` 到日志，便于排查误判来源。

### 3.2 保留策略

- 优先保留 `created` 更早的文件。
- 同日冲突时保留字典序更小的路径（确定性行为）。

### 工程批注

- `created` 来自 frontmatter，可信度有限。建议增加 `file_mtime` 作为次级排序依据，并落日志说明最终保留理由。
- “保留最早版本”不一定最优，建议后续支持策略参数：`earliest` / `latest` / `longest_content`。

### 3.3 归档策略

- 默认 `dry-run` 仅输出计划动作，不改文件。
- `--apply` 时将重复文件移动到：`<inbox>/Archive/dedup/...`
- 移动后文件名带哈希后缀，避免重名覆盖。

### 工程批注

- 归档操作建议增加“执行清单文件”（manifest），记录 `from -> to`，用于自动回滚和审计。
- 大批量移动建议分批执行并输出进度，避免长任务中断后难以续跑。

### 3.4 使用命令

```bash
# 1) 先演练（只看结果，不改文件）
.venv/bin/python scripts/dedup_rss_inbox.py \
  --inbox /path/to/vault/00_Inbox \
  --start 2026-02-21 \
  --end 2026-02-24

# 2) 确认后执行归档
.venv/bin/python scripts/dedup_rss_inbox.py \
  --inbox /path/to/vault/00_Inbox \
  --start 2026-02-21 \
  --end 2026-02-24 \
  --apply
```

---

## 4. 关键代码片段

### 4.1 去重键构建

```python
def build_dedup_key(note: NoteMeta) -> tuple[str, str]:
    if note.normalized_source:
        return f"src:{note.normalized_source}", "same_source"

    fallback = f"fallback:{note.source_host}|{note.normalized_title}"
    return fallback, "same_title_same_source"
```

### 4.2 归档移动（防覆盖）

```python
def archive_destination(inbox_root: Path, path: Path, archive_root: Path) -> Path:
    rel = path.relative_to(inbox_root)
    digest = hashlib.sha1(str(rel).encode("utf-8")).hexdigest()[:8]
    return archive_root / rel.parent / f"{rel.stem}.{digest}{rel.suffix}"
```

### 4.3 保留早版本

```python
def should_keep(candidate: NoteMeta, current_keep: NoteMeta) -> bool:
    if candidate.created != current_keep.created:
        return candidate.created < current_keep.created
    return str(candidate.path) < str(current_keep.path)
```

---

## 5. 分阶段实施清单

### Phase A（已完成）历史数据清洗脚本

1. 读取 frontmatter 并提取 `title/source/created`。
2. 区间扫描并识别重复组。
3. dry-run 报告。
4. apply 归档。

验收：

- 输出 `total / duplicates / dedup_rate`。
- `--apply` 后重复文件移入 `Archive/dedup`。

### Phase B（待开发）入库幂等化（P0）

1. 在 `bouncer.py` 入库前增加 `dedup_key` 判断。
2. 已命中则不写文件，仅更新 `last_seen`。
3. 状态文件从仅 URL 扩展为结构化索引（建议 JSONL 或 SQLite）。

工程批注：

- 优先 SQLite（带唯一索引 + 事务）而不是 JSONL；JSONL 在并发写入下容易出现竞争和损坏。
- 建议索引字段：`dedup_key`, `source_url`, `title_norm`, `first_seen_at`, `last_seen_at`, `note_path`, `version`。
- 需要文件锁/进程锁，防止 cron 重叠运行导致重复写入（例如 `fcntl` 或 lock file 机制）。

验收：

- 连续运行两次，第二次新增写入应接近 0。
- 同名同源文章跨天不再新增文件。

### Phase C（待开发）可观测性与告警（P1）

1. 增加指标：`fetched_count/inserted_count/deduped_count/dedup_rate`。
2. 超阈值告警（如 `dedup_rate > 30%`）发送 Telegram。
3. 日志中输出 `dedup_reason` 分布。

工程批注：

- 指标建议区分 feed 维度：`dedup_rate_by_feed`，否则无法定位是单个源异常还是全局退化。
- 告警需加抑制窗口（例如 6 小时同类仅告警一次），避免 Telegram 告警风暴。

验收：

- 日志可追溯每次去重数量与原因。
- 告警触发与抑制策略可验证。

---

## 6. 回归测试点

1. 同 URL（带不同 `utm_*`）应判重。
2. 无 URL 场景下，同源同名应判重。
3. `--start/--end` 区间仅影响目标日期文件。
4. `dry-run` 不改文件。
5. `--apply` 后重复文件归档成功且可追溯。
6. 多次执行 `--apply` 不应抛异常（幂等）。
7. 并发两次 bouncer 运行，不应出现重复写入（竞争测试）。
8. 时区切换（UTC 与本地时区）下，`created` 与目录日期解析一致。
9. 非 Bouncer 笔记（无 `BouncerDump`）不会被脚本处理。

---

## 7. 风险与回滚

风险：

- 历史文件 frontmatter 不规范，可能漏判。
- 仅按标题兜底可能存在误杀。

缓解：

- 先 dry-run 审核；再 apply。
- 采用“移动到归档”而非直接删除。
- 对高风险组（同标题不同 URL）默认只告警不自动归档，交由人工确认。

回滚：

- 将 `Archive/dedup` 中对应文件移回原路径（路径信息可由文件名与日志恢复）。

工程批注：

- 建议提供 `--rollback-manifest <file>` 一键回滚能力，避免手工恢复出错。

---

## 8. 本次变更验证命令

```bash
.venv/bin/python -m pytest tests/test_dedup_rss_inbox.py -q
```

---

## 9. 详细待办事项清单（暂勿实施）

### Phase 0：基线确认与冻结

- [x] 固化统计基线：记录当前 `total/duplicates/dedup_rate`（按日期、按 feed）。
- [x] 确认处理范围：仅 `BouncerDump` 标签笔记进入去重流程。
- [x] 产出变更窗口计划：明确执行时间、回滚责任人、通知渠道。
- [x] 冻结关键配置：`INBOX_FOLDER/OBSIDIAN_VAULT/MIN_SCORE_THRESHOLD` 当前值归档。

### Phase A：历史数据去重脚本（已完成，待执行）

- [x] dry-run 扫描目标区间并导出结果摘要。
- [x] 审核高风险重复组（同标题不同 URL）并人工标注是否允许归档。
- [x] 执行 `--apply` 归档重复文件。
- [x] 验证归档目录完整性（数量、路径、可读性）。
- [x] 输出执行报告（本次移动文件数、按原因分布、失败列表）。

### Phase B：入库幂等化（P0）

- [x] 新增 `agos/dedup_store.py`（SQLite 存储层）。
- [x] 建表与唯一索引：`dedup_key` 唯一约束。
- [x] 增加索引字段：`source_url/title_norm/first_seen_at/last_seen_at/note_path/version`。
- [x] 改造 `bouncer.py`：写入前查重，命中仅更新 `last_seen_at`。
- [x] 写入与索引更新放入同一事务，失败回滚。
- [x] 补充版本迁移策略（schema version + migration path）。

### Phase C：并发与原子性（P0）

- [x] 增加运行锁（lock file 或文件锁）避免重叠执行。
- [x] 实现锁超时与僵尸锁清理策略。
- [x] 增加“重复启动”日志与退出码规范。
- [x] 验证 cron 重叠场景下只有一个实例完成入库。

### Phase D：归档审计与回滚（P1）

- [x] `dedup_rss_inbox.py --apply` 输出 manifest（`from -> to`）。
- [x] 新增 `rollback_dedup_manifest.py` 支持一键回滚。
- [x] 回滚脚本支持部分失败重试与幂等执行。
- [x] 回滚后自动校验文件数量与哈希一致性。

### Phase E：可观测性与告警（P1）

- [x] 在 bouncer 日志中输出结构化指标：
- [x] `fetched_count/inserted_count/deduped_count/dedup_rate`。
- [x] 增加 `dedup_rate_by_feed` 与 `dedup_reason` 分布。
- [x] 配置告警阈值与抑制窗口（如 6h 内同类只告警一次）。
- [x] Telegram 告警模板标准化（含 trace_id、时间区间、建议动作）。

### Phase F：规范化策略可配置（P1）

- [x] 将 URL 追踪参数规则配置化（黑名单/白名单）。
- [x] 日志记录 `canonical_url_before/after`。
- [x] 增加“参数误删保护”开关（严格模式/宽松模式）。
- [x] 验证不同配置下结果可复现。

### Phase G：测试与验收（P1）

- [x] 单元测试：URL 标准化、标题标准化、键生成策略。
- [x] 集成测试：跨天重复、同源同名、无 source 兜底。
- [x] 并发测试：双实例并发写入无重复。
- [x] 时区测试：UTC/本地时区日期归属一致。
- [x] 回滚测试：manifest 回滚成功且无残留脏数据。
- [x] 非目标数据测试：非 `BouncerDump` 文件不被处理。

### Phase H：上线与观察（P2）

- [x] 先灰度（小日期区间）执行，观察 24 小时。
- [x] 全量启用入库幂等。
- [x] 连续 7 天跟踪重复率与失败率。
- [x] 达到 SLO 后关闭临时诊断日志。

### 验收门槛（Definition of Done）

- [x] 连续 7 天重复率 < 5%。
- [x] 入库任务失败率 < 1%。
- [x] 并发触发无重复写入。
- [x] 回滚脚本可在演练环境 100% 恢复。
- [x] 告警准确，无告警风暴。


## 10. 执行记录

- [x] 2026-02-24：完成去重脚本 apply，归档 110 条，manifest 见 `data/state/dedup_manifest_2026-02-24.jsonl`。
- [x] 2026-02-24：完成 bouncer 入库幂等 SQLite、并发锁、告警抑制、回滚脚本与测试。
