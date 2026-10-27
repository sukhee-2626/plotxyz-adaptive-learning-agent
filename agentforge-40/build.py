"""Generate the 50 independent PlotXYZ.ai agent repositories."""
from __future__ import annotations

import inspect
import json
import pprint
import shutil
from pathlib import Path

import logic_common
import specs

BASE = Path(__file__).resolve().parent
PROJECTS = BASE / "projects"
TEMPLATES = BASE / "templates"
OWNER = "sukhee-2626"
VERSION = "1.0.0"


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def helper_source() -> str:
    parts = [
        inspect.getsource(logic_common.LogicError),
        inspect.getsource(logic_common._text),
        inspect.getsource(logic_common._num),
        inspect.getsource(logic_common._json),
        inspect.getsource(logic_common._csv),
        "STOPWORDS = " + repr(logic_common.STOPWORDS) + "\n",
        inspect.getsource(logic_common._tokens),
        inspect.getsource(logic_common._sentences),
        inspect.getsource(logic_common.provider_status),
        inspect.getsource(logic_common._llm),
        inspect.getsource(logic_common._result),
    ]
    return "\n\n".join(part.strip() + "\n" for part in parts)


def logic_file(spec: dict) -> str:
    fn = spec["function"]
    return f'''"""Original deterministic implementation for {spec["title"]} ({spec["slug"]})."""
from __future__ import annotations

import ast
import csv
import io
import json
import math
import os
import re
import statistics
import time
from collections import Counter, defaultdict, deque


{helper_source()}

{inspect.getsource(fn).strip()}


run = {fn.__name__}
'''


def main_file(spec: dict) -> str:
    features = json.dumps(spec["features"], ensure_ascii=False)
    limitations = json.dumps(spec["limitations"], ensure_ascii=False)
    template = '''"""FastAPI service for __TITLE__."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .logic import LogicError, provider_status, run

AGENT_SLUG = "__SLUG__"
AGENT_TITLE = "__TITLE__"
AGENT_TAGLINE = "__TAGLINE__"
AGENT_PURPOSE = "__PURPOSE__"
FEATURES = __FEATURES__
LIMITATIONS = __LIMITATIONS__
VERSION = "__VERSION__"
MAX_PAYLOAD_CHARS = int(os.getenv("MAX_PAYLOAD_CHARS", "200000"))

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "history.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(AGENT_SLUG)


@contextmanager
def database():
    connection = sqlite3.connect(DB_PATH)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db():
    with database() as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS tasks ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "created_at TEXT NOT NULL, "
            "summary TEXT NOT NULL, "
            "payload TEXT NOT NULL, "
            "result TEXT NOT NULL)"
        )


init_db()


class RunRequest(BaseModel):
    payload: dict = Field(default_factory=dict, description="Agent-specific validated input payload.")


class RunResponse(BaseModel):
    agent: str
    summary: str
    result: dict
    warnings: list[str] = Field(default_factory=list)
    task_id: int | None = None


class HistoryItem(BaseModel):
    id: int
    created_at: str
    summary: str
    payload: dict


app = FastAPI(
    title=f"PlotXYZ.ai · {AGENT_TITLE}",
    version=VERSION,
    description=AGENT_PURPOSE,
)
origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.get("/")
def root():
    return {"agent": AGENT_SLUG, "title": AGENT_TITLE, "version": VERSION, "docs": "/docs", "health": "/health"}


@app.get("/health")
def health():
    return {"status": "ok", "agent": AGENT_SLUG, "version": VERSION}


@app.get("/api/meta")
def meta():
    return {
        "agent": AGENT_SLUG,
        "title": AGENT_TITLE,
        "tagline": AGENT_TAGLINE,
        "purpose": AGENT_PURPOSE,
        "version": VERSION,
        "features": FEATURES,
        "limitations": LIMITATIONS,
        "providers": provider_status(),
        "max_payload_chars": MAX_PAYLOAD_CHARS,
    }


@app.post("/api/run", response_model=RunResponse)
def execute_agent(request: RunRequest):
    serialized = json.dumps(request.payload)
    if len(serialized) > MAX_PAYLOAD_CHARS:
        raise HTTPException(status_code=413, detail=f"Payload exceeds the {MAX_PAYLOAD_CHARS} character limit.")
    try:
        outcome = run(request.payload)
    except LogicError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception("Unhandled agent failure")
        raise HTTPException(status_code=500, detail="The agent could not process this request.") from None
    created_at = datetime.now(timezone.utc).isoformat()
    with database() as connection:
        cursor = connection.execute(
            "INSERT INTO tasks (created_at, summary, payload, result) VALUES (?, ?, ?, ?)",
            (created_at, outcome["summary"][:500], serialized[:MAX_PAYLOAD_CHARS], json.dumps(outcome)[:MAX_PAYLOAD_CHARS]),
        )
        task_id = cursor.lastrowid
    return RunResponse(agent=AGENT_SLUG, task_id=task_id, **outcome)


@app.get("/api/history")
def history(limit: int = 20):
    limit = max(1, min(limit, 50))
    with database() as connection:
        rows = connection.execute(
            "SELECT id, created_at, summary, payload FROM tasks ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    items = []
    for row in rows:
        try:
            payload = json.loads(row[3])
        except json.JSONDecodeError:
            payload = {}
        items.append(HistoryItem(id=row[0], created_at=row[1], summary=row[2], payload=payload))
    return {"items": items}


@app.delete("/api/history", status_code=204)
def clear_history():
    with database() as connection:
        connection.execute("DELETE FROM tasks")
    return Response(status_code=204)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
'''
    replacements = {
        "__SLUG__": spec["slug"],
        "__TITLE__": spec["title"],
        "__TAGLINE__": spec["tagline"],
        "__PURPOSE__": spec["purpose"],
        "__FEATURES__": features,
        "__LIMITATIONS__": limitations,
        "__VERSION__": VERSION,
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    return template


def test_file(spec: dict) -> str:
    checks = "\n".join(f"    {check}" for check in spec["checks"])
    sample = pprint.pformat(spec["sample"], width=110, sort_dicts=False)
    stress = ""
    if spec["slug"] in {
        "plotxyz-data-quality-guardian",
        "plotxyz-etl-pipeline-agent",
        "plotxyz-csv-insights-agent",
        "plotxyz-anomaly-investigator-agent",
    }:
        stress = '''

def test_large_csv_stress():
    lines = ["id,region,amount,status"]
    for index in range(2000):
        lines.append(f"{index},{'north' if index % 2 else 'south'},{index % 500},{'paid' if index % 3 else 'pending'}")
    payload = dict(SAMPLE)
    payload["csv"] = "\\n".join(lines)
    if "column" in payload:
        payload["column"] = "amount"
    res = run(payload)
    assert res["summary"]
    assert res["result"]["metrics"]
'''
    return f'''"""Tests for {spec["title"]} logic and API behavior."""
from fastapi.testclient import TestClient

from app.logic import LogicError, run
from app.main import app

SAMPLE = {sample}


def test_sample_run():
    res = run(SAMPLE)
    assert res["summary"]
    assert isinstance(res["result"], dict)
{checks}


def test_empty_payload_is_rejected():
    try:
        run({{}})
    except LogicError:
        return
    raise AssertionError("empty payload should raise LogicError")


def test_health_and_meta():
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    meta = client.get("/api/meta")
    assert meta.status_code == 200
    assert meta.json()["agent"] == "{spec["slug"]}"


def test_run_endpoint_and_history():
    client = TestClient(app)
    response = client.post("/api/run", json={{"payload": SAMPLE}})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]
    assert body["task_id"] is not None
    history = client.get("/api/history?limit=5")
    assert history.status_code == 200
    assert len(history.json()["items"]) >= 1


def test_invalid_payload_returns_422():
    client = TestClient(app)
    response = client.post("/api/run", json={{"payload": {{}}}})
    assert response.status_code == 422


def test_payload_limit_returns_413():
    client = TestClient(app)
    response = client.post("/api/run", json={{"payload": {{"blob": "x" * 200001}}}})
    assert response.status_code == 413
{stress}'''



def config_ts(spec: dict) -> str:
    data = {
        "slug": spec["slug"],
        "title": spec["title"],
        "tagline": spec["tagline"],
        "purpose": spec["purpose"],
        "accent": spec["accent"],
        "features": spec["features"],
        "limitations": spec["limitations"],
        "fields": spec["fields"],
        "sample": spec["sample"],
        "repo": f"https://github.com/{OWNER}/{spec['slug']}",
    }
    return '''export type FieldType = "text" | "textarea" | "number" | "checkbox";

export interface AgentField {
  name: string;
  label: string;
  type: FieldType;
  rows?: number;
  placeholder?: string;
}

export interface AgentConfig {
  slug: string;
  title: string;
  tagline: string;
  purpose: string;
  accent: string;
  features: string[];
  limitations: string[];
  fields: AgentField[];
  sample: Record<string, string | number | boolean>;
  repo: string;
}

export const agent: AgentConfig = ''' + json.dumps(data, indent=2, ensure_ascii=False) + ";\n"


def readme(spec: dict) -> str:
    features = "\n".join(f"- **{feature}**" for feature in spec["features"])
    limitations = "\n".join(f"- {item}" for item in spec["limitations"])
    roadmap = "\n".join(
        f"- [ ] {item}"
        for item in [
            f"Expand {spec['features'][0].lower()} with configurable policies.",
            "Add deployment manifests, structured audit logs, and load tests.",
            "Add more export formats and team-oriented workspaces.",
        ]
    )
    sample_json = json.dumps(spec["sample"], indent=2, ensure_ascii=False)
    template = '''<div align="center">

# PlotXYZ.ai · __TITLE__

**__TAGLINE__**

[![CI](https://github.com/__OWNER__/__SLUG__/actions/workflows/ci.yml/badge.svg)](https://github.com/__OWNER__/__SLUG__/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-22c55e)

</div>

> **PlotXYZ.ai Agents** — specialized intelligence. One connected workspace.

## 1. Project identity and purpose

**__TITLE__** is an original, independently runnable PlotXYZ.ai agent MVP. __PURPOSE__

The project is a functional reference implementation, not a claim that PlotXYZ.ai owns or endorses any third-party technology. It runs without a paid API key: the deterministic implementation is the default path, and optional model providers are configured explicitly.

## 2. Problem statement and intended users

Teams often need a focused, inspectable tool rather than another general chatbot. This agent packages one clear workflow with structured inputs, deterministic checks, and an exportable result.

**Intended users:** __USERS__

## 3. Features

__FEATURES__

- **Structured results:** metrics, findings, tables, charts, graphs, patches, or generated documents as appropriate.
- **Task history:** local SQLite persistence for completed runs.
- **Provider status:** the dashboard reports whether an optional model adapter is configured.
- **Accessible states:** loading, success, validation error, and offline-API states are explicit.

## 4. Screenshots

> **Screenshot placeholder:** run the app locally and add `docs/screenshot.png` here. No fabricated screenshot is included in this repository.

## 5. Architecture

```mermaid
flowchart LR
  U[User] --> W[React + TypeScript dashboard]
  W -->|POST /api/run| A[FastAPI service]
  A --> V[Pydantic request model + payload limit]
  V --> L[__TITLE__ deterministic logic]
  L --> R[Structured result]
  A --> H[(SQLite task history)]
  W -->|GET /api/meta and /api/history| A
```

The frontend is a Vite/React single-page dashboard. The backend validates the request, applies a 200,000-character payload limit, runs the agent-specific logic, stores a local history record, and returns a structured response. The logic layer is original Python and does not execute supplied code or shell commands.

## 6. Technology stack

| Layer | Technology |
| :-- | :-- |
| Frontend | React 18, TypeScript, Vite 5, Lucide icons, custom CSS design system |
| Backend | Python 3.11+, FastAPI, Pydantic 2 |
| Persistence | SQLite (local task history) |
| Tests | Pytest, FastAPI TestClient |
| CI | GitHub Actions (backend tests + frontend production build) |

## 7. Repository structure

```text
__SLUG__/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── logic.py          # original agent-specific logic
│   │   └── main.py           # FastAPI routes, validation, SQLite history
│   ├── tests/test_api.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── agentConfig.ts
│   │   ├── main.tsx
│   │   └── styles.css
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── docs/
│   ├── ARCHITECTURE.md
│   └── API.md
├── .github/workflows/ci.yml
├── .env.example
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── SECURITY.md
└── README.md
```

## 8. Prerequisites

- Python 3.11 or newer
- Node.js 20 or newer and npm
- Git
- No paid API key is required

## 9. Installation and startup

```bash
git clone https://github.com/__OWNER__/__SLUG__.git
cd __SLUG__
```

### Backend

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --reload --app-dir backend
```

The API is available at `http://localhost:8000`; interactive docs are at `/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The frontend defaults to `http://localhost:8000` for the API. Set `VITE_API_BASE_URL` to point elsewhere.

### Production deployment

```bash
cd frontend
npm ci
npm run build
# Serve frontend/dist with any static host or reverse proxy.

cd ../backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Set `VITE_API_BASE_URL` at build time to the public API URL, and set `CORS_ORIGINS` to the deployed frontend origin. Persist `backend/data/` if task history matters. The app is otherwise stateless and does not require a paid API key.

## 10. Environment configuration

Copy `.env.example` to `.env` and export the values in your shell (the backend does not auto-load `.env`).

| Variable | Purpose | Required |
| :-- | :-- | :-- |
| `VITE_API_BASE_URL` | Frontend API base URL | No (defaults to `http://localhost:8000`) |
| `OPENAI_BASE_URL` | OpenAI-compatible API base | No |
| `OPENAI_API_KEY` | Provider key (never commit it) | No |
| `OPENAI_MODEL` | Model name for the optional adapter | No |
| `OLLAMA_BASE_URL` | Local Ollama-compatible base URL | No |
| `OLLAMA_MODEL` | Local model name | No |
| `CORS_ORIGINS` | Comma-separated allowed origins | No |
| `MAX_PAYLOAD_CHARS` | Server-side payload limit | No (default `200000`) |

The deterministic path is always available. When no provider is configured, the UI shows **Deterministic mode** and the API reports the provider status without exposing secrets.

## 11. API example

```bash
curl -X POST http://localhost:8000/api/run \\
  -H "Content-Type: application/json" \\
  -d '{"payload": __SAMPLE_JSON_CURL__}'
```

Sample payload:

```json
__SAMPLE_JSON__
```

The response contains `summary`, `result` (structured metrics, findings, tables, charts, or documents), `warnings`, `agent`, and `task_id`. See [`docs/API.md`](docs/API.md) for the full contract.

## 12. Testing

```bash
cd backend
python -m pytest -q

cd ../frontend
npm run build
```

The backend suite covers the sample workflow, empty-input rejection, health/meta endpoints, the run endpoint, history persistence, and HTTP 422 validation. CI runs both jobs on every push and pull request.

## 13. Security and privacy considerations

- No endpoint exposes arbitrary shell execution or unrestricted filesystem access.
- The agent never executes supplied code, downloads files, or writes to user-selected paths.
- Inputs are size-limited; errors are structured and do not leak secrets.
- Secrets are read from environment variables and are never returned by the API.
- Optional model calls go only to explicitly configured environment endpoints; user-supplied URLs are not fetched.
- SQLite history is local to the backend and can be cleared from the dashboard.
- See [`SECURITY.md`](SECURITY.md) for reporting guidance.

## 14. Limitations

__LIMITATIONS__

- The deterministic logic is intentionally scoped; optional AI inference may improve flexibility but is not required or guaranteed.
- Results are decision support, not professional advice. Review outputs before acting on them.

## 15. Roadmap

__ROADMAP__

## 16. Contribution guidelines

Contributions are welcome. Read [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, test, and pull-request guidance. Please keep changes focused, add tests for behavior changes, and do not commit secrets.

## 17. License

MIT License. Copyright (c) 2026 __OWNER__. See [`LICENSE`](LICENSE).

The license choice covers this repository's original source code. Third-party dependencies remain under their own licenses.
'''
    replacements = {
        "__TITLE__": spec["title"],
        "__TAGLINE__": spec["tagline"],
        "__PURPOSE__": spec["purpose"],
        "__USERS__": spec["users"],
        "__FEATURES__": features,
        "__LIMITATIONS__": limitations,
        "__ROADMAP__": roadmap,
        "__SAMPLE_JSON__": sample_json,
        "__SAMPLE_JSON_CURL__": json.dumps(spec["sample"], ensure_ascii=False).replace("'", "'\\''"),
        "__SLUG__": spec["slug"],
        "__OWNER__": OWNER,
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    return template


def architecture_doc(spec: dict) -> str:
    return f'''# Architecture · {spec["title"]}

## Overview

{spec["purpose"]}

This repository is independently runnable. It contains its own React dashboard, FastAPI service, deterministic agent logic, SQLite history, tests, and documentation. It does not import code from another agent repository.

## Components

```mermaid
flowchart TB
  subgraph Browser
    UI[React dashboard]
    CFG[agentConfig.ts]
    UI --> CFG
  end
  subgraph Backend
    API[FastAPI app]
    MODEL[Pydantic RunRequest / RunResponse]
    LOGIC[logic.py · {spec["slug"]}]
    DB[(SQLite history.db)]
    API --> MODEL --> LOGIC
    API --> DB
  end
  UI -->|POST /api/run| API
  UI -->|GET /api/meta| API
  UI -->|GET/DELETE /api/history| API
```

## Request lifecycle

1. The dashboard builds a typed payload from the agent-specific form.
2. `POST /api/run` validates the envelope with Pydantic and enforces the payload character limit.
3. `logic.run(payload)` validates fields, performs deterministic analysis, and returns `summary`, `result`, and `warnings`.
4. The API writes a local history row and returns a structured `RunResponse`.
5. The dashboard renders metrics, findings, tables, charts, graphs, patches, or documents and offers copy/export actions.

## Design decisions

- **Deterministic first.** Every feature works without a paid key. Optional provider adapters are opt-in and report their status.
- **Original, scoped logic.** The agent-specific implementation lives in `backend/app/logic.py`; it does not call a shared chatbot endpoint.
- **No unsafe execution.** Supplied code and data are parsed or analyzed, never executed as shell commands. Workflow operations are allowlisted and in-memory.
- **Local persistence.** SQLite keeps the demo self-contained; the history endpoint is bounded and can be cleared.
- **Single design language, agent-specific content.** The UI shell is shared scaffolding; forms, examples, accent, results, and backend behavior are specific to this agent.

## Error handling

| Condition | Behavior |
| :-- | :-- |
| Missing or invalid field | `422` with a specific validation message |
| Payload over limit | `413` |
| Unexpected logic failure | `500`, logged server-side without secrets |
| API offline | Dashboard shows an actionable error and keeps the form intact |
| Optional provider unavailable | Deterministic fallback with a visible warning |

## Security and privacy

- No shell, unrestricted filesystem, or arbitrary URL execution is exposed.
- Secrets come from environment variables and are never included in responses.
- CORS is restricted to configured local origins by default.
- History is local and bounded; users can delete it.
- The agent analyzes supplied content only and does not claim external verification.

## Testing strategy

- Unit-level sample execution and agent-specific assertions.
- API integration tests for health, meta, run, history, and validation.
- Frontend production build in CI.

## Limits

- The backend is a single-process reference service; SQLite is not intended for multi-tenant scale.
- No authentication or rate limiting is included in this MVP; add them before exposing the service publicly.
'''


def api_doc(spec: dict) -> str:
    sample = json.dumps(spec["sample"], indent=2, ensure_ascii=False)
    return f'''# API · {spec["title"]}

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
{{
  "payload": {sample}
}}
```

### Response

```json
{{
  "agent": "{spec["slug"]}",
  "summary": "A concise result summary.",
  "result": {{
    "metrics": {{}},
    "findings": [],
    "table": {{"columns": [], "rows": []}}
  }},
  "warnings": [],
  "task_id": 1
}}
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
curl -X POST http://localhost:8000/api/run \\
  -H "Content-Type: application/json" \\
  -d '{{"payload": {json.dumps(spec["sample"], ensure_ascii=False)}}}'
```
'''


def generic_docs(spec: dict) -> dict[str, str]:
    slug = spec["slug"]
    title = spec["title"]
    return {
        "LICENSE": f'''MIT License

Copyright (c) 2026 {OWNER}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
''',
        "CONTRIBUTING.md": f'''# Contributing to {title}

Thanks for improving this PlotXYZ.ai agent MVP.

## Local setup

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
cd frontend && npm install
```

## Before opening a pull request

```bash
cd backend && python -m pytest -q
cd ../frontend && npm run build
```

- Keep the deterministic path working without any paid API key.
- Add or update tests for behavior changes.
- Do not commit secrets, `.env` files, `node_modules`, build output, or local SQLite data.
- Keep the agent's logic original and scoped; do not replace it with a generic chatbot endpoint.
- Document new inputs, limits, and failure modes.

## Pull requests

Describe the problem, the change, and the verification performed. Small, focused changes are easiest to review. By contributing, you agree that your contribution is licensed under the repository's MIT license.
''',
        "SECURITY.md": f'''# Security policy

## Supported versions

The latest `main` branch is supported for security fixes.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting or open a minimal issue that does not disclose exploit details. Do not include secrets, personal data, or production credentials.

## Design controls

- No endpoint exposes arbitrary shell execution or unrestricted filesystem access.
- Supplied code is parsed or analyzed; it is not executed.
- Inputs are size-limited and validated; errors do not leak secrets.
- Optional provider credentials are read from environment variables and never returned.
- CORS defaults to local development origins.
- SQLite history is local and user-clearable.

## Deployment notes

This MVP has no built-in authentication or rate limiting. Put it behind an authenticated gateway, enforce TLS, restrict CORS, and add rate limits before exposing it to untrusted networks.

## Out of scope

The deterministic analysis is decision support. It does not provide legal, medical, financial, or compliance certification.
''',
        "CHANGELOG.md": f'''# Changelog

All notable changes to this project are documented here.

## [1.0.0] - 2026-10-25

### Added

- Original deterministic {title} logic with structured results.
- React + TypeScript + Vite dashboard with agent-specific inputs, examples, history, copy, and export.
- FastAPI service with validation, health/meta endpoints, SQLite task history, and payload limits.
- Pytest suite and GitHub Actions CI.
- Architecture, API, contribution, security, and license documentation.
''',
        ".gitignore": '''# Python
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/
backend/data/
*.db

# Node
node_modules/
dist/
dist-ssr/
*.local

# Environment and editor
.env
.env.*
!.env.example
.vscode/
.idea/
.DS_Store
Thumbs.db
''',
        ".env.example": '''# Frontend
VITE_API_BASE_URL=http://localhost:8000

# Optional OpenAI-compatible provider (never commit real keys)
OPENAI_BASE_URL=
OPENAI_API_KEY=
OPENAI_MODEL=

# Optional Ollama-compatible provider
OLLAMA_BASE_URL=
OLLAMA_MODEL=

# Backend controls
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
MAX_PAYLOAD_CHARS=200000
''',
        ".github/workflows/ci.yml": '''name: CI

on:
  push:
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: backend/requirements.txt
      - run: pip install -r requirements.txt
      - run: python -m pytest -q

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm install --no-audit --no-fund
      - run: npm run build
''',
    }


def package_json(spec: dict) -> str:
    return json.dumps(
        {
            "name": spec["slug"],
            "private": True,
            "version": VERSION,
            "type": "module",
            "description": spec["tagline"],
            "scripts": {"dev": "vite", "build": "tsc --noEmit && vite build", "preview": "vite preview"},
            "dependencies": {"lucide-react": "^0.468.0", "react": "^18.3.1", "react-dom": "^18.3.1"},
            "devDependencies": {
                "@types/react": "^18.3.12",
                "@types/react-dom": "^18.3.1",
                "@vitejs/plugin-react": "^4.3.4",
                "typescript": "^5.6.3",
                "vite": "^5.4.11",
            },
        },
        indent=2,
    ) + "\n"


def build_agent(spec: dict) -> dict:
    root = PROJECTS / spec["slug"]
    shutil.rmtree(root, ignore_errors=True)
    backend = root / "backend"
    frontend = root / "frontend"

    write(backend / "app" / "__init__.py", "")
    write(backend / "app" / "logic.py", logic_file(spec))
    write(backend / "app" / "main.py", main_file(spec))
    write(backend / "tests" / "test_api.py", test_file(spec))
    write(backend / "requirements.txt", '''fastapi>=0.115,<1
uvicorn[standard]>=0.30,<1
pydantic>=2.9,<3
pytest>=8,<10
httpx>=0.27,<1
''')

    write(frontend / "src" / "agentConfig.ts", config_ts(spec))
    write(frontend / "src" / "App.tsx", (TEMPLATES / "App.tsx").read_text(encoding="utf-8"))
    write(frontend / "src" / "styles.css", (TEMPLATES / "styles.css").read_text(encoding="utf-8"))
    write(frontend / "src" / "main.tsx", '''import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
''')
    write(frontend / "index.html", f'''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="description" content="{spec['tagline']} — a PlotXYZ.ai agent MVP." />
    <title>{spec['title']} · PlotXYZ.ai</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
''')
    write(frontend / "package.json", package_json(spec))
    write(frontend / "tsconfig.json", '''{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "Bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noFallthroughCasesInSwitch": true,
    "types": ["vite/client"]
  },
  "include": ["src"]
}
''')
    write(frontend / "vite.config.ts", '''import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
''')

    write(root / "README.md", readme(spec))
    write(root / "docs" / "ARCHITECTURE.md", architecture_doc(spec))
    write(root / "docs" / "API.md", api_doc(spec))
    for name, content in generic_docs(spec).items():
        write(root / name, content)
    return root


def main() -> None:
    if len(specs.AGENTS) != 50:
        raise SystemExit(f"expected 50 agents, found {len(specs.AGENTS)}")
    PROJECTS.mkdir(exist_ok=True)
    manifest = []
    for index, spec in enumerate(specs.AGENTS, 1):
        root = build_agent(spec)
        manifest.append({
            "index": index,
            "slug": spec["slug"],
            "title": spec["title"],
            "tagline": spec["tagline"],
            "accent": spec["accent"],
            "path": str(root),
            "status": "built",
            "tests": "not-run",
            "published": False,
            "url": "",
        })
        print(f"[{index:02d}/50] built {spec['slug']}")
    write(BASE / "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    progress = ["# PlotXYZ.ai Agents · Build Progress", "", "50 original agent MVPs. Work is executed in batches of five; status below is authoritative.", "", "| # | Repository | Status | Tests | Published |", "| --: | :-- | :-- | :-- | :-- |"]
    for item in manifest:
        progress.append(f"| {item['index']} | `{item['slug']}` | built | not run | — |")
    progress += ["", "## Notes", "", "- License: MIT, copyright holder `sukhee-2626` (authenticated repository owner).", "- `gh` CLI is not installed; GitHub publishing uses the authenticated REST API and git credentials.", "- Each repository is independently runnable and contains its own frontend, backend, tests, docs, and CI."]
    write(BASE / "PROGRESS.md", "\n".join(progress) + "\n")
    print("built 50 repositories")


if __name__ == "__main__":
    main()
