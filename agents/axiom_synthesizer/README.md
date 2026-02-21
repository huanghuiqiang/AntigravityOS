---
name: axiom_synthesizer
description: Antigravity OS 的认知蒸馏 Agent。扫描 Obsidian Inbox 中所有高分笔记（BouncerDump/WebClip），提取碎片公理，通过 LLM 做语义去重、抽象升华和规范命名，将新公理追加到「000 认知架构地图.md」，并为每条公理创建独立笔记文件。建议每周运行一次（周日晚）。
---

# Axiom Synthesizer Agent

从信息噪音中蒸馏出可持续的认知资产，自动更新认知地图。

## 数据流

```
00_Inbox/**/*.md (BouncerDump / WebClip, score ≥ 8.0)
  ↓ 提取 [!abstract] callout 中的 axiom_extracted
  ↓
Gemini 2.0 Flash
  ↓ 语义去重 → 抽象升华 → 命名规范化 → 排序
  ↓
000 认知架构地图.md  ← 追加新 Axiom 条目
Axiom - {name}.md   ← 在 Vault 根目录创建独立笔记
  ↓
Telegram 推送合成摘要
```

## 运行

```bash
cd /Users/hugh/Desktop/Antigravity

# Dry Run（只分析，不写入，推荐首次使用）
PYTHONPATH=. python agents/axiom_synthesizer/synthesizer.py --dry-run

# 正式运行
PYTHONPATH=. python agents/axiom_synthesizer/synthesizer.py

# 只更新地图，不创建独立笔记
PYTHONPATH=. python agents/axiom_synthesizer/synthesizer.py --no-notes

# 调整采集门槛
PYTHONPATH=. python agents/axiom_synthesizer/synthesizer.py --min-score 9.0
```

## Cron 建议

在 `scripts/setup_cron.sh` 中加入（每周日 21:00）：

```bash
0 21 * * 0  cd /ROOT && PYTHONPATH=. python agents/axiom_synthesizer/synthesizer.py >> data/logs/synthesizer.log 2>&1
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GEMINI_API_KEY` | *(必填)* | OpenRouter API Key |
| `SYNTH_MIN_SCORE` | `8.0` | 最低采集分数 |
| `SYNTH_MAX_BATCH` | `30` | 单次最多提交给 LLM 的碎片数 |
| `OBSIDIAN_VAULT` | `/Users/hugh/Documents/Obsidian/AINotes` | Vault 路径 |

## 设计原则

- **只追加，不修改**：现有地图条目一律不动，幂等安全
- **去重防护**：通过标题模糊匹配跳过已存在公理
- **低风险**：`--dry-run` 可预览所有写入操作再确认执行
