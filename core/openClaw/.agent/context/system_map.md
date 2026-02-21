# 🧠 Antigravity 持久化上下文：系统地图

## 1. 核心路径
- **OpenClaw 配置**: `~/.openclaw/openclaw.json`
- **Agent 工作区 (Soul/Memory)**: `~/.openclaw/workspace/`
- **项目目录 (Projects)**: `~/Desktop/Projects/`
- **自动化工具箱 (Pi-Tools)**: `~/Desktop/Projects/pi-tools/`

## 2. API 与 模型
- **Provider**: OpenRouter
- **Model Loop**: Claude Opus (Primary) -> Gemini 2.5 Pro (Fallback) -> DeepSeek (Last Resort)
- **OpenRouter Key**: 已配置在 `openclaw.json` 的 `env` 字段中。

## 3. 已安装 Skills
- [x] obsidian
- [x] github
- [x] summarize
- [x] nano-pdf
- [x] blogwatcher
- [x] model-usage
