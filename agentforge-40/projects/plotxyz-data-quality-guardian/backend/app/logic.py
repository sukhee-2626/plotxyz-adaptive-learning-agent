"""Original deterministic implementation for Data Quality Guardian (plotxyz-data-quality-guardian)."""
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


def agent_data_quality_guardian(payload):
    columns, rows = _csv(payload, "csv")
    findings, table = [], []
    duplicate_keys = Counter(tuple(row[col] for col in columns) for row in rows)
    duplicate_rows = sum(count - 1 for count in duplicate_keys.values() if count > 1)
    total_missing = 0
    for column in columns:
        values = [row[column] for row in rows]
        non_empty = [v for v in values if v != ""]
        missing = len(values) - len(non_empty)
        total_missing += missing
        unique = len(set(non_empty))
        inferred, invalid = "text", 0
        if non_empty:
            sample = non_empty[:200]
            if all(re.fullmatch(r"-?\d+", v) for v in sample):
                inferred = "integer"
                invalid = sum(1 for v in non_empty if not re.fullmatch(r"-?\d+", v))
            elif all(re.fullmatch(r"-?\d+(\.\d+)?", v) for v in sample):
                inferred = "number"
                invalid = sum(1 for v in non_empty if not re.fullmatch(r"-?\d+(\.\d+)?", v))
            elif all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) for v in sample):
                inferred = "date"
                invalid = sum(1 for v in non_empty if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v))
            elif all(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v) for v in sample):
                inferred = "email"
                invalid = sum(1 for v in non_empty if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v))
        missing_rate = missing / len(rows)
        invalid_rate = invalid / max(1, len(non_empty))
        if missing_rate > 0.2:
            findings.append({"title": "High missing rate", "severity": "high" if missing_rate > 0.5 else "medium", "detail": f"Column '{column}' is {missing_rate:.0%} empty."})
        if invalid_rate > 0:
            findings.append({"title": "Invalid values", "severity": "medium", "detail": f"Column '{column}' has {invalid} value(s) that do not match inferred type {inferred}."})
        table.append([column, missing, f"{missing_rate:.0%}", unique, inferred, invalid])
    duplicate_rate = duplicate_rows / max(1, len(rows))
    if duplicate_rows:
        findings.append({"title": "Duplicate rows", "severity": "medium", "detail": f"{duplicate_rows} duplicate row(s) detected."})
    score = max(0, round(100 - (total_missing / max(1, len(rows) * len(columns))) * 40 - duplicate_rate * 30 - len([f for f in findings if f["title"] == "Invalid values"]) * 5))
    return _result(
        f"Quality score {score}/100 across {len(rows)} rows and {len(columns)} columns.",
        {
            "metrics": {"score": score, "rows": len(rows), "columns": len(columns), "duplicate_rows": duplicate_rows, "missing_cells": total_missing},
            "table": {"columns": ["Column", "Missing", "Missing %", "Unique", "Inferred type", "Invalid"], "rows": table},
            "findings": findings,
        },
        ["Type inference uses the first 200 non-empty values per column; review edge cases before loading."],
    )


run = agent_data_quality_guardian
