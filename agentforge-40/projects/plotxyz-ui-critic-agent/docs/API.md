# API · UI Critic

Base URL: `http://localhost:8000`

## Endpoints

| Method | Path | Purpose |
| :-- | :-- | :-- |
| `GET` | `/health` | Liveness and agent identity |
| `GET` | `/api/meta` | Agent metadata and provider status |
| `POST` | `/api/run` | Execute the agent with a JSON payload |
| `GET` | `/api/history?limit=20` | Recent local task history |
| `DELETE` | `/api/history` | Clear local history |

Interactive OpenAPI documentation: `GET /docs`.

## POST /api/run

### Request

```json
{
  "payload": {
  "elements": "[{\"name\":\"Submit button\",\"type\":\"button\",\"label\":\"\",\"contrast_ratio\":2.8,\"tap_size_px\":36},{\"name\":\"Hero image\",\"type\":\"image\",\"label\":\"Hero\",\"alt\":\"\",\"contrast_ratio\":5.0},{\"name\":\"Email field\",\"type\":\"input\",\"label\":\"Email\",\"contrast_ratio\":7.2,\"tap_size_px\":48}]",
  "description": ""
}
}
```

### Response

```json
{
  "agent": "plotxyz-ui-critic-agent",
  "summary": "A concise result summary.",
  "result": {
    "metrics": {},
    "findings": [],
    "table": {"columns": [], "rows": []}
  },
  "warnings": [],
  "task_id": 1
}
```

The exact `result` keys depend on the agent. Common keys include `metrics`, `findings`, `table`, `graph`, `chart`, `patches`, `markdown`, `items`, and agent-specific data.

### Error responses

| Status | Meaning |
| :-- | :-- |
| `413` | Payload exceeds `MAX_PAYLOAD_CHARS` |
| `422` | Missing or invalid agent input; `detail` explains the field |
| `500` | Unexpected server failure (no secrets are returned) |

## Limits

- Payload size: 200,000 characters by default (`MAX_PAYLOAD_CHARS`).
- History: returns at most 50 items.
- No authentication is included in this MVP. Add authentication, rate limiting, and TLS before public deployment.

## Example

```bash
curl -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"payload": {"elements": "[{\"name\":\"Submit button\",\"type\":\"button\",\"label\":\"\",\"contrast_ratio\":2.8,\"tap_size_px\":36},{\"name\":\"Hero image\",\"type\":\"image\",\"label\":\"Hero\",\"alt\":\"\",\"contrast_ratio\":5.0},{\"name\":\"Email field\",\"type\":\"input\",\"label\":\"Email\",\"contrast_ratio\":7.2,\"tap_size_px\":48}]", "description": ""}}'
```
