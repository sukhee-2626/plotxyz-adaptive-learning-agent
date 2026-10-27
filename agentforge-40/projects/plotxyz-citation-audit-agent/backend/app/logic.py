"""Original deterministic implementation for Citation Audit (plotxyz-citation-audit-agent)."""
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


def agent_citation_audit(payload):
    references_text = _text(payload, "references", max_len=60000)
    claims_text = _text(payload, "claims", max_len=30000)
    references = [line.strip(" -•") for line in references_text.splitlines() if line.strip()]
    claims = [line.strip(" -•") for line in claims_text.splitlines() if line.strip()]
    if not references or not claims:
        raise LogicError("supply references and claims, one per line")
    rows, findings, normalized = [], [], Counter()
    for index, reference in enumerate(references, 1):
        year = re.search(r"\b(19|20)\d{2}\b", reference)
        doi = re.search(r"10\.\d{4,9}/\S+", reference)
        url = re.search(r"https?://\S+", reference)
        issues = []
        if not year:
            issues.append("missing year")
        if not doi and not url:
            issues.append("no DOI or URL")
        if len(reference) < 25:
            issues.append("very short entry")
        normalized[re.sub(r"\W+", "", reference.lower())] += 1
        if issues:
            findings.append({"title": "Reference format issue", "severity": "low", "detail": f"Reference {index}: {', '.join(issues)}."})
        linked = []
        ref_tokens = set(_tokens(reference))
        for claim_index, claim in enumerate(claims, 1):
            claim_tokens = set(_tokens(claim))
            overlap = len(ref_tokens & claim_tokens) / max(1, len(claim_tokens))
            if overlap >= 0.25:
                linked.append(f"C{claim_index}")
        rows.append([f"R{index}", reference[:160], year.group(0) if year else "-", "yes" if (doi or url) else "no", ", ".join(linked) or "unlinked"])
    for reference, count in normalized.items():
        if count > 1:
            findings.append({"title": "Duplicate reference", "severity": "low", "detail": f"A reference appears {count} times after normalization."})
    unlinked_claims = []
    for claim_index, claim in enumerate(claims, 1):
        if not any(f"C{claim_index}" in row[4] for row in rows):
            unlinked_claims.append(claim)
    if unlinked_claims:
        findings.append({"title": "Claims without a detected reference", "severity": "high", "detail": f"{len(unlinked_claims)} claim(s) could not be linked to a supplied reference by keyword overlap."})
    return _result(
        f"Audited {len(references)} reference(s) and {len(claims)} claim(s); {len(unlinked_claims)} claim(s) unlinked.",
        {
            "metrics": {"references": len(references), "claims": len(claims), "unlinked_claims": len(unlinked_claims), "format_issues": sum(1 for f in findings if f["title"] == "Reference format issue")},
            "table": {"columns": ["Ref", "Reference", "Year", "DOI/URL", "Linked claims"], "rows": rows},
            "findings": findings,
        },
        ["Linkage uses keyword overlap and does not verify that a source actually supports a claim. URLs are not fetched."],
    )


run = agent_citation_audit
