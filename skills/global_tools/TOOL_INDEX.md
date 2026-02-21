# 🗺️ Global Agent Tools Index

此目录包含所有可供 Agent 跨项目调用的核心技能。

## 🛠️ 可用工具列表

### 1. YouTube 字幕提取器 (youtube_downloader)
- **描述**: 输入 YouTube URL，自动下载并解析为 `.txt` 或 `.srt`。
- **路径**: `skills/global_tools/youtube_downloader/extractor.py`
- **使用说明**: 详见 `skills/global_tools/youtube_downloader/README.md`

### 2. Obsidian Bridge (obsidian_bridge) ✅ NEW
- **描述**: Obsidian Vault CRUD API。读写笔记、更新 frontmatter、扫描 pending 条目、创建 Axiom。
- **路径**: `skills/obsidian_bridge/bridge.py`
- **核心函数**: `scan_pending()`, `read_note()`, `write_note()`, `update_frontmatter()`, `create_axiom()`
- **使用说明**: 详见 `skills/obsidian_bridge/SKILL.md`

### 3. NotebookLM (notebooklm)
- **描述**: Google NotebookLM 完整 API——创建 notebook、添加 sources、生成 Report/Podcast/Quiz。
- **路径**: `skills/notebooklm/SKILL.md`
- **调用方式**: CLI 命令 `notebooklm <subcommand>`

### 4. (计划中)
- PDF 解析器 (`pdf_ingester`)
- Web 剪报 (`web_clipper`) — 接受 URL 即时评分入库，不等 cron

---
## 💡 如何调用？

```python
# obsidian_bridge（推荐方式）
import sys; sys.path.insert(0, "/Users/hugh/Desktop/Antigravity")
from skills.obsidian_bridge.bridge import scan_pending, write_note

# youtube_downloader
python3 skills/global_tools/youtube_downloader/extractor.py "<URL>"
```

---
## 📐 设计原则
- **无状态**：每个 skill 是纯函数/工具，不保存运行时状态
- **可独立测试**：每个 skill 有自己的 `__main__` 自检
- **共享路径**：通过环境变量 `ANTIGRAVITY_ROOT` / `OBSIDIAN_VAULT` 解耦硬编码
