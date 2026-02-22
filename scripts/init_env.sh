#!/bin/zsh

# --- Antigravity OS 环境变量初始化 ---

# 获取项目根目录 (绝对路径)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export ANTIGRAVITY_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 1. 将原子化工具加入 Python 搜索路径
# 允许从 agents 或 core 中直接执行: from youtube_downloader import extractor
export PYTHONPATH="$ANTIGRAVITY_ROOT/skills/global_tools:$PYTHONPATH"

# 2. 将核心工具加入系统 PATH (可选)
# export PATH="$ANTIGRAVITY_ROOT/core/openClaw:$PATH"

# 3. 定义数据总线便捷访问
export OBSIDIAN_VAULT="${OBSIDIAN_VAULT:-$ANTIGRAVITY_ROOT/data/obsidian_inbox}"
export INBOX_FOLDER="${INBOX_FOLDER:-00_Inbox}"
export ANTIGRAVITY_INBOX="$OBSIDIAN_VAULT/$INBOX_FOLDER"

echo "------------------------------------------------"
echo "🚀 Antigravity Environment Loaded"
echo "ROOT: $ANTIGRAVITY_ROOT"
echo "PYTHONPATH: $PYTHONPATH"
echo "INBOX: $ANTIGRAVITY_INBOX"
echo "------------------------------------------------"
