"""Original deterministic implementation for Anomaly Investigator (plotxyz-anomaly-investigator-agent)."""
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


def agent_anomaly_investigator(payload):
    columns, rows = _csv(payload, "csv")
    column = str(payload.get("column", "")).strip()
    if not column:
        for candidate in columns:
            values = []
            for row in rows:
                try:
                    values.append(float(row[candidate]))
                except ValueError:
                    pass
            if len(values) >= 5:
                column = candidate
                break
    if column not in columns:
        raise LogicError("a numeric column could not be determined; supply 'column'")
    values, indices = [], []
    for index, row in enumerate(rows):
        try:
            values.append(float(row[column]))
            indices.append(index)
        except ValueError:
            continue
    if len(values) < 5:
        raise LogicError("at least five numeric values are required")
    mean = statistics.fmean(values)
    stdev = statistics.pstdev(values) or 1
    ordered = sorted(values)
    q1 = ordered[int(0.25 * (len(ordered) - 1))]
    q3 = ordered[int(0.75 * (len(ordered) - 1))]
    iqr = q3 - q1
    anomalies = []
    for position, (index, value) in enumerate(zip(indices, values)):
        z = (value - mean) / stdev
        if abs(z) >= 2.5 or value < q1 - 1.5 * iqr or value > q3 + 1.5 * iqr:
            anomalies.append([index, round(value, 3), round(z, 2), "high" if z > 0 else "low"])
    explanations = []
    if anomalies:
        anomaly_positions = [int(item[0]) for item in anomalies]
        consecutive = any(b - a == 1 for a, b in zip(anomaly_positions, anomaly_positions[1:]))
        half = len(values) // 2
        shift = abs(statistics.fmean(values[:half]) - statistics.fmean(values[half:]))
        if consecutive:
            explanations.append({"title": "Cluster or level shift", "severity": "medium", "detail": "Consecutive anomalous points suggest a sustained change rather than a single spike."})
        elif len(anomalies) == 1:
            explanations.append({"title": "Isolated outlier", "severity": "low", "detail": "A single extreme observation is the most likely pattern; verify the source record."})
        if shift > stdev:
            explanations.append({"title": "Distribution shift", "severity": "medium", "detail": f"Mean of the second half differs by {shift:.2f}, more than one standard deviation."})
        if any("high" in item[3] for item in anomalies) and any("low" in item[3] for item in anomalies):
            explanations.append({"title": "Two-sided variation", "severity": "info", "detail": "Both unusually high and low values are present; check for mixed populations."})
    step = max(1, len(values) // 40)
    chart_values = values[::step][:40]
    chart = {"labels": [str(indices[i]) for i in range(0, len(values), step)][:40], "values": [round(v, 2) for v in chart_values]}
    findings = explanations + ([] if anomalies else [{"title": "No strong anomalies", "severity": "info", "detail": "No values crossed the z-score or IQR thresholds."}])
    return _result(
        f"Found {len(anomalies)} anomalous value(s) in '{column}' out of {len(values)} observations.",
        {
            "metrics": {"values": len(values), "anomalies": len(anomalies), "mean": round(mean, 3), "stdev": round(stdev, 3)},
            "table": {"columns": ["Row index", "Value", "Z-score", "Direction"], "rows": anomalies},
            "chart": chart,
            "findings": findings,
        },
        ["Statistical flags are candidate explanations, not proof of a cause. Confirm against source systems."],
    )


run = agent_anomaly_investigator
