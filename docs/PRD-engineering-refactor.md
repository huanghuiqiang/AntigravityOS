# PRD: Antigravity OS 工程成熟度重构

> **版本**: v1.0  
> **日期**: 2026-02-21  
> **目标**: 将项目从"能跑的脚本集合"提升为"可维护、可测试、可部署的工程系统"  
> **原则**: 最小破坏性重构 — 不改变任何业务逻辑，只改变代码组织方式

---

## 现状诊断

| 问题 | 严重程度 | 影响 |
|------|---------|------|
| 硬编码路径散落在 6+ 个文件中 | 🔴 高 | 不可移植、每个文件各搞一套路径，改一处必漏一处 |
| `_parse_frontmatter` 在 `bridge.py` 和 `stats.py` 各实现一遍 | 🔴 高 | 逻辑不一致，返回类型不同（tuple vs dict） |
| `telegram_notify.py` 住在 bouncer 子模块里，其他 agent 通过 `sys.path.insert` hack 引用 | 🔴 高 | 脆弱的耦合，bouncer 作为 git submodule 一旦路径变动全崩 |
| `.env` 加载逻辑散落，部分 agent 读 bouncer 的 `.env` | 🟡 中 | 配置不透明，调试困难 |
| 零测试 | 🔴 高 | 任何重构都是盲改 |
| `stats.py` 在模块加载时执行 `collect()` + `print()` | 🟡 中 | 被 import 时产生副作用 |
| `import requests` 在函数中间位置零散出现 | 🟢 低 | 代码可读性差 |

---

## 重构计划（6 个 Phase）

### Phase 1: 统一配置中心 `antigravity/config.py`

**目标**：一处定义，全局引用。消灭所有硬编码路径。

**产出文件**: `antigravity/config.py`

```
所有当前散落的配置收拢为：
- VAULT_PATH         ← 消灭 6 处 "/Users/hugh/..." 硬编码
- INBOX_FOLDER       ← 消灭 3 处 "00_Inbox" 重复
- PROJECT_ROOT       ← 自动检测
- LOG_DIR            ← 统一日志目录
- OPENROUTER_API_KEY ← 统一 API Key 读取
- TELEGRAM_BOT_TOKEN ← 统一 TG 配置
- TELEGRAM_CHAT_ID
- MODELS (dict)      ← bouncer / synthesizer 使用的模型名
```

**原则**: 用 `pydantic-settings` + `.env` 文件，支持环境变量覆盖。

**涉及修改**:
- `skills/obsidian_bridge/bridge.py` — 删除 `DEFAULT_VAULT` 常量，改用 `config.VAULT_PATH`
- `scripts/stats.py` — 删除 `VAULT = Path(...)` 硬编码
- `agents/cognitive_bouncer/bouncer.py` — 删除 `ANTIGRAVITY_INBOX` 硬编码
- `agents/axiom_synthesizer/synthesizer.py` — 删除路径和 API key 硬编码
- `agents/knowledge_auditor/auditor.py` — 删除 `VAULT = get_vault()` 模块级调用
- `agents/daily_briefing/daily_briefing.py` — 无需改动（已间接调用）

---

### Phase 2: 抽取共享基础设施 `antigravity/notify.py` + `antigravity/frontmatter.py`

**目标**：消灭 `sys.path.insert` hack，消灭重复实现。

#### 2a: `antigravity/notify.py`
将 `agents/cognitive_bouncer/telegram_notify.py` 的核心 `send_message()` 函数提升为项目级共享模块。

**涉及修改**:
- `agents/cognitive_bouncer/bouncer.py` — `from antigravity.notify import send_message`
- `agents/axiom_synthesizer/synthesizer.py` — 删除 `sys.path.insert(bouncer_dir)` hack
- `agents/inbox_processor/inbox_processor.py` — 同上
- `agents/knowledge_auditor/auditor.py` — 同上
- `agents/daily_briefing/daily_briefing.py` — 同上

#### 2b: `antigravity/frontmatter.py`
统一 `_parse_frontmatter` 实现。当前两个版本：
- `bridge.py`: 返回 `(dict, str)` ← 正确
- `stats.py`: 返回 `dict` ← 信息丢失

**决策**: 保留 `bridge.py` 版本（tuple），`stats.py` 改为 import 共享版。

---

### Phase 3: 包结构化 — 引入 `antigravity/` 顶层包

**目标**：正式的 Python 包结构，`pip install -e .` 可用，告别 `PYTHONPATH=.`

**新目录结构**:
```
Antigravity/
├── pyproject.toml              ← 新增：包管理 + 依赖声明
├── antigravity/                ← 新增：核心共享包
│   ├── __init__.py
│   ├── config.py               ← Phase 1 产出
│   ├── notify.py               ← Phase 2a 产出
│   └── frontmatter.py          ← Phase 2b 产出
├── agents/                     ← 不动
├── skills/                     ← 不动
├── scripts/                    ← 不动
└── ...
```

**`pyproject.toml` 关键内容**:
```toml
[project]
name = "antigravity-os"
version = "2026.2"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "python-dotenv>=1.0",
    "httpx>=0.24",
    "requests>=2.28",
    "feedparser>=6.0",
    "beautifulsoup4>=4.12",
    "pyyaml>=6.0",
    "rich>=13.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov"]
```

---

### Phase 4: 消除反模式

| 反模式 | 位置 | 修复 |
|--------|------|------|
| `stats.py` 底部的 `collect()` | `scripts/stats.py:255` | 移到 `if __name__ == "__main__"` 中 |
| 顶层 `print("Starting script...")` | `scripts/stats.py:6` | 删除 |
| `import requests` / `import re` 散落在函数中间 | `bouncer.py:62,132` | 移至文件顶部 |
| `load_dotenv()` 在 `evaluate_article` 函数内每次调用 | `bouncer.py:67` | 移到模块顶层 |
| `__import__('datetime')` 内联 hack | `bouncer.py:153` | 用已导入的 `datetime` |
| Bouncer 使用 `requests` + `httpx` 两个 HTTP 库 | `bouncer.py` | 统一为 `httpx` |

---

### Phase 5: 基础测试框架

**目标**：覆盖 3 个核心纯函数，建立测试习惯。

**测试文件**:
```
tests/
├── conftest.py                   ← 共享 fixture（mock vault, mock env）
├── test_config.py                ← 配置加载单元测试
├── test_frontmatter.py           ← frontmatter 解析边界条件
└── test_notify.py                ← Telegram 消息格式化（mock HTTP）
```

**覆盖目标**:
- `antigravity/frontmatter.py` → 正常 YAML / 无 frontmatter / 损坏 YAML
- `antigravity/config.py` → 环境变量覆盖 / 无 `.env` 降级
- `antigravity/notify.py` → 消息格式化正确性（不发真实请求）

---

### Phase 6: 清理 & 文档更新

- 更新 `README.md` 中的安装说明（`pip install -e .` 替代 `PYTHONPATH=.`）  
- 更新 `setup_cron.sh` 中的 Python 调用方式  
- 删除所有 `sys.path.insert(0, ...)` hack  
- 更新 `AGENT_GUIDE.md`

---

## 执行顺序与依赖关系

```
Phase 1 (config.py)
    ↓
Phase 2 (notify.py + frontmatter.py)  ← 依赖 Phase 1
    ↓
Phase 3 (pyproject.toml + pip install -e .)  ← 依赖 Phase 1-2
    ↓
Phase 4 (反模式清理)  ← 可与 Phase 3 并行
    ↓
Phase 5 (测试)  ← 依赖 Phase 1-3
    ↓
Phase 6 (文档清理)  ← 最后执行
```

---

## 风险控制

1. **每个 Phase 完成后立即 `git commit`**，确保可回滚
2. **Phase 3 完成后运行 `python -m agents.daily_briefing.daily_briefing --mock`** 验证模块导入链路
3. **不改变任何业务逻辑**，只改变代码的组织方式和导入路径

---

## 不在本次范围内

- ❌ asyncio 并发改造（属于性能优化，不是工程基础）
- ❌ SQLite / DuckDB 状态存储（属于架构升级）
- ❌ Embedding 向量去重（属于新功能）
- ❌ Web Dashboard V2（属于产品迭代）

> 这些都是"正确的事"，但现在最紧急的是"把地基打好"。
