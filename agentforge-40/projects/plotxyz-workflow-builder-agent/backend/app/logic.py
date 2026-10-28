"""Original deterministic implementation for Workflow Builder (plotxyz-workflow-builder-agent)."""
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


def agent_workflow_builder(payload):
    data = _json(payload, "data")
    workflow = _json(payload, "workflow", list)
    if not workflow:
        raise LogicError("'workflow' must contain at least one step")
    if len(workflow) > 50:
        raise LogicError("workflow is limited to 50 steps")

    def get_path(document, path):
        current = document
        for part in str(path).split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
            else:
                raise LogicError(f"path not found: {path}")
        return current

    def set_path(document, path, value):
        parts = str(path).split(".")
        current = document
        for part in parts[:-1]:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                raise LogicError(f"path not found: {path}")
        if not isinstance(current, dict):
            raise LogicError(f"cannot set path: {path}")
        current[parts[-1]] = value

    log = []
    for index, step in enumerate(workflow, 1):
        if not isinstance(step, dict) or "op" not in step:
            raise LogicError(f"step {index} must be an object with an 'op'")
        op = str(step["op"]).lower()
        try:
            if op == "set":
                set_path(data, step.get("path", ""), step.get("value"))
            elif op in {"uppercase", "lowercase"}:
                path = step.get("path", "")
                value = get_path(data, path)
                if not isinstance(value, str):
                    raise LogicError("value is not a string")
                set_path(data, path, value.upper() if op == "uppercase" else value.lower())
            elif op == "replace":
                path = step.get("path", "")
                value = get_path(data, path)
                if not isinstance(value, str):
                    raise LogicError("value is not a string")
                set_path(data, path, value.replace(str(step.get("find", "")), str(step.get("replace", ""))))
            elif op == "extract":
                set_path(data, step.get("as", "result"), get_path(data, step.get("path", "")))
            elif op == "append":
                path = step.get("path", "")
                value = get_path(data, path)
                if not isinstance(value, list):
                    raise LogicError("value is not a list")
                value.append(step.get("value"))
            elif op == "multiply":
                path = step.get("path", "")
                value = get_path(data, path)
                set_path(data, path, float(value) * float(step.get("factor", 1)))
            elif op == "filter":
                path = step.get("path", "")
                items = get_path(data, path)
                if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
                    raise LogicError("filter target must be a list of objects")
                field = str(step.get("field", ""))
                comparator = str(step.get("op_type", "eq")).lower()
                target = step.get("value")
                if comparator == "eq":
                    kept = [item for item in items if item.get(field) == target]
                elif comparator == "ne":
                    kept = [item for item in items if item.get(field) != target]
                elif comparator == "contains":
                    kept = [item for item in items if str(target).lower() in str(item.get(field, "")).lower()]
                elif comparator in {"gt", "lt"}:
                    kept = []
                    for item in items:
                        try:
                            left, right = float(item.get(field)), float(target)
                        except (TypeError, ValueError):
                            continue
                        if (comparator == "gt" and left > right) or (comparator == "lt" and left < right):
                            kept.append(item)
                else:
                    raise LogicError(f"unsupported filter comparison '{comparator}'")
                set_path(data, path, kept)
            else:
                raise LogicError(f"unsupported op '{op}'")
            log.append([index, op, "ok", ""])
        except LogicError as exc:
            log.append([index, op, "failed", str(exc)])
            raise LogicError(f"step {index} ({op}): {exc}")
    return _result(
        f"Executed {len(workflow)} workflow step(s) with allowlisted operations.",
        {
            "metrics": {"steps": len(workflow), "succeeded": sum(1 for row in log if row[2] == "ok")},
            "table": {"columns": ["Step", "Op", "Status", "Detail"], "rows": log},
            "data": data,
            "items": ["Workflow used only in-memory set/transform/filter operations; no shell or HTTP calls are available."],
        },
        ["Inspect the output data before using it downstream. Workflow operations are intentionally limited."],
    )


run = agent_workflow_builder
