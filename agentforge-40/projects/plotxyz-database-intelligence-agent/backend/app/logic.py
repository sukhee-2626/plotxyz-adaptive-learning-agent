"""Original deterministic implementation for Database Intelligence (plotxyz-database-intelligence-agent)."""
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


def agent_database_intelligence(payload):
    ddl = _text(payload, "ddl", max_len=80000)
    workload = str(payload.get("workload", "")).strip()
    tables = []
    for match in re.finditer(r"create\s+table\s+(?:if\s+not\s+exists\s+)?([`\"\[]?[\w.]+[`\"\]]?)\s*\((.*?)\)\s*;", ddl, re.I | re.S):
        name = match.group(1).strip("`\"[]")
        body = match.group(2)
        parts, buf, depth = [], "", 0
        for char in body:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            if char == "," and depth == 0:
                parts.append(buf.strip())
                buf = ""
            else:
                buf += char
        if buf.strip():
            parts.append(buf.strip())
        columns, pk = [], False
        for part in parts:
            lowered = part.lower()
            if lowered.startswith(("primary key", "constraint", "foreign key", "unique")):
                if "primary key" in lowered:
                    pk = True
                continue
            token = part.split()[0].strip("`\"[]")
            col_type = " ".join(part.split()[1:3]) or "unknown"
            if "primary key" in lowered:
                pk = True
            columns.append({"name": token, "type": col_type})
        tables.append({"name": name, "columns": columns, "primary_key": pk})
    if not tables:
        raise LogicError("no CREATE TABLE statements were found")
    indexes = []
    for match in re.finditer(r"create\s+(unique\s+)?index\s+(\w+)\s+on\s+([`\"\[]?[\w.]+[`\"\]]?)\s*\(([^)]+)\)", ddl, re.I):
        indexes.append({"name": match.group(2), "table": match.group(3).strip("`\"[]"), "columns": [c.strip().strip("`\"[]") for c in match.group(4).split(",")], "unique": bool(match.group(1))})
    indexed = {(index["table"], column) for index in indexes for column in index["columns"]}
    where_columns = re.findall(r"\bwhere\s+([\w.]+)", workload, re.I)
    findings, suggestions = [], []
    rows = []
    for table in tables:
        if not table["primary_key"]:
            findings.append({"title": "Missing primary key", "severity": "medium", "detail": f"Table '{table['name']}' has no detected primary key."})
        for column in table["columns"]:
            rows.append([table["name"], column["name"], column["type"], "yes" if table["primary_key"] and "primary key" in column["type"].lower() else "no", "yes" if (table["name"], column["name"]) in indexed else "no"])
            if column["name"].endswith("_id") and (table["name"], column["name"]) not in indexed:
                suggestions.append(f"CREATE INDEX idx_{table['name']}_{column['name']} ON {table['name']} ({column['name']});")
                findings.append({"title": "Unindexed foreign-key-like column", "severity": "low", "detail": f"{table['name']}.{column['name']} may benefit from an index if used in joins."})
        for where in where_columns:
            base = where.split(".")[-1]
            if any(column["name"] == base for column in table["columns"]) and (table["name"], base) not in indexed:
                statement = f"CREATE INDEX idx_{table['name']}_{base} ON {table['name']} ({base});"
                if statement not in suggestions:
                    suggestions.append(statement)
    markdown = "## Suggested indexes\n\n" + ("\n".join(f"```sql\n{s}\n```" for s in suggestions) if suggestions else "No index suggestions.")
    return _result(
        f"Analyzed {len(tables)} table(s), {sum(len(t['columns']) for t in tables)} columns, and {len(indexes)} index(es).",
        {
            "metrics": {"tables": len(tables), "columns": sum(len(t["columns"]) for t in tables), "indexes": len(indexes), "suggestions": len(suggestions)},
            "table": {"columns": ["Table", "Column", "Type", "PK", "Indexed"], "rows": rows},
            "findings": findings,
            "markdown": markdown,
        },
        ["DDL parsing is regex-based; validate against your database engine before applying changes."],
    )


run = agent_database_intelligence
