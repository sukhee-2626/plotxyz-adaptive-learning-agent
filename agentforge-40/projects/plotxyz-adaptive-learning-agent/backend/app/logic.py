"""Original deterministic implementation for Adaptive Learning (plotxyz-adaptive-learning-agent)."""
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


def agent_adaptive_learning(payload):
    study = _text(payload, "study_text", max_len=80000)
    difficulty = int(_num(payload, "difficulty", default=2, lo=1, hi=3))
    answers_raw = payload.get("answers", "")
    answers = {}
    if answers_raw:
        answers = _json(payload, "answers", dict)
    sentences = [s for s in _sentences(study) if len(s.split()) >= 7]
    if len(sentences) < 3:
        raise LogicError("provide at least three substantive sentences of study text")
    counts = Counter()
    for sentence in sentences:
        counts.update(token for token in _tokens(sentence) if len(token) >= 5)
    terms = [term for term, _ in counts.most_common(12)]
    questions, used_sentences = [], set()
    for term in terms:
        if len(questions) >= min(5, 2 + difficulty):
            break
        for position, sentence in enumerate(sentences):
            if position in used_sentences or term not in sentence.lower():
                continue
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.I)
            if not pattern.search(sentence):
                continue
            question_text = pattern.sub("_____", sentence, count=1)
            distractors = [other for other in terms if other != term][:3]
            options = sorted({term, *distractors})
            questions.append({"id": f"Q{len(questions) + 1}", "question": question_text, "answer": term, "options": options})
            used_sentences.add(position)
            break
    if len(questions) < 2:
        raise LogicError("the study text did not yield enough cloze questions")
    rows = [[q["id"], q["question"][:260], ", ".join(q["options"])] for q in questions]
    result = {
        "metrics": {"questions": len(questions), "difficulty": difficulty, "study_sentences": len(sentences)},
        "table": {"columns": ["ID", "Question", "Options"], "rows": rows},
        "items": [f"{q['id']}: {q['question']} [{', '.join(q['options'])}]" for q in questions],
    }
    warnings = ["Quiz items are cloze questions generated from the supplied text; answers are single terms."]
    if answers:
        correct, feedback = 0, []
        for question in questions:
            submitted = str(answers.get(question["id"], "")).strip().lower()
            ok = submitted == question["answer"].lower()
            correct += int(ok)
            feedback.append(f"{question['id']}: {'correct' if ok else 'incorrect'} (expected '{question['answer']}')")
        score = round(correct / len(questions) * 100, 1)
        next_difficulty = min(3, difficulty + 1) if score >= 80 else max(1, difficulty - 1) if score < 50 else difficulty
        result["metrics"].update({"score": score, "correct": correct, "next_difficulty": next_difficulty})
        result["markdown"] = "## Results\n\n" + "\n".join(f"- {line}" for line in feedback) + f"\n\n**Score:** {score}% · **Next difficulty:** {next_difficulty}"
        result["findings"] = [{"title": "Adaptive recommendation", "severity": "info", "detail": f"Score {score}% moves the next session to difficulty {next_difficulty}."}]
    else:
        result["markdown"] = "## Quiz\n\n" + "\n".join(f"**{q['id']}.** {q['question']}\n\nOptions: {', '.join(q['options'])}" for q in questions)
        warnings.append("Submit an 'answers' object keyed by question ID to grade the quiz.")
    return _result(f"Generated {len(questions)} cloze question(s) at difficulty {difficulty}.", result, warnings)


run = agent_adaptive_learning
