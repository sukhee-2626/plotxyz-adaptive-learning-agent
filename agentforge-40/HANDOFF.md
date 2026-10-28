# Session Handoff — PlotXYZ.ai Agents (50 repos)

**Saved:** 2026-10-27 (session paused at user request)
**Resume:** 2026-10-28
**Working root:** `C:\Users\HP\todo-app\agentforge-40`

---

## 1. User's latest requirements

1. Make every agent **fully functional** end to end.
2. Let the user **pull a repo, add an API key in `.env`, and use it** without editing code.
3. Use **OpenCode as an AI/API provider** and test the integration.
4. Improve the UI/UX: **easy, neat, all features easy to access**.
5. Re-apply **README enhancements** to every existing repo.
6. Test agents **one by one** and provide a **final list of all 50 agents**.
7. Keep the deterministic baseline working with **no paid API key**; never fabricate results.

---

## 2. Current state (important)

### Done earlier
- 50 agent MVPs implemented with unique deterministic logic:
  - `logic_a.py` (agents 1–20)
  - `logic_b.py` (agents 21–50)
  - `specs.py` (metadata, fields, samples, checks)
  - `build.py` (generates all 50 projects)
- All 50 repos were created and published under `https://github.com/sukhee-2626/<slug>`.
- Earlier validation: **304 backend tests passed across 50 repos**, **50/50 frontend builds passed**.
- Earlier README enhancement was applied and partially pushed.

### Current local state after the last `build.py` run
- `python build.py` was run successfully: **50/50 projects regenerated**.
- **This wiped each project's `.git` directory**, all `node_modules`, and the enhanced READMEs.
- No project currently has `node_modules`.
- The last `npm install` run timed out; do not assume dependencies are installed.
- `manifest.json` was reset by `build.py`:
  - all entries are `status: "built"`, `tests: "not-run"`, `published: false`, `url: ""`.
- `PROGRESS.md` was also reset by `build.py`.
- The current project code is the **old backend/UI** (no provider layer, no AI narrative).
- `templates/styles.css` is a newer dark theme but is **missing styles used by `App.tsx`**:
  - `.nav`, `.settings-bar`, `.form-card`, `.result-card`, `.table-panel`, `.hero-chips`.
- `templates/App.tsx` is still the old UI (sample prefill + settings bar + provider pill), without the planned AI panel/capabilities/nav improvements.

### Git state
- The root workspace `C:\Users\HP\todo-app` is a git repo.
- `agentforge-40` may have a broken/odd `.git` state. A `git status` run from `agentforge-40` returned:
  - `fatal: 'agentforge-40/projects/plotxyz-compliance-checker-agent/.git' not recognized as a git repository`
- Investigate before committing:
  - `Get-ChildItem -Force C:\Users\HP\todo-app\agentforge-40\.git`
  - If `.git` is a file, inspect its `gitdir:` target.
  - Do **not** delete user data without checking.
- All project `.git` directories are gone because `build.py` uses `shutil.rmtree(root)`.

### README push state
- README push was **incomplete/unverified** before the rebuild.
- Some repos were synced; many failed due to:
  - local branch `master` vs remote `main`
  - missing `origin`
  - network/DNS resets
  - stale `index.lock`
- After the rebuild, **all 50 need a fresh git init + commit + push**.

---

## 3. Key findings from this session

### OpenCode Console (OpenAI-compatible API)
- Base URL: `https://opencode.ai/inference/openai/v1`
- Chat endpoint: `https://opencode.ai/inference/openai/v1/chat/completions`
- Model list includes `deepseek-v4.1-flash-free`.
- Requires an OpenCode Console API key (`OPENCODE_API_KEY`).
- Free-tier models may require the OpenCode client; paid/Go models work from other clients.
- This is the best "pull repo, add env key, use it" provider preset.

### Local OpenCode service API
- OpenCode CLI installed: `v2.1.2`.
- Executable: `C:\Users\HP\AppData\Roaming\npm\node_modules\@opencode\cli\bin\opencode.exe`
- Service started at `http://127.0.0.1:45278` (port is dynamic).
- Useful one-shot endpoint:
  - `POST /api/experimental/generate`
  - Body:
    ```json
    {
      "prompt": "...",
      "model": {"providerID": "opencode", "id": "deepseek-v4.1-flash-free"}
    }
    ```
  - Response: `{"data": {"text": "..."}}`
- Direct HTTP requests to the service return `UnauthorizedError`; `opencode api` handles auth.
- PowerShell quoting for `opencode api --data` is unreliable. Use Python `subprocess.run([exe, "api", "post", "/api/experimental/generate", "--data", json.dumps(body)])` with an argument list.
- **Live model call is currently blocked:**
  - Free model: `Free usage limit reached`.
  - Default OpenRouter model: insufficient credits for 65536 max tokens.
- No `OPENCODE_API_KEY` / `OPENAI_API_KEY` is present in the environment.
- No `~/.local/share/opencode/auth.json` and no `~/.config/opencode/opencode.json`.

### Testing implication
- Use a **local mock OpenAI-compatible server** for contract/integration tests.
- The mock should implement:
  - `GET /v1/models`
  - `POST /v1/chat/completions`
  - `POST /api/experimental/generate` (for local OpenCode CLI mode)
- Optionally test the local OpenCode CLI path with a fake `opencode` executable that prints the mock response.
- Do not claim a live AI call succeeded unless a real key/credit is available.

---

## 4. Planned implementation (not yet applied)

### A. Backend provider layer
Create `agentforge-40/templates/provider.py` and generate it into every repo as `backend/app/provider.py`.

Required features:
- Auto-load `.env` from repo root and `backend/.env` **without overriding existing env vars**.
- Provider modes:
  - `opencode` → OpenCode Console OpenAI-compatible HTTP
  - `openai` → any OpenAI-compatible endpoint
  - `ollama` → Ollama OpenAI-compatible endpoint
  - `opencode-local` → local OpenCode service via `opencode api` CLI
  - `deterministic` / `none` → off
- Auto-detect when `LLM_PROVIDER` is blank:
  - `OPENCODE_API_KEY` present → `opencode`
  - `OPENAI_API_KEY` present → `openai`
  - `OLLAMA_MODEL` present → `ollama`
  - otherwise deterministic
- `provider_status()` returns safe metadata only:
  - mode, active, provider, model, sanitized base URL, configured, llm_enabled,
    timeout, max_output_tokens, openai_compatible, opencode_compatible,
    ollama_compatible, local_opencode, key_present.
  - Never return API keys.
- `llm_chat(messages, ...)`:
  - OpenAI-compatible HTTP via `httpx`, fallback to stdlib `urllib` if needed.
  - Parse `choices[0].message.content` and `output_text`.
  - Sanitize errors; never leak secrets.
  - Retry without `max_tokens` if a provider rejects it.
- `llm_json(...)`:
  - Strip markdown fences; parse the first/last JSON object.
- `llm_test()`:
  - Minimal "Reply with ready" call.
  - Returns `ok`, `provider`, `model`, `latency_ms`, `message`, `reply_preview`.
- `enrich_result(outcome, title, purpose, features, payload)`:
  - Only runs when a provider is active.
  - Sends deterministic summary/metrics/findings/warnings + truncated payload.
  - Requires strict JSON:
    ```json
    {
      "summary": "...",
      "insights": ["..."],
      "recommendations": ["..."],
      "risks": ["..."],
      "confidence": "low|medium|high"
    }
    ```
  - Merges into `result["ai"]` and top-level `ai`.
  - Keeps `result["deterministic_summary"]`.
  - On failure, returns deterministic result + warning + `ai.status = "unavailable"`.
  - Never invents metrics; AI narrative is clearly labeled.

### B. `build.py` changes
- Add `VERSION = "1.1.0"` (optional but recommended).
- `helper_source()`: remove `provider_status` and `_llm` from the copied helpers.
- `logic_file()`: add
  ```python
  from .provider import llm_chat as _llm
  from .provider import provider_status
  ```
- `main_file()`:
  - Import `enrich_result, llm_test, provider_status` from `.provider`.
  - Remove `provider_status` from `.logic` import.
  - Add `ai: dict | None = None` to `RunResponse`.
  - After `outcome = run(request.payload)`, call:
    ```python
    outcome = enrich_result(
        outcome, AGENT_TITLE, AGENT_PURPOSE, FEATURES, request.payload
    )
    ```
  - Add `GET /api/provider/test` returning `llm_test()`.
- `build_agent()`: write `backend/app/provider.py` from the template.
- `generic_docs()[" .env.example"]`: add:
  ```env
  # AI provider (optional; deterministic mode works with no key)
  LLM_PROVIDER=
  LLM_ENABLED=true
  LLM_TIMEOUT_SECONDS=30
  LLM_MAX_OUTPUT_TOKENS=900

  # OpenCode Console (OpenAI-compatible)
  OPENCODE_BASE_URL=https://opencode.ai/inference/openai/v1
  OPENCODE_API_KEY=
  OPENCODE_MODEL=deepseek-v4.1-flash-free

  # Generic OpenAI-compatible
  OPENAI_BASE_URL=
  OPENAI_API_KEY=
  OPENAI_MODEL=

  # Ollama
  OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
  OLLAMA_MODEL=

  # Local OpenCode CLI (no external key; requires OpenCode installed)
  # OPENCODE_BIN=
  # OPENCODE_LOCAL_MODEL_PROVIDER=opencode
  # OPENCODE_LOCAL_MODEL=deepseek-v4.1-flash-free
  ```
- `readme()`:
  - Section 3: add "Optional AI narrative".
  - Section 5: add provider layer to the diagram.
  - Section 6: add optional AI provider row.
  - Section 7: add `provider.py`.
  - Section 9: add `cp .env.example .env` and restart note.
  - Section 10: document auto-load, OpenCode preset, OpenAI, Ollama, local OpenCode.
  - Section 11: include `ai` in the example response.
  - Section 12: mention provider tests and `/api/provider/test`.
  - Section 14: clarify AI narrative is optional.
- `api_doc()`:
  - Add `GET /api/provider/test`.
  - Document `ai` in the response.
  - Document provider env vars.
- `architecture_doc()`:
  - Add `provider.py` and the optional AI narrative flow.
- `test_file()`:
  - Add `test_provider_status_shape`.
  - Add `test_ai_enrichment_with_mock` (monkeypatch `provider.provider_status` and `provider.llm_json`).
  - Add `test_provider_test_endpoint` (200 + expected keys).
  - Add env-gated integration test:
    ```python
    def test_provider_enrichment_when_configured():
        if not os.getenv("LLM_PROVIDER"):
            return
        client = TestClient(app)
        response = client.post("/api/run", json={"payload": SAMPLE})
        assert response.status_code == 200
        body = response.json()
        assert body.get("ai", {}).get("enabled") is True, body.get("ai")
    ```
- Do **not** rerun `build.py` until the provider template and all build edits are ready.

### C. Frontend changes
- `templates/App.tsx`:
  - Add nav links: Workspace, Capabilities, History, API docs, GitHub.
  - Add a Capabilities grid with clickable feature cards.
  - Add a "How it works" 3-step strip (Input → Analyze → Export).
  - Add provider settings panel with:
    - mode, model, base URL, key present, timeout
    - **Test provider** button → `GET /api/provider/test`
    - `.env` instructions and restart note
  - Add an **AI narrative** panel in results:
    - summary, insights, recommendations, risks, confidence, latency
    - unavailable state with deterministic-fallback note
  - Add character counts for textareas.
  - Add `Ctrl+Enter` / `Cmd+Enter` to submit.
  - Keep existing result renderers (metrics, findings, table, graph, chart, patches, markdown, items, raw JSON).
  - Add Export Markdown (optional).
- `templates/styles.css`:
  - Add missing `.nav`, `.settings-bar`, `.form-card`, `.result-card`, `.table-panel`, `.hero-chips`.
  - Add `.capability-grid`, `.capability-card`, `.ai-panel`, `.ai-badge`, `.ai-summary`,
    `.ai-list`, `.ai-meta`, `.provider-test`, `.banner`, `.char-count`, `.kbd`.
  - Keep responsive breakpoints; ensure mobile nav wraps.
- Test one frontend first (`plotxyz-incident-responder-agent`) before building all 50.

### D. Mock provider + tests
Create `agentforge-40/tools/mock_provider.py`:
- stdlib `ThreadingHTTPServer`.
- `GET /health` → `{"status":"ok"}`
- `GET /v1/models` → model list.
- `POST /v1/chat/completions`:
  - If the prompt asks for JSON, return a valid JSON string with
    `summary/insights/recommendations/risks/confidence`.
  - Otherwise return `{"choices":[{"message":{"role":"assistant","content":"ready"}}]}`.
- `POST /api/experimental/generate`:
  - Return `{"data":{"text":"..."}}` with the same mock content.
- Accept `--port` (default `8765`).

Create `agentforge-40/tools/fake_opencode.py` (optional):
- Mimics `opencode api post /api/experimental/generate --data <json>`.
- Parses the `--data` argument and prints `{"data":{"text":"..."}}`.
- Used with:
  ```powershell
  $env:OPENCODE_BIN = '["python","C:\\...\\tools\\fake_opencode.py"]'
  $env:LLM_PROVIDER = 'opencode-local'
  ```

Integration test plan:
1. Start mock provider on `127.0.0.1:8765`.
2. For each repo, run pytest with:
   ```powershell
   $env:LLM_PROVIDER = 'opencode'
   $env:OPENCODE_BASE_URL = 'http://127.0.0.1:8765/v1'
   $env:OPENCODE_API_KEY = 'test-key'
   $env:OPENCODE_MODEL = 'mock-model'
   ```
3. Assert all tests pass and the env-gated test sees `ai.enabled = true`.
4. Repeat one repo with `LLM_PROVIDER=opencode-local` and the fake CLI.
5. Run one repo with no provider env to confirm deterministic mode still passes.
6. Run all 50 frontend builds.
7. Do not claim a live OpenCode call succeeded; note the free-quota limitation.

### E. README enhancement
- The external script `C:\Users\HP\AppData\Local\Temp\opencode\enhance_readmes.py` exists but has a `$0## Contents` artifact risk.
- Prefer a new idempotent `agentforge-40/enhance_readmes.py` that:
  - Adds SVG hero + badges.
  - Adds `## Contents` TOC (no `$0`).
  - Adds `## Quick start` after section 2.
  - Replaces the screenshots section with a useful table + placeholder.
  - Adds a Troubleshooting table before section 14.
  - Does not overwrite the API example (build.py will already include `ai`).
  - Skips if `## Quick start` already exists.
- Run it after `build.py` and before git commit.
- Verify all 50 READMEs contain `## Quick start` and OpenCode env docs.

### F. Git re-init + push strategy
Each project currently has no `.git`. For each slug:
```powershell
git -C <project> init -b main
git -C <project> config user.name "sukhee-2626"
git -C <project> config user.email "sukhee-2626@users.noreply.github.com"
git -C <project> remote add origin "https://github.com/sukhee-2626/<slug>.git"
git -C <project> fetch origin main
git -C <project> update-ref refs/heads/main FETCH_HEAD
git -C <project> reset --mixed FETCH_HEAD   # keep working tree, index = remote
git -C <project> add -A
git -C <project> commit -m "feat: add OpenCode/OpenAI provider, AI narrative, UI polish, tests"
git -C <project> push origin main
```
Notes:
- `reset --mixed` preserves the regenerated working tree while making the commit a normal fast-forward on top of remote `main`.
- If fetch fails, retry; do not force-push unless necessary.
- Token retrieval (never print):
  ```powershell
  $cred = "protocol=https`nhost=github.com`n`n" | git credential fill 2>$null
  $token = (($cred | Where-Object { $_ -like 'password=*' }) -replace '^password=', '')
  ```
- GitHub API headers: `Authorization: token <token>`, `User-Agent: opencode`, `Accept: application/vnd.github+json`.
- `gh` CLI is not installed.
- Network was intermittent; process repos in small batches and log results.
- After pushing, verify a sample with:
  ```powershell
  Invoke-WebRequest "https://raw.githubusercontent.com/sukhee-2626/<slug>/main/README.md"
  ```
  and check for `## Quick start`.

### G. Update inventory
- Update `manifest.json` with:
  - `tests: "passed"` (and count)
  - `build: "passed"`
  - `published: true`
  - `url: "https://github.com/sukhee-2626/<slug>"`
  - `readme_enhanced: true`
  - `ai_provider: "opencode-compatible"`
- Update `PROGRESS.md` with the same status.
- Produce a final 50-row table: `# | Agent | GitHub URL | Backend tests | Frontend build | README | AI provider`.

---

## 5. Exact resume checklist (tomorrow)

1. [ ] Inspect `agentforge-40/.git` and the root `C:\Users\HP\todo-app\.git`; fix the `git status` error.
2. [ ] Create `templates/provider.py`.
3. [ ] Update `build.py` (provider file, imports, `/api/provider/test`, `ai`, docs, env, tests).
4. [ ] Update `templates/App.tsx` and `templates/styles.css`.
5. [ ] Create `tools/mock_provider.py` and `tools/fake_opencode.py`.
6. [ ] Run `python build.py` (50/50).
7. [ ] Run `python enhance_readmes.py`.
8. [ ] Test one backend with no provider (deterministic).
9. [ ] Test one backend with the mock OpenCode HTTP provider.
10. [ ] Test one backend with `opencode-local` + fake CLI.
11. [ ] Run all 50 backend test suites with the mock provider.
12. [ ] `npm install` + `npm run build` for all 50 frontends (batches; cache warm).
13. [ ] Verify all READMEs have `## Quick start`.
14. [ ] Re-init git, commit, push all 50.
15. [ ] Verify a sample of raw GitHub READMEs and CI runs.
16. [ ] Update `manifest.json` and `PROGRESS.md`.
17. [ ] Deliver the final 50-agent list with URLs and test results.

---

## 6. Important cautions

- **Do not run `build.py` casually.** It deletes `projects/` and wipes `.git`, `node_modules`, and README enhancements.
- Current project `.git` dirs are already gone, so a rebuild is acceptable once the templates are ready.
- Do not print or commit API keys, tokens, `.env` files, `node_modules`, `dist`, or `backend/data`.
- Keep the deterministic path working without any key.
- Do not claim live AI results; the OpenCode free quota is exhausted in this environment.
- The `opencode` CLI is a PowerShell shim on Windows; use the `.exe` path or `subprocess.run` with a list.
- PowerShell `Select-Object -Join` is invalid; use `-join` on an array instead.
- Watch for stale `.git/index.lock` files if git commands hang.
- Network/DNS to GitHub was intermittent; retry pushes in small batches.

---

## 7. 50-agent inventory (slugs + titles)

| # | Slug | Title |
| --: | :-- | :-- |
| 1 | `plotxyz-device-intelligence-agent` | Device Intelligence |
| 2 | `plotxyz-offline-personal-agent` | Offline Personal |
| 3 | `plotxyz-resource-optimization-agent` | Resource Optimization |
| 4 | `plotxyz-local-model-benchmark-agent` | Local Model Benchmark |
| 5 | `plotxyz-privacy-audit-agent` | Privacy Audit |
| 6 | `plotxyz-model-router-agent` | Model Router |
| 7 | `plotxyz-local-knowledge-agent` | Local Knowledge |
| 8 | `plotxyz-computer-health-agent` | Computer Health |
| 9 | `plotxyz-self-healing-code-agent` | Self-Healing Code |
| 10 | `plotxyz-api-detective-agent` | API Detective |
| 11 | `plotxyz-autonomous-qa-agent` | Autonomous QA |
| 12 | `plotxyz-code-review-agent` | Code Review |
| 13 | `plotxyz-dependency-risk-agent` | Dependency Risk |
| 14 | `plotxyz-documentation-generator-agent` | Documentation Generator |
| 15 | `plotxyz-refactoring-agent` | Refactoring |
| 16 | `plotxyz-database-intelligence-agent` | Database Intelligence |
| 17 | `plotxyz-data-quality-guardian` | Data Quality Guardian |
| 18 | `plotxyz-etl-pipeline-agent` | ETL Pipeline |
| 19 | `plotxyz-csv-insights-agent` | CSV Insights |
| 20 | `plotxyz-schema-drift-agent` | Schema Drift |
| 21 | `plotxyz-data-lineage-agent` | Data Lineage |
| 22 | `plotxyz-sql-performance-agent` | SQL Performance |
| 23 | `plotxyz-data-documentation-agent` | Data Documentation |
| 24 | `plotxyz-anomaly-investigator-agent` | Anomaly Investigator |
| 25 | `plotxyz-knowledge-graph-agent` | Knowledge Graph |
| 26 | `plotxyz-document-to-action-agent` | Document to Action |
| 27 | `plotxyz-evidence-verification-agent` | Evidence Verification |
| 28 | `plotxyz-research-synthesis-agent` | Research Synthesis |
| 29 | `plotxyz-meeting-intelligence-agent` | Meeting Intelligence |
| 30 | `plotxyz-contract-review-assistant` | Contract Review |
| 31 | `plotxyz-knowledge-gap-agent` | Knowledge Gap |
| 32 | `plotxyz-citation-audit-agent` | Citation Audit |
| 33 | `plotxyz-adaptive-learning-agent` | Adaptive Learning |
| 34 | `plotxyz-communication-coach-agent` | Communication Coach |
| 35 | `plotxyz-startup-cofounder-agent` | Startup Co-founder |
| 36 | `plotxyz-workflow-builder-agent` | Workflow Builder |
| 37 | `plotxyz-multi-agent-project-manager` | Multi-Agent Project Manager |
| 38 | `plotxyz-digital-clutter-agent` | Digital Clutter |
| 39 | `plotxyz-ui-critic-agent` | UI Critic |
| 40 | `plotxyz-what-if-simulator-agent` | What-If Simulator |
| 41 | `plotxyz-cost-tracker-agent` | Cost Tracker |
| 42 | `plotxyz-token-analyzer-agent` | Token Analyzer |
| 43 | `plotxyz-prompt-optimizer-agent` | Prompt Optimizer |
| 44 | `plotxyz-dependency-update-agent` | Dependency Update |
| 45 | `plotxyz-config-validator-agent` | Config Validator |
| 46 | `plotxyz-secret-scanner-agent` | Secret Scanner |
| 47 | `plotxyz-performance-profiler-agent` | Performance Profiler |
| 48 | `plotxyz-compliance-checker-agent` | Compliance Checker |
| 49 | `plotxyz-deployment-readiness-agent` | Deployment Readiness |
| 50 | `plotxyz-incident-responder-agent` | Incident Responder |

All repos live at `https://github.com/sukhee-2626/<slug>`.

---

## 8. Useful commands

```powershell
# Build all 50 projects
cd C:\Users\HP\todo-app\agentforge-40
python build.py

# Backend tests (one repo)
cd projects\plotxyz-incident-responder-agent\backend
C:\Users\HP\todo-app\agentforge-40\.venv\Scripts\python.exe -m pytest -q

# Frontend build (one repo)
cd ..\frontend
npm install --no-audit --no-fund
npm run build

# Start backend
cd ..\backend
C:\Users\HP\todo-app\agentforge-40\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# Start frontend
cd ..\frontend
npm run dev

# Mock provider
C:\Users\HP\todo-app\agentforge-40\.venv\Scripts\python.exe C:\Users\HP\todo-app\agentforge-40\tools\mock_provider.py --port 8765
```

---

## 9. What to tell the user tomorrow

- The deterministic baseline is complete and works without keys.
- The provider layer will support OpenCode Console, generic OpenAI-compatible, Ollama, and local OpenCode.
- `.env` will auto-load; the user only needs to add a key and restart.
- Live OpenCode testing was blocked by the free-quota/credit limit in this environment; contract tests use a mock provider.
- All 50 repos will be rebuilt, tested, README-enhanced, and pushed.
- The final message will include the full 50-agent list with URLs and verified test/build status.
