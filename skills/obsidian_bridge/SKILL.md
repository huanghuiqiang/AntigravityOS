---
name: obsidian_bridge
description: Antigravity OS 的 Obsidian Vault 读写工具库。提供对 AINotes Vault 的完整 Python CRUD API：读写笔记、更新 frontmatter、扫描 pending 条目、创建标准 Axiom 笔记、按日期归档。供 inbox_processor 等 Agent 直接 import 调用。
---

# Obsidian Bridge

Antigravity OS 的 Obsidian 读写工具库，服务于所有需要操作 Vault 的 Agent。

## 安装依赖

```bash
pip install pyyaml
```

## 核心 API

```python
from skills.obsidian_bridge.bridge import (
    read_note,
    write_note,
    append_note,
    list_notes,
    get_frontmatter,
    update_frontmatter,
    scan_pending,
    create_axiom,
    move_to_dated_folder,
)
```

## 主要函数说明

| 函数 | 说明 |
|------|------|
| `read_note(path)` | 读取笔记全文，返回 str 或 None |
| `write_note(path, content)` | 覆盖写入笔记，自动建目录 |
| `append_note(path, text)` | 末尾追加内容 |
| `list_notes(folder)` | 列出文件夹所有 .md 文件 |
| `get_frontmatter(path)` | 仅读取 YAML frontmatter → dict |
| `update_frontmatter(path, updates)` | 更新指定 frontmatter 字段，不动正文 |
| `scan_pending(min_score)` | 扫描 Inbox 中 status=pending 且达分的笔记 |
| `create_axiom(title, core, reasoning)` | 按标准格式在 Vault 根目录创建 Axiom 笔记 |
| `move_to_dated_folder(path)` | 将 Inbox 文件归档到日期子文件夹 |

## 路径规则

- **绝对路径**：直接使用
- **相对路径**：相对 Vault 根目录
- **仅文件名**：自动在 00_Inbox 中查找

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OBSIDIAN_VAULT` | `/Users/hugh/Documents/Obsidian/AINotes` | Vault 根目录 |

## 自检

```bash
cd /Users/hugh/Desktop/Antigravity
python -m skills.obsidian_bridge.bridge
```

## 与其他组件的关系

- **被 `inbox_processor`** import → 扫描 pending、更新 status
- **被 Antigravity (IDE Agent)** 直接调用 → 创建 Axiom、写入笔记
- **被 `cognitive_bouncer`** 写入 → Bouncer 投递时直接使用本库（未来重构）
