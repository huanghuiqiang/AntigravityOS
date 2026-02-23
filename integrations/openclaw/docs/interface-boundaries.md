# Interface Boundaries

## OpenClaw Plugin Layer

- Accepts Telegram callback messages.
- Validates callback format and byte length.
- Routes callback to a tool name.
- Calls Antigravity gateway via HTTP.

## Antigravity Tool Gateway

- Exposes `/api/tools/*` endpoints.
- Performs request validation and error mapping.
- Enforces allowlist and rate limit.
- Executes GitHub tool logic and internal actions.
- Emits audit records with trace IDs.

## External GitHub API Layer

- Handles repository read operations and PR comment writes.
- Returns provider-specific payloads.
- Gateway normalizes payloads to stable response envelopes.

## Ownership Rule

- Plugin owns callback parsing and tool routing.
- Gateway owns business execution and audit.
- GitHub API client owns provider protocol details.
