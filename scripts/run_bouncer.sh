#!/bin/zsh

# 加载环境
SOURCE_SCRIPT="$(dirname "$0")/init_env.sh"
if [ -f "$SOURCE_SCRIPT" ]; then
    source "$SOURCE_SCRIPT"
else
    echo "❌ Error: init_env.sh not found"
    exit 1
fi

# 切换到 Bouncer 目录并执行
cd "$ANTIGRAVITY_ROOT/agents/cognitive_bouncer"
echo "🛡️ Starting Cognitive Bouncer..."
python3 bouncer.py
