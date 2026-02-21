---
name: pdf_ingester
description: PDF 摄入工具。接受本地 PDF 路径或远程 PDF URL，用 pdfplumber 提取正文，调用 Bouncer LLM 评分，高分写入 Obsidian Inbox（status: pending），推送 Telegram 通知。激活条件：用户提供 .pdf 文件路径或 arxiv/PDF URL 并要求评分入库。
---

# PDF Ingester

## 使用方法

```bash
# 本地 PDF
PYTHONPATH=/Users/hugh/Desktop/Antigravity \
  python skills/global_tools/pdf_ingester/pdf_ingester.py ~/Downloads/paper.pdf

# 远程 PDF URL（自动下载）
python skills/global_tools/pdf_ingester/pdf_ingester.py \
  "https://arxiv.org/pdf/2303.08774.pdf"

# 降低门槛 + 静默模式
python skills/global_tools/pdf_ingester/pdf_ingester.py paper.pdf \
  --min-score 7.0 --silent
```

## Python API

```python
from skills.global_tools.pdf_ingester.pdf_ingester import ingest_pdf

result = ingest_pdf("/path/to/paper.pdf")
# 返回：{"source", "title", "score", "reason", "axiom", "written", "filepath", "pages"}
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GEMINI_API_KEY` | *(必填)* | OpenRouter API Key |
| `PDF_MIN_SCORE` | `8.0` | 入库分数门槛 |
| `OBSIDIAN_VAULT` | `/Users/hugh/Documents/Obsidian/AINotes` | Vault 路径 |
