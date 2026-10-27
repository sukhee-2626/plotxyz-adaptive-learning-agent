"""Original deterministic implementation for Research Synthesis (plotxyz-research-synthesis-agent)."""
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


def agent_research_synthesis(payload):
    sources_text = _text(payload, "sources", max_len=160000)
    focus = str(payload.get("focus", "")).strip()
    blocks = [block.strip() for block in re.split(r"\n?\s*(?:###|Source:)\s*", sources_text) if block.strip()]
    if len(blocks) < 2:
        raise LogicError("provide at least two sources separated by '###' or 'Source:'")
    focus_tokens = set(_tokens(focus))
    source_rows, selected_all, numeric_claims = [], [], []
    for index, block in enumerate(blocks, 1):
        lines = block.splitlines()
        title = lines[0].strip("# ").strip() or f"Source {index}"
        body = "\n".join(lines[1:]) if len(lines) > 1 else block
        sentences = _sentences(body)
        scored = []
        for position, sentence in enumerate(sentences):
            tokens = set(_tokens(sentence))
            score = len(tokens & focus_tokens) if focus_tokens else 0
            score += min(len(sentence) / 200, 1) + (1 if position == 0 else 0)
            scored.append((score, sentence))
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = [sentence for _, sentence in scored[:3]]
        selected_all.append((title, selected))
        source_rows.append([f"S{index}", title, len(sentences), len(selected)])
        for sentence in sentences:
            numbers = re.findall(r"\b\d+(?:\.\d+)?%?\b", sentence)
            if numbers:
                numeric_claims.append((index, sentence, set(numbers)))
    disagreements = []
    for i, (left_source, left_sentence, left_numbers) in enumerate(numeric_claims):
        for right_source, right_sentence, right_numbers in numeric_claims[i + 1:]:
            if left_source == right_source or left_numbers == right_numbers:
                continue
            left_tokens, right_tokens = set(_tokens(left_sentence)), set(_tokens(right_sentence))
            union = left_tokens | right_tokens
            if union and len(left_tokens & right_tokens) / len(union) >= 0.35:
                disagreements.append([f"S{left_source}", left_sentence[:160], f"S{right_source}", right_sentence[:160]])
    markdown = ["## Synthesis", ""]
    for index, (title, selected) in enumerate(selected_all, 1):
        markdown.append(f"### {title}")
        markdown += [f"- {sentence} [S{index}]" for sentence in selected] or ["- No extractable sentences."]
        markdown.append("")
    if disagreements:
        markdown.append("## Possible disagreements")
        markdown += [f"- [S{a[0][1:]}] {a[1]} ↔ [S{a[2][1:]}] {a[3]}" for a in disagreements[:8]]
    return _result(
        f"Synthesized {len(blocks)} sources with citations; {len(disagreements)} possible numeric disagreement(s).",
        {
            "metrics": {"sources": len(blocks), "citations": len(selected_all), "disagreements": len(disagreements)},
            "table": {"columns": ["Ref", "Source", "Sentences", "Selected"], "rows": source_rows},
            "markdown": "\n".join(markdown),
            "findings": [{"title": "Possible disagreement", "severity": "medium", "detail": f"{row[0]} vs {row[2]}: {row[1][:80]} / {row[3][:80]}"} for row in disagreements[:6]],
        },
        ["Extractive synthesis only. Citations point to supplied sources; numeric disagreement is a heuristic, not a verdict."],
    )


run = agent_research_synthesis
