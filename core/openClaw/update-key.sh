#!/bin/bash
# 更新 OpenClaw 的 OpenRouter API Key
# 用法: ./update-key.sh <新的API_KEY>

CONFIG="$HOME/.openclaw/openclaw.json"

if [ -z "$1" ]; then
  echo "❌ 请提供新的 API Key"
  echo "用法: ./update-key.sh sk-or-v1-xxxxxxxx"
  exit 1
fi

NEW_KEY="$1"

# 用 sed 替换 key（macOS 兼容）
sed -i '' "s|\"OPENROUTER_API_KEY\": \"sk-or-v1-[^\"]*\"|\"OPENROUTER_API_KEY\": \"$NEW_KEY\"|" "$CONFIG"

echo "✅ API Key 已更新"

# 重启 Gateway
eval "$(fnm env)" && openclaw gateway restart

echo "🦞 Gateway 已重启，新 Key 生效"
