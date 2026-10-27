"""Original deterministic implementation for Refactoring (plotxyz-refactoring-agent)."""
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


def agent_refactoring(payload):
    code = _text(payload, "code", max_len=60000)
    focus = str(payload.get("focus", "readability")).lower()
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise LogicError(f"Python syntax error at line {exc.lineno}: {exc.msg}")
    issues, patches = [], []
    working = code
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            length = (node.end_lineno or node.lineno) - node.lineno + 1
            if length > 30:
                issues.append({"line": node.lineno, "title": "Long function", "severity": "medium", "detail": f"'{node.name}' is {length} lines; extract cohesive helpers."})
    if re.search(r"==\s*None\b", working):
        issues.append({"line": 0, "title": "None equality", "severity": "low", "detail": "Use 'is None'."})
        before = working
        working = re.sub(r"==\s*None\b", "is None", working)
        patches.append({"title": "Use identity comparison for None", "before": "\n".join(line for line in before.splitlines() if "== None" in line)[:400], "after": "\n".join(line for line in working.splitlines() if "is None" in line)[:400]})
    if re.search(r"len\((\w+)\)\s*==\s*0", working):
        issues.append({"line": 0, "title": "Explicit empty check", "severity": "low", "detail": "Prefer truthiness checks for empty containers."})
        before = working
        working = re.sub(r"len\((\w+)\)\s*==\s*0", r"not \1", working)
        patches.append({"title": "Use truthiness for empty checks", "before": "\n".join(line for line in before.splitlines() if "len(" in line and "== 0" in line)[:400], "after": "\n".join(line for line in working.splitlines() if line.strip().startswith("not "))[:400]})
    magic = re.findall(r"(?<![\w.])(\d{3,})(?![\w.])", working)
    if magic and focus in {"readability", "complexity"}:
        number = magic[0]
        issues.append({"line": 0, "title": "Magic number", "severity": "low", "detail": f"Replace {number} with a named constant."})
        constant = f"NAMED_VALUE_{number} = {number}"
        working = re.sub(rf"(?<![\w.]){re.escape(number)}(?![\w.])", f"NAMED_VALUE_{number}", working, count=1)
        working = constant + "\n\n" + working
        patches.append({"title": "Name a magic number", "before": f"... {number} ...", "after": f"{constant}\n... NAMED_VALUE_{number} ..."})
    try:
        ast.parse(working)
    except SyntaxError:
        working = code
        patches = []
    score = max(0, 100 - len(issues) * 7)
    return _result(
        f"Identified {len(issues)} refactoring opportunity(ies) with {len(patches)} validated patch(es).",
        {
            "metrics": {"issues": len(issues), "patches": len(patches), "score": score},
            "findings": [{"title": item["title"], "severity": item["severity"], "detail": item["detail"]} for item in issues],
            "patches": patches,
            "refactored_code": working,
            "table": {"columns": ["Line", "Issue", "Severity", "Detail"], "rows": [[i["line"], i["title"], i["severity"], i["detail"]] for i in issues]},
        },
        ["Refactoring suggestions preserve behavior only where the patch is syntactic; review and run tests before adopting."],
    )


run = agent_refactoring
