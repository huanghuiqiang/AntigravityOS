# Tool Gateway API Contract

## Request

- Method: `POST`
- Path: `/api/tools/{tool_name}`
- Header: `X-Trace-Id` (optional, auto-generated if missing)
- Body: JSON object matching tool schema

## Success Response

- HTTP: `200`
- Body:

```json
{
  "success": true,
  "data": {},
  "trace_id": "uuid",
  "content": [{"type": "text", "text": "..."}]
}
```

## Error Response

- HTTP: `4xx` or `5xx`
- Body:

```json
{
  "success": false,
  "error": {"message": "..."},
  "trace_id": "uuid"
}
```

## Supported Tools

- `github_list_open_prs`
- `github_commit_stats`
- `github_repo_activity`
- `github_comment_pr`
- `ag_daily_briefing`
- `ag_weekly_sync`
