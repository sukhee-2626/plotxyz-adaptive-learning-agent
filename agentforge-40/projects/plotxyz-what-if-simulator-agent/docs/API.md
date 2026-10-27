# API · What-If Simulator

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
  "baseline": "{\"revenue\":100000,\"growth_rate_pct\":4,\"churn_rate_pct\":2,\"gross_margin_pct\":70,\"months\":12}",
  "scenarios": "[{\"name\":\"Base\",\"growth_delta_pct\":0,\"churn_delta_pct\":0},{\"name\":\"Churn spike\",\"growth_delta_pct\":0,\"churn_delta_pct\":3},{\"name\":\"Growth push\",\"growth_delta_pct\":2,\"churn_delta_pct\":-1}]"
}
}
```

### Response

```json
{
  "agent": "plotxyz-what-if-simulator-agent",
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
  -d '{"payload": {"baseline": "{\"revenue\":100000,\"growth_rate_pct\":4,\"churn_rate_pct\":2,\"gross_margin_pct\":70,\"months\":12}", "scenarios": "[{\"name\":\"Base\",\"growth_delta_pct\":0,\"churn_delta_pct\":0},{\"name\":\"Churn spike\",\"growth_delta_pct\":0,\"churn_delta_pct\":3},{\"name\":\"Growth push\",\"growth_delta_pct\":2,\"churn_delta_pct\":-1}]"}}'
```
