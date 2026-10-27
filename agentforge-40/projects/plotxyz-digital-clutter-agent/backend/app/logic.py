"""Original deterministic implementation for Digital Clutter (plotxyz-digital-clutter-agent)."""
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


def agent_digital_clutter(payload):
    columns, rows = _csv(payload, "files")
    required = {"path", "size"}
    if not required.issubset(set(columns)):
        raise LogicError("files CSV needs 'path' and 'size' columns")
    entries = []
    for row in rows:
        path = row.get("path", "")
        if not path:
            continue
        try:
            size = int(float(row.get("size", 0) or 0))
        except ValueError:
            raise LogicError(f"invalid size for '{path}'")
        entries.append({"path": path, "size": max(0, size), "hash": row.get("hash", "").strip()})
    if not entries:
        raise LogicError("no usable file entries were found")
    groups = defaultdict(list)
    for entry in entries:
        if entry["hash"]:
            key = ("hash", entry["hash"])
        else:
            stem = re.sub(r"(?i)(?:\s*[-_ ]?copy(?: \(\d+\))?|\s*\(\d+\))$", "", re.sub(r"\.[^.]+$", "", entry["path"].split("/")[-1].split("\\")[-1]))
            key = ("name", entry["size"], stem.lower())
        groups[key].append(entry)
    duplicate_rows, duplicate_groups, reclaimable = [], [], 0
    for key, items in groups.items():
        if len(items) < 2:
            continue
        duplicate_groups.append(items)
        extra = sum(item["size"] for item in items[1:])
        reclaimable += extra
        duplicate_rows.append([items[0]["path"], len(items), round(sum(i["size"] for i in items) / 1024, 1), round(extra / 1024, 1), key[0]])
    categories = {".jpg": "Images", ".jpeg": "Images", ".png": "Images", ".gif": "Images", ".pdf": "Documents", ".doc": "Documents", ".docx": "Documents", ".xls": "Documents", ".xlsx": "Documents", ".mp4": "Video", ".mov": "Video", ".mp3": "Audio", ".wav": "Audio", ".zip": "Archives", ".rar": "Archives", ".py": "Code", ".js": "Code", ".ts": "Code", ".json": "Code"}
    plan = Counter()
    for entry in entries:
        extension = ("." + entry["path"].rsplit(".", 1)[-1].lower()) if "." in entry["path"] else ""
        plan[categories.get(extension, "Other")] += 1
    plan_rows = [[category, count, f"{category}/"] for category, count in plan.most_common()]
    findings = []
    if duplicate_groups:
        findings.append({"title": "Duplicate files found", "severity": "medium", "detail": f"{len(duplicate_groups)} duplicate group(s); about {reclaimable / (1024 * 1024):.2f} MB could be reclaimed."})
    else:
        findings.append({"title": "No duplicates detected", "severity": "info", "detail": "No hash or size/name duplicate groups were found."})
    return _result(
        f"Found {len(duplicate_groups)} duplicate group(s); {reclaimable / (1024 * 1024):.2f} MB potentially reclaimable. No files were changed.",
        {
            "metrics": {"files": len(entries), "duplicate_groups": len(duplicate_groups), "reclaimable_mb": round(reclaimable / (1024 * 1024), 2)},
            "table": {"columns": ["Representative", "Copies", "Total KB", "Reclaimable KB", "Match basis"], "rows": duplicate_rows},
            "items": [f"{category}: move {count} file(s) to {category}/" for category, count, _ in plan_rows],
            "findings": findings,
        },
        ["Preview only. This agent never deletes, moves, or writes files; confirm before changing anything."],
    )


run = agent_digital_clutter
