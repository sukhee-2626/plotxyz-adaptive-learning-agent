"""Original deterministic implementation for Multi-Agent Project Manager (plotxyz-multi-agent-project-manager)."""
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


class LogicError(ValueError):
    """Raised when supplied input cannot be processed."""


def _text(payload, key, min_len=1, max_len=20000):
    value = payload.get(key)
    if not isinstance(value, str):
        raise LogicError(f"'{key}' must be a string")
    value = value.strip()
    if len(value) < min_len:
        raise LogicError(f"'{key}' is required")
    if len(value) > max_len:
        raise LogicError(f"'{key}' exceeds {max_len} characters")
    return value


def _num(payload, key, default=None, lo=None, hi=None):
    value = payload.get(key, default)
    if value is None or value == "":
        if default is None:
            raise LogicError(f"'{key}' is required")
        return default
    if isinstance(value, bool):
        raise LogicError(f"'{key}' must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise LogicError(f"'{key}' must be numeric")
    if lo is not None and number < lo:
        raise LogicError(f"'{key}' must be at least {lo}")
    if hi is not None and number > hi:
        raise LogicError(f"'{key}' must be at most {hi}")
    return number


def _json(payload, key, expected=None, max_len=200000):
    raw = payload.get(key)
    if isinstance(raw, (dict, list)):
        data = raw
    elif isinstance(raw, str):
        if len(raw) > max_len:
            raise LogicError(f"'{key}' exceeds {max_len} characters")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LogicError(f"'{key}' is not valid JSON: {exc.msg} at line {exc.lineno}")
    else:
        raise LogicError(f"'{key}' must be JSON")
    if expected is not None and not isinstance(data, expected):
        name = expected.__name__ if hasattr(expected, "__name__") else str(expected)
        raise LogicError(f"'{key}' must be a JSON {name}")
    return data


def _csv(payload, key, max_rows=5000):
    text = _text(payload, key, max_len=2000000)
    try:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise LogicError(f"'{key}' must include a header row")
        columns = [str(c).strip() for c in reader.fieldnames if c and str(c).strip()]
        if not columns:
            raise LogicError(f"'{key}' must include named columns")
        rows = []
        for index, raw in enumerate(reader):
            if index >= max_rows:
                raise LogicError(f"'{key}' exceeds {max_rows} rows")
            rows.append({col: (raw.get(col) or "").strip() for col in columns})
    except csv.Error as exc:
        raise LogicError(f"'{key}' is not valid CSV: {exc}")
    if not rows:
        raise LogicError(f"'{key}' must include at least one data row")
    return columns, rows


STOPWORDS = {'and', 'could', 'is', 'from', 'does', 'your', 'in', 'you', 'to', 'not', 'be', 'we', 'than', 'over', 'did', 'have', 'of', 'no', 'then', 'they', 'at', 'the', 'he', 'into', 'had', 'it', 'would', 'for', 'can', 'its', 'i', 'this', 'our', 'are', 'as', 'an', 'might', 'were', 'under', 'about', 'on', 'that', 'if', 'with', 'was', 'a', 'by', 'should', 'may', 'or', 'will', 'do', 'has', 'she', 'their'}


def _tokens(text):
    return [w for w in re.findall(r"[a-z0-9][a-z0-9_+-]{1,}", text.lower()) if w not in STOPWORDS]


def _sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip(" -•\t") for p in parts if len(p.strip()) > 2]


def provider_status():
    """Report which optional model providers are configured (never exposes secrets)."""
    ollama = bool(os.getenv("OLLAMA_BASE_URL"))
    openai = bool(os.getenv("OPENAI_BASE_URL") and os.getenv("OPENAI_MODEL"))
    return {"ollama_compatible": ollama, "openai_compatible": openai}


def _llm(messages, temperature=0.2):
    """Call an explicitly configured OpenAI-compatible endpoint; return None when unavailable."""
    base = os.getenv("OPENAI_BASE_URL", "").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "")
    if not base or not model:
        ollama = os.getenv("OLLAMA_BASE_URL", "").rstrip("/")
        if not ollama:
            return None
        base = f"{ollama}/v1"
        model = os.getenv("OLLAMA_MODEL", "")
    if not model:
        return None
    try:
        import httpx

        headers = {"Content-Type": "application/json"}
        key = os.getenv("OPENAI_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        with httpx.Client(timeout=20) as client:
            response = client.post(
                f"{base}/chat/completions",
                headers=headers,
                json={"model": model, "messages": messages, "temperature": temperature},
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"]).strip()
    except Exception:
        return None


def _result(summary, result, warnings=None):
    return {"summary": summary, "result": result, "warnings": warnings or []}


def agent_multi_agent_project_manager(payload):
    brief = _text(payload, "brief", max_len=8000)
    tasks_text = _text(payload, "tasks", max_len=20000)
    team_size = int(_num(payload, "team_size", default=3, lo=1, hi=50))
    deadline = int(_num(payload, "deadline_days", default=10, lo=1, hi=365))
    tasks = [line.strip(" -•") for line in tasks_text.splitlines() if line.strip()]
    if not tasks:
        raise LogicError("supply at least one task")
    tasks = tasks[:40]

    def planner(task):
        lowered = task.lower()
        if any(word in lowered for word in ("research", "interview", "discover", "spec")):
            return "Discovery"
        if any(word in lowered for word in ("design", "mock", "prototype", "architecture")):
            return "Design"
        if any(word in lowered for word in ("test", "qa", "review", "audit")):
            return "Validation"
        if any(word in lowered for word in ("launch", "deploy", "release", "migrate")):
            return "Launch"
        return "Build"

    def estimator(task):
        days = 1 + min(len(task) / 60, 2)
        lowered = task.lower()
        for keyword, extra in (("integration", 2), ("migration", 3), ("security", 2), ("payment", 2), ("auth", 1.5)):
            if keyword in lowered:
                days += extra
        return round(min(10, days), 1)

    def risk_handler(task):
        lowered = task.lower()
        flags = []
        if any(word in lowered for word in ("auth", "payment", "security")):
            flags.append("security-sensitive")
        if any(word in lowered for word in ("migration", "legacy")):
            flags.append("data-migration")
        if any(word in lowered for word in ("third-party", "vendor", "external")):
            flags.append("external dependency")
        return flags

    def reviewer(task):
        phase = planner(task)
        return {
            "Discovery": "Acceptance: problem statement, user segment, and success metric agreed.",
            "Design": "Acceptance: reviewed flow, edge cases, and accessibility notes.",
            "Build": "Acceptance: tests pass, error states covered, and docs updated.",
            "Validation": "Acceptance: risks tested, regressions checked, and sign-off recorded.",
            "Launch": "Acceptance: rollback plan, monitoring, and owner on call.",
        }[phase]

    rows, findings = [], []
    total_estimate = 0
    for task in tasks:
        phase = planner(task)
        estimate = estimator(task)
        total_estimate += estimate
        flags = risk_handler(task)
        rows.append([task[:180], phase, estimate, flags[0] if flags else "none", reviewer(task)])
        for flag in flags:
            findings.append({"title": f"{flag.title()} task", "severity": "medium", "detail": task[:140]})
    capacity = team_size * deadline
    feasible = total_estimate <= capacity
    if not feasible:
        findings.append({"title": "Plan exceeds capacity", "severity": "high", "detail": f"Estimated {total_estimate:.1f} person-days against {capacity} available person-days. Cut scope or extend the deadline."})
    markdown = f"""## Delivery plan

**Brief:** {brief}

**Team:** {team_size} people · **Deadline:** {deadline} days · **Estimated effort:** {total_estimate:.1f} person-days · **Capacity:** {capacity} person-days

### Delegation table
| Task | Phase | Estimate | Risk | Acceptance |
| :-- | :-- | --: | :-- | :-- |
""" + "\n".join(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |" for r in rows) + """

### Recommendation
""" + ("The plan fits within capacity; keep a 15% buffer for review and rework." if feasible else "The plan does not fit. Remove P2 scope or extend the deadline before committing.")
    return _result(
        f"Delegated {len(tasks)} task(s) across {team_size} people; estimated {total_estimate:.1f} person-days against {capacity} available.",
        {
            "metrics": {"tasks": len(tasks), "estimate_days": round(total_estimate, 1), "capacity_days": capacity, "feasible": feasible},
            "table": {"columns": ["Task", "Phase", "Estimate (days)", "Risk", "Acceptance"], "rows": rows},
            "markdown": markdown,
            "findings": findings,
        },
        ["Handlers are local deterministic rules; no external project-management system is modified."],
    )


run = agent_multi_agent_project_manager
