# OpenClaw × Antigravity Tool Bridge Runbook

## Required Environment Variables

- `ANTIGRAVITY_URL`
- `GITHUB_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_ACCOUNT`
- `TELEGRAM_ALLOWED_GROUP`

## Health Check

```bash
curl -sS -X POST http://127.0.0.1:8010/api/tools/health
```

## Common Diagnostics

1. `401/403` from GitHub
- Verify `GITHUB_TOKEN` scopes for repository read/comment permissions.

2. `429` from GitHub
- Reduce polling frequency and enable retry with backoff.

3. Callback not routed
- Ensure callback string starts with `callback_data: `.
- Ensure `callback_data` length is less than or equal to `64` bytes.

4. Tool not found
- Confirm `tool_name` is in gateway allowlist.

## Safe Rollback

1. Disable Telegram allowlist entries.
2. Set `dryRun=true` for `github_comment_pr`.
3. Stop the gateway service.
