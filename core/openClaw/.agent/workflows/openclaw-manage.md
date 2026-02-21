---
description: OpenClaw Gateway 管理（启动、重启、状态检查）
---

// turbo-all

## 检查 Gateway 状态

1. 检查 Gateway 运行状态
```bash
eval "$(fnm env)" && openclaw gateway status
```

2. 运行诊断
```bash
eval "$(fnm env)" && openclaw doctor
```

## 重启 Gateway

3. 重启 Gateway
```bash
eval "$(fnm env)" && openclaw gateway restart
```

## 更新 API Key

4. 更新 OpenRouter API Key（需要传入新 Key）
```bash
./update-key.sh <新的API_KEY>
```
