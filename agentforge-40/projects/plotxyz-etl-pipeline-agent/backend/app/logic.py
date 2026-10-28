"""Original deterministic implementation for ETL Pipeline (plotxyz-etl-pipeline-agent)."""
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


def agent_etl_pipeline(payload):
    columns, rows = _csv(payload, "csv")
    steps = _json(payload, "pipeline", list)
    if not steps:
        raise LogicError("'pipeline' must contain at least one step")
    if len(steps) > 40:
        raise LogicError("'pipeline' is limited to 40 steps")
    data = [dict(row) for row in rows]
    log = []
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict) or "op" not in step:
            raise LogicError(f"step {index} must be an object with an 'op'")
        op = str(step["op"]).lower()
        before_count = len(data)
        if op == "rename":
            source, target = str(step.get("from", "")), str(step.get("to", ""))
            if source not in columns:
                raise LogicError(f"step {index}: column '{source}' not found")
            if target in columns:
                raise LogicError(f"step {index}: target column '{target}' already exists")
            for row in data:
                row[target] = row.pop(source)
            columns = [target if c == source else c for c in columns]
        elif op == "drop":
            names = step.get("columns", [])
            names = [names] if isinstance(names, str) else list(names)
            missing = [n for n in names if n not in columns]
            if missing:
                raise LogicError(f"step {index}: columns not found: {missing}")
            columns = [c for c in columns if c not in names]
            data = [{c: row[c] for c in columns} for row in data]
        elif op == "filter":
            column = str(step.get("column", ""))
            if column not in columns:
                raise LogicError(f"step {index}: column '{column}' not found")
            comparator = str(step.get("op_type", step.get("operator", "eq"))).lower()
            target = str(step.get("value", ""))
            def keep(value):
                if comparator == "eq":
                    return value == target
                if comparator == "ne":
                    return value != target
                if comparator == "contains":
                    return target.lower() in value.lower()
                try:
                    left, right = float(value), float(target)
                except ValueError:
                    return False
                return left > right if comparator == "gt" else left < right if comparator == "lt" else False
            data = [row for row in data if keep(row[column])]
        elif op == "cast":
            column = str(step.get("column", ""))
            kind = str(step.get("type", "str")).lower()
            if column not in columns:
                raise LogicError(f"step {index}: column '{column}' not found")
            if kind not in {"int", "float", "str", "lower", "upper"}:
                raise LogicError(f"step {index}: unsupported cast '{kind}'")
            try:
                for row in data:
                    if kind == "int":
                        row[column] = int(float(row[column] or 0))
                    elif kind == "float":
                        row[column] = float(row[column] or 0)
                    elif kind == "str":
                        row[column] = str(row[column])
                    elif kind == "lower":
                        row[column] = row[column].lower()
                    else:
                        row[column] = row[column].upper()
            except ValueError:
                raise LogicError(f"step {index}: values in '{column}' cannot be cast to {kind}")
        elif op == "fillna":
            column = str(step.get("column", ""))
            if column not in columns:
                raise LogicError(f"step {index}: column '{column}' not found")
            value = str(step.get("value", ""))
            for row in data:
                if row[column] == "":
                    row[column] = value
        elif op == "aggregate":
            group = step.get("group_by", [])
            group = [group] if isinstance(group, str) else list(group)
            column = str(step.get("column", ""))
            operation = str(step.get("operation", "sum")).lower()
            if any(g not in columns for g in group) or column not in columns:
                raise LogicError(f"step {index}: aggregate references a missing column")
            if operation not in {"sum", "mean", "count", "min", "max"}:
                raise LogicError(f"step {index}: unsupported aggregate '{operation}'")
            buckets = defaultdict(list)
            for row in data:
                buckets[tuple(row[g] for g in group)].append(row[column])
            new_rows = []
            for key, values in buckets.items():
                numbers = []
                for value in values:
                    try:
                        numbers.append(float(value))
                    except ValueError:
                        pass
                if operation == "count":
                    result_value = len(values)
                elif not numbers:
                    result_value = 0
                elif operation == "sum":
                    result_value = sum(numbers)
                elif operation == "mean":
                    result_value = sum(numbers) / len(numbers)
                elif operation == "min":
                    result_value = min(numbers)
                else:
                    result_value = max(numbers)
                row = dict(zip(group, key))
                row[f"{column}_{operation}"] = round(result_value, 3) if isinstance(result_value, float) else result_value
                new_rows.append(row)
            data = new_rows
            columns = group + [f"{column}_{operation}"]
        else:
            raise LogicError(f"step {index}: unsupported op '{op}'")
        log.append([index, op, before_count, len(data), "ok"])
    output_rows = [[row.get(c, "") for c in columns] for row in data[:100]]
    return _result(
        f"Executed {len(steps)} pipeline step(s); {len(rows)} input rows became {len(data)} output rows.",
        {
            "metrics": {"input_rows": len(rows), "output_rows": len(data), "steps": len(steps)},
            "table": {"columns": columns, "rows": output_rows},
            "items": [f"Step {entry[0]}: {entry[1]} ({entry[2]} -> {entry[3]} rows)" for entry in log],
            "markdown": "## Pipeline log\n\n" + "\n".join(f"{e[0]}. `{e[1]}` — {e[2]} → {e[3]} rows" for e in log),
        },
        ["Pipeline runs in memory and does not write to external systems. Output is capped at 100 preview rows."],
    )


run = agent_etl_pipeline
