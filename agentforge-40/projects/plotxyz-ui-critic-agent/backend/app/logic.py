"""Original deterministic implementation for UI Critic (plotxyz-ui-critic-agent)."""
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


def agent_ui_critic(payload):
    description = str(payload.get("description", "")).strip()
    elements = payload.get("elements")
    findings, rows = [], []
    score = 100
    if isinstance(elements, str) and elements.strip():
        elements = _json(payload, "elements", list)
    if isinstance(elements, list) and elements:
        for index, element in enumerate(elements[:100], 1):
            if not isinstance(element, dict):
                raise LogicError("each UI element must be an object")
            name = str(element.get("name") or f"Element {index}")
            kind = str(element.get("type", "control")).lower()
            label = str(element.get("label", "")).strip()
            contrast = element.get("contrast_ratio")
            tap = element.get("tap_size_px")
            alt = element.get("alt")
            heading = element.get("heading_level")
            issues = []
            if kind not in {"text", "heading", "image"} and not label:
                issues.append(("Missing accessible label", "high"))
            if isinstance(contrast, (int, float)) and contrast < 4.5:
                issues.append((f"Low contrast ({contrast}:1)", "high" if contrast < 3 else "medium"))
            if isinstance(tap, (int, float)) and tap < 44 and kind in {"button", "link", "control", "icon"}:
                issues.append((f"Small target ({tap}px)", "medium"))
            if kind == "image" and not alt:
                issues.append(("Image missing alt text", "medium"))
            if heading is not None:
                try:
                    level = int(heading)
                    if level < 1 or level > 6:
                        issues.append(("Invalid heading level", "low"))
                except (TypeError, ValueError):
                    issues.append(("Invalid heading level", "low"))
            for title, severity in issues:
                findings.append({"title": title, "severity": severity, "detail": f"{name} ({kind})."})
                score -= 12 if severity == "high" else 7 if severity == "medium" else 3
            rows.append([name, kind, "pass" if not issues else "; ".join(i[0] for i in issues)])
        warnings = ["Checks use supplied element metadata; contrast and target size are not measured from pixels."]
    elif description:
        lowered = description.lower()
        checks = [
            ("contrast", "Contrast is mentioned but not measured. Supply element metadata for a ratio check."),
            ("alt text", "Confirm every meaningful image has alt text."),
            ("keyboard", "Confirm the flow is fully keyboard reachable."),
            ("label", "Confirm every control has a visible, programmatic label."),
            ("mobile", "Confirm tap targets are at least 44×44 px."),
        ]
        for keyword, detail in checks:
            if keyword in lowered:
                findings.append({"title": f"Review {keyword}", "severity": "low", "detail": detail})
                score -= 3
        rows.append(["Description", "text", "heuristic review only"])
        warnings = ["Only a description was supplied; no element metadata was available. Results are generic heuristics."]
    else:
        raise LogicError("supply 'elements' JSON or a UI 'description'")
    score = max(0, score)
    return _result(
        f"UI review score {score}/100 with {len(findings)} finding(s).",
        {
            "metrics": {"score": score, "elements": len(elements) if isinstance(elements, list) else 0, "findings": len(findings)},
            "table": {"columns": ["Element", "Type", "Result"], "rows": rows},
            "findings": findings,
            "items": ["Test with keyboard-only navigation and a screen reader.", "Verify contrast against WCAG 2.2 AA thresholds."],
        },
        warnings,
    )


run = agent_ui_critic
