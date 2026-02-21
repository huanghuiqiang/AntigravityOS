# 🦞 OpenClaw 安装与配置工作总结

> **日期**: 2026-02-13  
> **环境**: macOS (Apple Silicon) · fnm · Node v22.22.0 (arm64)

---

## 一、从 nvm 迁移到 fnm

| 操作 | 详情 |
|------|------|
| 安装 arm64 Node | `fnm install 22 --arch arm64` → v22.22.0 (arm64 原生) |
| 修改 `~/.zshrc` | 移除 nvm 3 行，替换为 `eval "$(fnm env --use-on-cd)"` |
| 清理 nvm | 已删除 `~/.nvm` 目录 |

> ⚡ 收获：终端启动速度提升（nvm ~300ms → fnm ~1ms）

---

## 二、安装并配置 OpenClaw

| 步骤 | 结果 |
|------|------|
| 安装 CLI | `npm install -g openclaw@latest` → **v2026.2.12** |
| 运行 onboard 向导 | 完成全部配置 |
| Telegram Bot | 已创建并连接（Pi 🧊） |
| LLM 模型 | 主力 **Claude Opus 4**（OpenRouter），备选 Gemini 2.5 Pro → DeepSeek |
| Skills 安装 | gemini、obsidian、github、summarize、nano-pdf、blogwatcher、model-usage、clawhub |
| Hooks 启用 | session-memory（跨会话记忆）、command-logger（命令日志） |
| Gateway Daemon | 开机自启动，后台运行 |

### 模型 Failover 策略

```
Claude Opus 4 (主力)
    ↓ 失败时自动切换
Gemini 2.5 Pro (备选)
    ↓ 失败时自动切换
DeepSeek Chat (兜底)
```

---

## 三、解决的问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| OpenClaw 安装失败 | Homebrew/fnm 是 x64 版本（Rosetta），Node 也是 x64，`node-llama-cpp` 不支持 Rosetta | `fnm install 22 --arch arm64` 安装原生 arm64 Node |
| Google Gemini API 报 429 | API Key 在 free tier，`limit: 0` | 切换到 OpenRouter，按量付费无限制 |
| obsidian-cli 找不到 | 已安装但 Pi 不知道 | 已告知 Pi 笔记库路径 |

---

## 四、产出的文件

| 文件 | 说明 |
|------|------|
| `~/Desktop/Projects/openClaw/ARCHITECTURE.md` | 架构设计文档 |
| `~/Desktop/Projects/openClaw/update-key.sh` | OpenRouter API Key 一键更新脚本 |
| `~/Desktop/Projects/openClaw/SUMMARY.md` | 本文件 |
| `~/.openclaw/openclaw.json` | OpenClaw 核心配置 |
| `~/.zshrc` | 更新后的 Shell 配置（fnm 替代 nvm） |

---

## 五、当前系统状态

```
🦞 OpenClaw v2026.2.12
├── Gateway:   ✅ 后台运行中 (ws://127.0.0.1:18789)
├── Model:     Claude Opus 4 (via OpenRouter)
├── Fallback:  Gemini 2.5 Pro → DeepSeek Chat
├── Channel:   Telegram Bot (Pi 🧊)
├── Memory:    session-memory 已启用
├── Obsidian:  /Users/hugh/Documents/Obsidian/AINotes/
└── Daemon:    launchd 开机自启
```

---

## 六、核心配置参考

### `~/.openclaw/openclaw.json` 关键字段

```jsonc
{
  "agents": {
    "defaults": {
      "model": {
        "primary": "openrouter/anthropic/claude-opus-4",
        "fallbacks": [
          "openrouter/google/gemini-2.5-pro",
          "openrouter/deepseek/deepseek-chat"
        ]
      }
    }
  },
  "env": {
    "OPENROUTER_API_KEY": "sk-or-v1-***"
  },
  "channels": {
    "telegram": { "enabled": true }
  },
  "hooks": {
    "internal": {
      "entries": {
        "session-memory": { "enabled": true },
        "command-logger": { "enabled": true }
      }
    }
  }
}
```

---

## 七、常用命令速查

### 终端命令

| 命令 | 说明 |
|------|------|
| `openclaw gateway status` | 查看 Gateway 状态 |
| `openclaw gateway restart` | 重启 Gateway |
| `openclaw dashboard` | 打开 Web 控制面板 |
| `openclaw doctor` | 诊断配置问题 |
| `openclaw tui` | 终端对话界面 |
| `openclaw update` | 更新 OpenClaw |

### Telegram 聊天命令

| 命令 | 说明 |
|------|------|
| `/status` | 查看模型、token 用量 |
| `/new` | 重置对话 |
| `/compact` | 压缩上下文 |
| `/think high` | 深度思考模式 |
| `/think low` | 快速回复模式 |
| `/model` | 查看/切换模型 |

### 工具脚本

```bash
# 更新 OpenRouter API Key
./update-key.sh sk-or-v1-新的Key
```

---

## 八、后续探索方向

- [ ] 设置定时任务（每日摘要、RSS 监控）
- [ ] 浏览器自动化（信息抓取）
- [ ] GitHub 集成（Issue/PR 管理）
- [ ] 自定义 Skills
- [ ] 深度定制 SOUL.md 和 AGENTS.md
- [ ] 远程 Gateway（部署到服务器，笔记本关机也能用）

---

*Generated: 2026-02-13 15:32*
