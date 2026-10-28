"""Original deterministic implementation for SQL Performance (plotxyz-sql-performance-agent)."""
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


def agent_sql_performance(payload):
    explain = _text(payload, "explain", max_len=60000)
    query = str(payload.get("query", "")).strip()
    node_pattern = re.compile(r"\b(Seq Scan|Index Scan|Index Only Scan|Bitmap Heap Scan|Nested Loop|Hash Join|Merge Join|Sort|Aggregate|Limit|CTE Scan)\b", re.I)
    cost_pattern = re.compile(r"cost=(\d+(?:\.\d+)?)\.\.(\d+(?:\.\d+)?)")
    rows_pattern = re.compile(r"rows=(\d+)")
    nodes, findings = [], []
    for line in explain.splitlines():
        match = node_pattern.search(line)
        if not match:
            continue
        cost_match = cost_pattern.search(line)
        rows_match = rows_pattern.search(line)
        cost = float(cost_match.group(2)) if cost_match else None
        estimate = int(rows_match.group(1)) if rows_match else None
        kind = match.group(1)
        issue = "-"
        if kind.lower() == "seq scan" and (estimate is None or estimate > 1000):
            issue = "large sequential scan"
            findings.append({"title": "Sequential scan on a large relation", "severity": "high", "detail": f"Plan reports a Seq Scan with estimated rows {estimate}. Consider a selective index."})
        elif kind.lower() == "nested loop" and estimate and estimate > 10000:
            issue = "high-row nested loop"
            findings.append({"title": "Expensive nested loop", "severity": "medium", "detail": f"Nested loop estimates {estimate} rows; verify join indexes and statistics."})
        elif kind.lower() == "sort" and "external" in line.lower():
            issue = "external sort"
            findings.append({"title": "External sort", "severity": "medium", "detail": "Increase work_mem or reduce the sorted row count."})
        elif kind.lower() in {"hash join", "merge join"} and cost and cost > 100000:
            issue = "high-cost join"
            findings.append({"title": "High-cost join", "severity": "medium", "detail": f"Join cost reaches {cost:g}; inspect cardinality estimates."})
        nodes.append([kind, round(cost, 2) if cost is not None else "-", estimate if estimate is not None else "-", issue])
    if not nodes:
        findings.append({"title": "No recognized plan nodes", "severity": "info", "detail": "The supplied text does not contain common EXPLAIN node names."})
    seq_scans = sum(1 for node in nodes if node[0].lower() == "seq scan")
    score = max(0, 100 - seq_scans * 12 - len([f for f in findings if f["severity"] == "high"]) * 10 - len([f for f in findings if f["severity"] == "medium"]) * 5)
    suggestions = []
    if seq_scans:
        suggestions.append("Add or adjust indexes for predicates that filter many rows.")
    if "order by" in (query + explain).lower():
        suggestions.append("Consider an index matching the ORDER BY columns to avoid a sort.")
    suggestions += ["Refresh table statistics after large data changes.", "Compare estimated rows with actual rows to detect stale statistics."]
    return _result(
        f"Plan review score {score}/100 across {len(nodes)} recognized node(s).",
        {
            "metrics": {"score": score, "seq_scans": seq_scans, "nodes": len(nodes)},
            "table": {"columns": ["Node", "Total cost", "Estimated rows", "Issue"], "rows": nodes},
            "findings": findings,
            "items": suggestions,
        },
        ["This analyzes supplied EXPLAIN text; it does not connect to or modify a database."],
    )


run = agent_sql_performance
