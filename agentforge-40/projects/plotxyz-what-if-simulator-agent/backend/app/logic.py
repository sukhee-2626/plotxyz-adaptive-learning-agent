"""Original deterministic implementation for What-If Simulator (plotxyz-what-if-simulator-agent)."""
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


STOPWORDS = {'could', 'than', 'your', 'does', 'in', 'have', 'you', 'is', 'they', 'then', 'will', 'it', 'of', 'their', 'are', 'about', 'should', 'into', 'not', 'were', 'would', 'no', 'as', 'from', 'had', 'may', 'a', 'i', 'for', 'he', 'can', 'over', 'under', 'the', 'our', 'to', 'might', 'she', 'be', 'do', 'has', 'an', 'if', 'this', 'at', 'by', 'that', 'we', 'and', 'with', 'its', 'did', 'was', 'or', 'on'}


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


def agent_what_if_simulator(payload):
    baseline = _json(payload, "baseline", dict)
    scenarios = _json(payload, "scenarios", list)
    if not scenarios:
        raise LogicError("supply at least one scenario")
    try:
        revenue = float(baseline.get("revenue", 0))
        growth = float(baseline.get("growth_rate_pct", 0))
        churn = float(baseline.get("churn_rate_pct", 0))
        margin = float(baseline.get("gross_margin_pct", 70))
        months = int(baseline.get("months", 12))
    except (TypeError, ValueError):
        raise LogicError("baseline values must be numeric")
    if revenue <= 0:
        raise LogicError("baseline.revenue must be positive")
    if not 1 <= months <= 36:
        raise LogicError("baseline.months must be between 1 and 36")
    clean = []
    for scenario in scenarios[:8]:
        if not isinstance(scenario, dict):
            raise LogicError("each scenario must be an object")
        name = str(scenario.get("name") or f"Scenario {len(clean) + 1}")
        try:
            clean.append({
                "name": name,
                "growth_delta": float(scenario.get("growth_delta_pct", 0)),
                "churn_delta": float(scenario.get("churn_delta_pct", 0)),
                "margin_delta": float(scenario.get("margin_delta_pct", 0)),
            })
        except (TypeError, ValueError):
            raise LogicError("scenario deltas must be numeric")
    projections = {}
    rows = []
    for month in range(1, months + 1):
        row = [month]
        for scenario in clean:
            effective_growth = (growth + scenario["growth_delta"]) / 100
            effective_churn = (churn + scenario["churn_delta"]) / 100
            value = revenue * ((1 + effective_growth) * (1 - effective_churn)) ** month
            effective_margin = max(0, min(100, margin + scenario["margin_delta"])) / 100
            projections.setdefault(scenario["name"], []).append(round(value, 2))
            row.append(round(value, 2))
        rows.append(row)
    chart = {"labels": [s["name"] for s in clean], "values": [projections[s["name"]][-1] for s in clean]}
    findings = []
    for scenario in clean:
        final = projections[scenario["name"]][-1]
        if final < revenue:
            findings.append({"title": f"{scenario['name']} declines", "severity": "medium", "detail": f"Projected revenue falls from {revenue:,.0f} to {final:,.0f} by month {months}."})
        if (growth + scenario["growth_delta"]) < (churn + scenario["churn_delta"]):
            findings.append({"title": "Churn exceeds growth", "severity": "high", "detail": f"{scenario['name']}: effective churn is higher than effective growth, so the base shrinks."})
    best = max(clean, key=lambda s: projections[s["name"]][-1]) if clean else None
    return _result(
        f"Projected {months} month(s) across {len(clean)} scenario(s); best final revenue: {best['name'] if best else 'none'}.",
        {
            "metrics": {"months": months, "scenarios": len(clean), "baseline_revenue": revenue, "best_final": projections[best["name"]][-1] if best else 0},
            "table": {"columns": ["Month"] + [s["name"] for s in clean], "rows": rows},
            "chart": chart,
            "items": [
                "Formula: revenue × ((1 + growth + scenario delta) × (1 − churn − scenario delta))^month.",
                "Gross margin is reported separately and does not change revenue.",
                "All assumptions are explicit in the supplied baseline and scenarios.",
            ],
            "findings": findings,
        },
        ["Deterministic arithmetic on your assumptions. This is not a forecast or financial advice."],
    )


run = agent_what_if_simulator
