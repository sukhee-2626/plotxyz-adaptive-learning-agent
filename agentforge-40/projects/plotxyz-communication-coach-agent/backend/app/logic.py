"""Original deterministic implementation for Communication Coach (plotxyz-communication-coach-agent)."""
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


def agent_communication_coach(payload):
    text = _text(payload, "text", max_len=30000)
    context = str(payload.get("context", "general")).lower()
    words = re.findall(r"\b[\w'-]+\b", text)
    sentences = _sentences(text)
    filler = re.compile(r"\b(um+|uh+|like|you know|basically|actually|sort of|kind of|literally)\b", re.I)
    fillers = filler.findall(text)
    passive = re.findall(r"\b(was|were|been|being|is|are)\s+\w+(?:ed|en)\b", text, re.I)
    long_sentences = [s for s in sentences if len(s.split()) > 28]
    repeated = [(word, count) for word, count in Counter(w.lower() for w in words if len(w) > 4 and w.lower() not in {"about", "there", "their", "would", "could", "should", "because"}).most_common(5) if count >= 4]
    syllables = sum(max(1, len(re.findall(r"[aeiouy]+", word.lower()))) for word in words)
    asl = len(words) / max(1, len(sentences))
    asw = syllables / max(1, len(words))
    readability = round(206.835 - 1.015 * asl - 84.6 * asw, 1)
    rewrite = filler.sub("", text)
    rewrite = re.sub(r"\s{2,}", " ", rewrite).strip()
    rewrite = re.sub(r"\bI think that\b", "", rewrite, flags=re.I)
    patches = []
    if fillers:
        patches.append({"title": "Remove filler words", "before": text[:400], "after": rewrite[:400]})
    for sentence in long_sentences[:2]:
        parts = re.split(r",\s+(?:and|but|so)\s+", sentence, maxsplit=1)
        if len(parts) == 2:
            replacement = parts[0].rstrip() + ". " + parts[1][0].upper() + parts[1][1:]
            patches.append({"title": "Split a long sentence", "before": sentence, "after": replacement})
    suggestions = []
    if fillers:
        suggestions.append(f"Remove {len(fillers)} filler word(s) to sound more confident.")
    if passive:
        suggestions.append(f"Review {len(passive)} passive construction(s) and name the actor where useful.")
    if long_sentences:
        suggestions.append(f"Split {len(long_sentences)} sentence(s) longer than 28 words.")
    if repeated:
        suggestions.append("Vary repeated words: " + ", ".join(f"'{w}' ({c}x)" for w, c in repeated[:3]) + ".")
    if context == "interview":
        suggestions.append("Use a STAR structure: situation, task, action, result.")
    elif context == "presentation":
        suggestions.append("Open with the decision you want, then support it with three points.")
    else:
        suggestions.append("Put the request and deadline in the first two sentences.")
    findings = []
    if readability < 30:
        findings.append({"title": "Very dense prose", "severity": "medium", "detail": f"Estimated Flesch reading ease is {readability}; shorten sentences."})
    if len(fillers) >= 5:
        findings.append({"title": "Frequent filler words", "severity": "low", "detail": f"Detected {len(fillers)} fillers."})
    table = {
        "columns": ["Metric", "Value", "Target"],
        "rows": [
            ["Words", len(words), "context dependent"],
            ["Sentences", len(sentences), "—"],
            ["Avg. sentence length", round(asl, 1), "12–22 words"],
            ["Filler words", len(fillers), "0–2"],
            ["Passive constructions", len(passive), "minimize"],
            ["Reading ease", readability, "50–70"],
        ],
    }
    return _result(
        f"Coaching review for {context}: {len(words)} words, reading ease {readability}, {len(fillers)} filler(s).",
        {
            "metrics": {"words": len(words), "readability": readability, "fillers": len(fillers), "passive": len(passive), "long_sentences": len(long_sentences)},
            "table": table,
            "items": suggestions,
            "patches": patches,
            "markdown": "## Suggested rewrite\n\n" + rewrite[:2500],
            "findings": findings,
        },
        ["Readability and grammar signals are heuristic; a human editor should confirm tone and intent."],
    )


run = agent_communication_coach
