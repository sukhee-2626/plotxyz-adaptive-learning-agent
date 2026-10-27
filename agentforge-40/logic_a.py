"""Deterministic logic for PlotXYZ.ai agents 1-20 (original implementations)."""
from __future__ import annotations

import ast
import json
import math
import re
import statistics
from collections import Counter, defaultdict

from logic_common import (
    LogicError,
    _csv,
    _json,
    _llm,
    _num,
    _result,
    _sentences,
    _text,
    _tokens,
    provider_status,
)


def agent_device_intelligence(payload):
    hardware = _json(payload, "hardware", dict)
    try:
        cores = float(hardware.get("cpu_cores", 0))
        ram = float(hardware.get("ram_gb", 0))
        vram = float(hardware.get("vram_gb", 0) or 0)
        disk = float(hardware.get("disk_free_gb", 0) or 0)
    except (TypeError, ValueError):
        raise LogicError("hardware fields must be numeric")
    if cores <= 0 or ram <= 0:
        raise LogicError("hardware.cpu_cores and hardware.ram_gb must be positive")
    use_case = str(payload.get("use_case", "balanced")).lower()
    weights = {
        "coding": (0.60, 0.20),
        "chat": (0.45, 0.35),
        "speed": (0.25, 0.65),
        "balanced": (0.50, 0.30),
    }.get(use_case, (0.50, 0.30))
    catalog = [
        {"name": "Nano 1B", "params": 1, "ram": 4, "vram": 0, "disk": 2, "quality": 40, "speed": 96},
        {"name": "Mini 3B", "params": 3, "ram": 8, "vram": 4, "disk": 4, "quality": 58, "speed": 84},
        {"name": "Studio 7B", "params": 7, "ram": 16, "vram": 6, "disk": 8, "quality": 74, "speed": 66},
        {"name": "Pro 13B", "params": 13, "ram": 24, "vram": 10, "disk": 14, "quality": 84, "speed": 48},
        {"name": "Max 34B", "params": 34, "ram": 48, "vram": 24, "disk": 30, "quality": 93, "speed": 28},
    ]
    rows, findings = [], []
    for model in catalog:
        if ram < model["ram"] or disk < model["disk"]:
            fit, bonus = "unsupported", 0
        elif model["vram"] > 0 and vram < model["vram"]:
            fit, bonus = "cpu-only", 4
        else:
            fit, bonus = "accelerated", 10
        score = model["quality"] * weights[0] + model["speed"] * weights[1] + bonus
        rows.append([model["name"], model["params"], model["ram"], model["vram"], fit, round(score, 1)])
    rows.sort(key=lambda row: row[5], reverse=True)
    compatible = [row for row in rows if row[4] != "unsupported"]
    if not compatible:
        findings.append({"title": "No catalog model fits", "severity": "high", "detail": "Increase RAM or free disk space; all catalog models exceed the supplied limits."})
    if vram <= 0:
        findings.append({"title": "CPU-only profile", "severity": "info", "detail": "No GPU VRAM was supplied, so latency estimates assume CPU inference."})
    if disk < 10:
        findings.append({"title": "Low disk headroom", "severity": "medium", "detail": "Less than 10 GB free may prevent model downloads and caching."})
    best = compatible[0][0] if compatible else "none"
    return _result(
        f"Best fit for {use_case}: {best} ({len(compatible)} compatible catalog entries).",
        {
            "metrics": {"best_model": best, "compatible_models": len(compatible), "ram_gb": ram, "vram_gb": vram},
            "table": {"columns": ["Model", "Params (B)", "Min RAM (GB)", "Min VRAM (GB)", "Fit", "Score"], "rows": rows},
            "findings": findings,
        },
        ["Compatibility is rule-based and should be validated against the model's current requirements."],
    )


def agent_offline_personal(payload):
    message = _text(payload, "message", max_len=8000)
    context = str(payload.get("context", "")).strip()
    use_provider = bool(payload.get("use_provider", False))
    warnings, mode = [], "deterministic-fallback"
    reply = None
    if use_provider:
        reply = _llm([
            {"role": "system", "content": "You are a concise offline personal assistant. Do not claim to have used tools."},
            {"role": "user", "content": message + (f"\n\nContext:\n{context}" if context else "")},
        ])
        if reply:
            mode = "configured-provider"
        else:
            warnings.append("No OpenAI-compatible or Ollama endpoint is configured (or the call failed); deterministic fallback used.")
    if reply is None:
        lowered = message.lower()
        if re.fullmatch(r"[0-9\s+\-*/().%]+", message) and re.search(r"[+\-*/%]", message):
            try:
                node = ast.parse(message, mode="eval")
                allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.USub, ast.UAdd)
                if any(not isinstance(item, allowed) for item in ast.walk(node)):
                    raise ValueError("unsupported expression")
                value = eval(compile(node, "<calc>", "eval"), {"__builtins__": {}}, {})
                reply = f"**Result:** `{value}`\n\nCalculated locally; no external service was called."
            except Exception:
                reply = "I could not evaluate that expression safely. Try plain arithmetic such as `(12 + 8) * 3`."
        elif lowered.startswith(("summar", "tl;dr")) and context:
            sentences = _sentences(context)
            picked = sentences[:3]
            reply = "**Local extractive summary**\n\n" + "\n".join(f"- {s}" for s in picked) + "\n\nOnly the supplied context was used."
        elif any(word in lowered for word in ("todo", "plan", "next step")):
            steps = [line.strip(" -") for line in context.splitlines() if line.strip()] if context else []
            if steps:
                reply = "**Plan from your notes**\n\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(steps[:8], 1))
            else:
                reply = "Here is a simple plan:\n\n1. State the outcome.\n2. List constraints.\n3. Take the smallest next action.\n4. Review the result."
        elif lowered.startswith(("hi", "hello", "hey")):
            reply = "Hello. I am the offline personal agent. I can calculate, summarize supplied context, and turn notes into a plan without a network connection."
        else:
            reply = (
                "**Offline response**\n\n"
                f"You said: {message}\n\n"
                "I can help with three local tasks: arithmetic, extractive summaries of pasted context, and turning notes into a plan. "
                "Configure `OPENAI_BASE_URL`/`OPENAI_MODEL` or `OLLAMA_BASE_URL` to enable optional model inference."
            )
    followups = ["Summarize the context I pasted", "Turn my notes into a plan", "Calculate (120 + 30) / 5"]
    return _result(
        f"Reply generated in {mode} mode.",
        {
            "markdown": reply,
            "metrics": {"mode": mode, "input_chars": len(message), "provider_configured": provider_status()},
            "items": followups,
        },
        warnings,
    )


def agent_resource_optimization(payload):
    cores = _num(payload, "cpu_cores", lo=1, hi=512)
    ram = _num(payload, "ram_gb", lo=1, hi=4096)
    workload = str(payload.get("workload", "api")).lower()
    if workload not in {"api", "batch", "ml"}:
        raise LogicError("workload must be api, batch, or ml")
    current_workers = int(_num(payload, "current_workers", default=1, lo=1, hi=1024))
    target_latency = _num(payload, "target_latency_ms", default=300, lo=10, hi=60000)
    if workload == "api":
        workers = max(2, int(cores * 2))
        batch = max(1, int(ram / 4))
        cache = min(4096, int(ram * 128))
        reason = "I/O-bound API work benefits from roughly two workers per core."
    elif workload == "batch":
        workers = max(1, int(cores))
        batch = max(8, int(ram * 2))
        cache = min(2048, int(ram * 64))
        reason = "CPU-bound batch work is kept near one worker per core."
    else:
        workers = max(1, int(cores // 2))
        batch = max(1, int(ram / 16))
        cache = min(8192, int(ram * 192))
        reason = "ML workloads reserve memory for model weights and avoid oversubscription."
    if target_latency < 100:
        workers = min(cores * 4, workers * 2)
        reason += " Tight latency targets increase concurrency."
    table = {
        "columns": ["Setting", "Current", "Recommended", "Rationale"],
        "rows": [
            ["Workers", current_workers, workers, reason],
            ["Batch size", "-", batch, "Derived from available RAM and workload type."],
            ["Cache (MB)", "-", cache, "Leaves headroom for the operating system and model."],
        ],
    }
    findings = []
    if current_workers > workers * 2:
        findings.append({"title": "Possible worker oversubscription", "severity": "medium", "detail": f"{current_workers} workers is more than twice the recommended {workers}; expect context-switch overhead."})
    if ram < 8 and workload == "ml":
        findings.append({"title": "Low memory for ML", "severity": "high", "detail": "Under 8 GB RAM is unlikely to support local model inference comfortably."})
    if current_workers < workers // 2:
        findings.append({"title": "Underutilized capacity", "severity": "low", "detail": "More concurrency may improve throughput if the workload is not memory-bound."})
    return _result(
        f"Recommended {workers} workers, batch size {batch}, and {cache} MB cache for the {workload} workload.",
        {
            "metrics": {"recommended_workers": workers, "batch_size": batch, "cache_mb": cache, "cpu_cores": cores, "ram_gb": ram},
            "table": table,
            "findings": findings,
            "items": ["Load-test with production-like payloads before applying changes.", "Watch p95 latency and memory pressure after the change."],
        },
    )


def agent_local_model_benchmark(payload):
    if not payload:
        raise LogicError("provide benchmark settings")
    iterations = int(_num(payload, "iterations", default=200, lo=10, hi=5000))
    size = int(_num(payload, "payload_tokens", default=512, lo=16, hi=8192))
    blob = "token " * size
    timings = []
    for _ in range(iterations):
        started = __import__("time").perf_counter()
        encoded = json.dumps({"text": blob, "meta": {"iteration": _}}).encode("utf-8")
        json.loads(encoded)
        timings.append((__import__("time").perf_counter() - started) * 1000)
    ordered = sorted(timings)
    p50 = ordered[int(0.50 * (len(ordered) - 1))]
    p95 = ordered[int(0.95 * (len(ordered) - 1))]
    mean = statistics.fmean(timings)
    throughput = 1000 / mean if mean else 0
    rows = [
        ["p50", round(p50, 3)],
        ["p95", round(p95, 3)],
        ["mean", round(mean, 3)],
        ["min", round(min(timings), 3)],
        ["max", round(max(timings), 3)],
        ["throughput (ops/s)", round(throughput, 1)],
    ]
    warnings = ["This measures a local JSON serialization reference workload, not model inference. No model latency or token throughput is fabricated."]
    provider = provider_status()
    endpoint = None
    if provider["ollama_compatible"]:
        import os
        import httpx

        url = os.getenv("OLLAMA_BASE_URL", "").rstrip("/") + "/api/tags"
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(url)
            endpoint = {"reachable": response.status_code == 200, "status_code": response.status_code, "url": url}
        except Exception as exc:
            endpoint = {"reachable": False, "error": type(exc).__name__, "url": url}
    return _result(
        f"Reference workload completed {iterations} iterations at p50 {p50:.3f} ms.",
        {
            "metrics": {"p50_ms": round(p50, 3), "p95_ms": round(p95, 3), "throughput_ops_s": round(throughput, 1), "iterations": iterations, "payload_tokens": size},
            "table": {"columns": ["Statistic", "Value"], "rows": rows},
            "chart": {"labels": ["p50", "p95", "max"], "values": [round(p50, 3), round(p95, 3), round(max(timings), 3)]},
            "items": ([f"Ollama endpoint check: {json.dumps(endpoint)}"] if endpoint else ["Set OLLAMA_BASE_URL to check a local endpoint."]),
        },
        warnings,
    )


def agent_privacy_audit(payload):
    config = _text(payload, "config", max_len=60000)
    flow = str(payload.get("data_flow", "")).strip()
    haystack = config + "\n" + flow
    patterns = [
        ("Email address", r"[\w.+-]+@[\w-]+\.[\w.]+", "high", "Personal identifiers may be stored or transmitted."),
        ("API key or cloud token", r"(sk-[A-Za-z0-9]{8,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})", "high", "A credential-like value is present in the supplied text."),
        ("Sensitive field name", r"\b(password|secret|token|ssn|credit_card|date_of_birth|dob)\b", "high", "Sensitive fields need encryption, minimization, and access control."),
        ("Plain HTTP endpoint", r"http://[^\s\"']+", "medium", "Traffic over plain HTTP can be intercepted."),
        ("Telemetry or analytics", r"\b(telemetry|analytics|tracking|sentry|segment|mixpanel)\b", "medium", "Telemetry can reveal usage patterns; confirm consent and retention."),
        ("Third-party endpoint", r"https?://([\w.-]+)", "low", "Review each external destination and its data-processing terms."),
        ("Logging of payloads", r"\b(log|logging|logger)\b[^\n]{0,40}\b(payload|body|request|response)\b", "medium", "Request logging may capture personal data."),
    ]
    findings, rows = [], []
    score = 100
    for label, pattern, severity, detail in patterns:
        matches = re.findall(pattern, haystack, re.I)
        count = len(matches)
        if count:
            examples = sorted({m if isinstance(m, str) else str(m) for m in matches})[:3]
            score -= {"high": 18, "medium": 9, "low": 3}[severity] * min(count, 3)
            findings.append({"title": label, "severity": severity, "detail": f"{detail} Found {count} match(es), e.g. {', '.join(examples)[:160]}."})
        rows.append([label, count, severity, "review" if count else "clear"])
    score = max(0, min(100, score))
    if not flow:
        findings.append({"title": "Data-flow description missing", "severity": "low", "detail": "Add sources, transforms, storage, and destinations for a fuller review."})
    return _result(
        f"Static privacy review found {len(findings)} item(s); heuristic score {score}/100.",
        {
            "metrics": {"score": score, "findings": len(findings), "high_severity": sum(1 for f in findings if f["severity"] == "high")},
            "findings": findings,
            "table": {"columns": ["Check", "Matches", "Severity", "Status"], "rows": rows},
        },
        ["This is a static text heuristic, not a compliance certification or legal advice."],
    )


def agent_model_router(payload):
    models = _json(payload, "models", list)
    if not models or len(models) > 50:
        raise LogicError("'models' must contain 1-50 model entries")
    task = str(payload.get("task", "balanced")).lower()
    max_latency = _num(payload, "max_latency_ms", default=None, lo=1, hi=600000)
    max_cost = _num(payload, "max_cost_per_1k", default=None, lo=0, hi=10000)
    clean = []
    for item in models:
        if not isinstance(item, dict) or not item.get("name"):
            raise LogicError("each model needs a name")
        try:
            clean.append({
                "name": str(item["name"]),
                "capability": float(item.get("capability", 50)),
                "latency_ms": float(item.get("latency_ms", 1000)),
                "cost": float(item.get("cost_per_1k", 0)),
            })
        except (TypeError, ValueError):
            raise LogicError("model capability, latency_ms, and cost_per_1k must be numeric")
    weights = {"coding": (0.65, 0.15, 0.20), "chat": (0.45, 0.35, 0.20), "cheap": (0.30, 0.20, 0.50), "balanced": (0.50, 0.30, 0.20)}.get(task, (0.50, 0.30, 0.20))
    lat_max = max(m["latency_ms"] for m in clean) or 1
    cost_max = max(m["cost"] for m in clean) or 1
    rows = []
    for model in clean:
        if max_latency is not None and model["latency_ms"] > max_latency:
            continue
        if max_cost is not None and model["cost"] > max_cost:
            continue
        score = (
            model["capability"] * weights[0]
            + (1 - model["latency_ms"] / lat_max) * 100 * weights[1]
            + (1 - model["cost"] / cost_max) * 100 * weights[2]
        )
        rows.append([model["name"], model["capability"], model["latency_ms"], model["cost"], round(score, 1)])
    rows.sort(key=lambda row: row[4], reverse=True)
    findings = []
    if not rows:
        findings.append({"title": "No model satisfies the constraints", "severity": "high", "detail": "Relax latency or cost limits, or add another configured model."})
    chosen = rows[0][0] if rows else None
    if rows:
        findings.append({"title": "Routing decision", "severity": "info", "detail": f"Selected {chosen} using {task} weights. Scores combine capability, normalized latency, and normalized cost."})
    return _result(
        f"Selected {chosen or 'no model'} from {len(clean)} candidate(s).",
        {
            "metrics": {"selected": chosen, "eligible": len(rows), "task": task},
            "table": {"columns": ["Model", "Capability", "Latency (ms)", "Cost / 1k", "Score"], "rows": rows},
            "findings": findings,
        },
        ["Cost values are user-supplied; verify current provider pricing before production routing."],
    )


def agent_local_knowledge(payload):
    documents = _text(payload, "documents", max_len=120000)
    query = _text(payload, "query", max_len=1000)
    top_k = int(_num(payload, "top_k", default=3, lo=1, hi=5))
    sections = []
    if "###" in documents:
        for index, block in enumerate(re.split(r"\n?\s*###\s*", documents)):
            block = block.strip()
            if block:
                lines = block.splitlines()
                title = lines[0].strip("# ").strip() or f"Document {index}"
                sections.append((title, "\n".join(lines[1:]) if len(lines) > 1 else block))
    else:
        for index, block in enumerate([b for b in re.split(r"\n\s*\n", documents) if b.strip()], 1):
            sections.append((f"Document {index}", block.strip()))
    if not sections:
        raise LogicError("no readable documents were supplied")
    query_tokens = set(_tokens(query))
    passages = []
    for title, body in sections:
        words = body.split()
        for start in range(0, len(words), 60):
            chunk = " ".join(words[start:start + 60]).strip()
            if chunk:
                passages.append({"title": title, "text": chunk})
    scored = []
    for passage in passages:
        tokens = set(_tokens(passage["text"]))
        overlap = len(query_tokens & tokens) / max(1, len(query_tokens))
        phrase = 0.5 if query.lower() in passage["text"].lower() else 0
        scored.append((round(overlap + phrase, 3), passage))
    scored.sort(key=lambda item: item[0], reverse=True)
    top = scored[:top_k]
    lines = ["**Extractive answer from approved documents**", ""]
    for rank, (score, passage) in enumerate(top, 1):
        excerpt = passage["text"][:420]
        lines.append(f"{rank}. **{passage['title']}** (relevance {score:.2f})")
        lines.append(f"   > {excerpt}")
    best = top[0][0] if top else 0
    findings = []
    if best <= 0:
        findings.append({"title": "No lexical match", "severity": "medium", "detail": "No passage shares keywords with the query. Try different terms or add documents."})
    return _result(
        f"Retrieved {len(top)} passage(s); best relevance {best:.2f}. Answers are extractive with source titles.",
        {
            "metrics": {"passages_indexed": len(passages), "retrieved": len(top), "best_score": best},
            "markdown": "\n".join(lines),
            "table": {"columns": ["Source", "Relevance", "Excerpt"], "rows": [[p["title"], s, p["text"][:120]] for s, p in top]},
            "findings": findings,
        },
        ["Keyword retrieval only; no embeddings or external search are used."],
    )


def agent_computer_health(payload):
    metrics = _json(payload, "metrics", dict)
    limits = {"cpu_percent": 85, "memory_percent": 85, "disk_percent": 90, "temperature_c": 80, "failed_services": 0}
    values = {}
    for key, limit in limits.items():
        raw = metrics.get(key, 0)
        try:
            values[key] = float(raw or 0)
        except (TypeError, ValueError):
            raise LogicError(f"metrics.{key} must be numeric")
    score = 100
    findings, rows = [], []
    labels = {"cpu_percent": "CPU", "memory_percent": "Memory", "disk_percent": "Disk", "temperature_c": "Temperature", "failed_services": "Failed services"}
    for key, limit in limits.items():
        value = values[key]
        if key == "failed_services":
            bad = value > 0
        else:
            bad = value >= limit
        if bad:
            penalty = 20 if key in {"failed_services", "temperature_c"} else 12
            score -= penalty
            severity = "high" if key in {"failed_services", "temperature_c"} else "medium"
            findings.append({"title": f"{labels[key]} threshold exceeded", "severity": severity, "detail": f"Observed {value:g}; threshold {limit:g}."})
        rows.append([labels[key], value, limit, "attention" if bad else "ok"])
    score = max(0, score)
    uptime = values.get("failed_services", 0)
    return _result(
        f"Health score {score}/100 with {len(findings)} threshold alert(s).",
        {
            "metrics": {"score": score, "alerts": len(findings), "failed_services": int(uptime)},
            "findings": findings,
            "table": {"columns": ["Metric", "Observed", "Threshold", "Status"], "rows": rows},
            "items": ["Investigate failed services first, then sustained CPU or memory pressure."] if findings else ["All supplied metrics are within configured thresholds."],
        },
        ["Analysis uses only the metrics supplied; no system access is performed."],
    )


def agent_self_healing_code(payload):
    code = _text(payload, "code", max_len=60000)
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise LogicError(f"Python syntax error at line {exc.lineno}: {exc.msg}")
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append({"line": node.lineno, "title": "Bare except", "severity": "high", "detail": "Catches every exception, including interrupts and programming errors."})
        if isinstance(node, ast.Compare) and any(isinstance(op, ast.Eq) for op in node.ops):
            if any(isinstance(c, ast.Constant) and c.value is None for c in node.comparators):
                issues.append({"line": node.lineno, "title": "Equality with None", "severity": "low", "detail": "Use 'is None' for identity checks."})
        if isinstance(node, ast.FunctionDef):
            for default in node.args.defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    issues.append({"line": node.lineno, "title": "Mutable default argument", "severity": "medium", "detail": f"Function '{node.name}' uses a mutable default shared across calls."})
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            issues.append({"line": node.lineno, "title": "Dynamic code execution", "severity": "high", "detail": f"{node.func.id}() can execute untrusted input."})
    patched = re.sub(r"except\s*:", "except Exception:", code)
    patched = re.sub(r"==\s*None\b", "is None", patched)
    patches = []
    if patched != code:
        try:
            ast.parse(patched)
        except SyntaxError:
            patched = code
        else:
            patches.append({
                "title": "Normalize exception and None checks",
                "before": "\n".join(line for line in code.splitlines() if re.search(r"except\s*:|==\s*None", line))[:600],
                "after": "\n".join(line for line in patched.splitlines() if re.search(r"except Exception:|is None", line))[:600],
            })
    rows = [[item["line"], item["title"], item["severity"], item["detail"]] for item in issues]
    return _result(
        f"Found {len(issues)} issue(s) and generated {len(patches)} safe patch(es). Code was parsed, not executed.",
        {
            "metrics": {"issues": len(issues), "patches": len(patches), "lines": len(code.splitlines())},
            "table": {"columns": ["Line", "Issue", "Severity", "Detail"], "rows": rows},
            "patches": patches,
            "patched_code": patched,
            "findings": [{"title": item["title"], "severity": item["severity"], "detail": f"Line {item['line']}: {item['detail']}"} for item in issues],
        },
        ["Patches are pattern-based and must be reviewed. No test suite or untrusted code was executed."],
    )


def agent_api_detective(payload):
    method = _text(payload, "method", max_len=12).upper()
    url = _text(payload, "url", max_len=2000)
    status = int(_num(payload, "status", lo=100, hi=599))
    body = str(payload.get("response_body", "")).strip()
    lowered = body.lower()
    findings, suggestions = [], []
    if 200 <= status < 300:
        summary = f"{method} {url} returned {status}; the request succeeded."
        severity = "info"
    elif status == 401:
        summary = "Authentication is missing, expired, or malformed."
        findings.append({"title": "401 Unauthorized", "severity": "high", "detail": "The server did not accept the supplied credentials."})
        suggestions += ["Confirm the Authorization header is present and uses the expected scheme.", "Check token expiry and audience."]
    elif status == 403:
        summary = "The caller is authenticated but not authorized for this resource."
        findings.append({"title": "403 Forbidden", "severity": "high", "detail": "Check scopes, roles, and resource ownership."})
        suggestions += ["Verify scopes/roles.", "Confirm the resource belongs to the caller."]
    elif status == 404:
        summary = "The route or resource was not found."
        findings.append({"title": "404 Not Found", "severity": "medium", "detail": "Check the path, base URL, and resource identifier."})
        suggestions += ["Compare the path with the API specification.", "Check for a missing ID or trailing slash."]
    elif status == 429:
        summary = "The request was rate limited."
        findings.append({"title": "429 Rate limited", "severity": "medium", "detail": "Retry after the advertised delay and add backoff."})
        suggestions += ["Read Retry-After if present.", "Add exponential backoff with jitter."]
    elif 500 <= status < 600:
        summary = f"Server error {status}; the failure is likely on the provider side."
        findings.append({"title": "Server-side failure", "severity": "high", "detail": "Capture a request ID and retry idempotent requests with backoff."})
        suggestions += ["Retry idempotent requests with backoff.", "Escalate with the request ID and timestamp."]
    elif 400 <= status < 500:
        summary = f"Client error {status}; the request needs correction."
        findings.append({"title": "Client error", "severity": "medium", "detail": "Inspect validation messages and required fields."})
        suggestions += ["Validate required fields and content type.", "Log the response body without secrets."]
    else:
        summary = f"Informational response {status}."
    if "cors" in lowered:
        findings.append({"title": "CORS mentioned", "severity": "medium", "detail": "Check allowed origins, methods, and preflight headers."})
    if "timeout" in lowered:
        findings.append({"title": "Timeout mentioned", "severity": "medium", "detail": "Check server latency and client timeout settings."})
    if not body:
        suggestions.append("Attach the response body for more specific guidance.")
    rows = [["Status class", f"{status // 100}xx"], ["Body supplied", "yes" if body else "no"], ["Method", method], ["URL host", re.sub(r"^https?://([^/]+).*", r"\1", url)]]
    return _result(summary, {
        "metrics": {"status": status, "client_error": 400 <= status < 500, "server_error": status >= 500},
        "findings": findings,
        "items": suggestions,
        "table": {"columns": ["Check", "Value"], "rows": rows},
    }, ["No network request was made; this analysis uses the supplied request and response details."])


def agent_autonomous_qa(payload):
    requirements = _text(payload, "requirements", max_len=30000)
    risk = str(payload.get("risk_level", "medium")).lower()
    lines = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip() for line in requirements.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        raise LogicError("at least one requirement is needed")
    lines = lines[:20]
    rows, findings = [], []
    vague = re.compile(r"\b(fast|easy|simple|user-friendly|robust|better|quick)\b", re.I)
    for index, requirement in enumerate(lines, 1):
        base = requirement.rstrip(".")
        rows.append([f"TC-{index:02d}A", base, "Happy path", f"Provide valid input for: {base}", "Expected behavior is observed and recorded."])
        rows.append([f"TC-{index:02d}B", base, "Invalid input", f"Submit malformed or missing input for: {base}", "Validation error is returned; no partial write occurs."])
        rows.append([f"TC-{index:02d}C", base, "Boundary", f"Use minimum, maximum, and empty values for: {base}", "Limits are enforced consistently."])
        if vague.search(requirement):
            findings.append({"title": "Ambiguous acceptance criterion", "severity": "medium", "detail": f"Requirement {index} uses a subjective term; add measurable criteria."})
    if risk == "high":
        rows.append(["TC-R01", "Cross-cutting", "Security", "Attempt unauthorized access to the changed surface.", "Access is denied and the event is logged."])
        rows.append(["TC-R02", "Cross-cutting", "Recovery", "Interrupt a write and retry the operation.", "Data remains consistent; retry is idempotent."])
    table = {"columns": ["ID", "Requirement", "Type", "Steps", "Expected"], "rows": rows}
    markdown = "## Generated test plan\n\n" + "\n".join(f"- **{r[0]}** [{r[2]}] {r[1]}" for r in rows)
    return _result(
        f"Generated {len(rows)} test case(s) from {len(lines)} requirement(s) at {risk} risk.",
        {"metrics": {"requirements": len(lines), "test_cases": len(rows), "ambiguous": len(findings)}, "table": table, "markdown": markdown, "findings": findings},
        ["Test cases are derived from requirement text; a human must confirm expected results."],
    )


def agent_code_review(payload):
    code = _text(payload, "code", max_len=60000)
    language = str(payload.get("language", "python")).lower()
    findings, rows = [], []
    metrics = {"lines": len(code.splitlines()), "functions": 0, "max_function_lines": 0}
    if language == "python":
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            findings.append({"title": "Syntax error", "severity": "high", "detail": f"Line {exc.lineno}: {exc.msg}"})
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    length = (node.end_lineno or node.lineno) - node.lineno + 1
                    metrics["functions"] += 1
                    metrics["max_function_lines"] = max(metrics["max_function_lines"], length)
                    rows.append([node.name, node.lineno, length, len(node.args.args)])
                    if length > 40:
                        findings.append({"title": "Long function", "severity": "medium", "detail": f"'{node.name}' is {length} lines; consider extracting helpers."})
                    depth = 0
                    for child in ast.walk(node):
                        if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
                            depth += 1
                    if depth > 8:
                        findings.append({"title": "High nesting", "severity": "medium", "detail": f"'{node.name}' contains {depth} control-flow nodes; reduce nesting."})
    else:
        findings.append({"title": "Limited language support", "severity": "info", "detail": "AST checks run for Python; other languages receive pattern-based checks only."})
    patterns = [
        ("Dynamic execution", r"\b(eval|exec)\s*\(", "high", "Avoid executing dynamic strings."),
        ("Shell invocation", r"subprocess\.[^(]+\([^)]*shell\s*=\s*True", "high", "shell=True can enable command injection."),
        ("Hardcoded credential", r"(?i)(password|api_key|secret|token)\s*=\s*['\"][^'\"]{4,}['\"]", "high", "Move credentials to environment variables."),
        ("Unsafe deserialization", r"\bpickle\.loads?\s*\(", "medium", "Do not unpickle untrusted data."),
        ("Broad exception", r"except\s*:", "medium", "Catch specific exceptions."),
        ("TODO marker", r"#\s*TODO\b", "low", "Track unfinished work explicitly."),
    ]
    for label, pattern, severity, detail in patterns:
        count = len(re.findall(pattern, code))
        if count:
            findings.append({"title": label, "severity": severity, "detail": f"{detail} Found {count} occurrence(s)."})
    score = max(0, 100 - sum({"high": 18, "medium": 8, "low": 3}[f["severity"]] for f in findings))
    metrics["score"] = score
    return _result(
        f"Review score {score}/100 with {len(findings)} finding(s).",
        {
            "metrics": metrics,
            "findings": findings,
            "table": {"columns": ["Function", "Line", "Length", "Args"], "rows": rows},
            "items": ["Add tests for the changed behavior.", "Keep functions under roughly 40 lines where practical."],
        },
        ["Heuristic review only; it does not prove the absence of vulnerabilities."],
    )


def agent_dependency_risk(payload):
    manifest = _text(payload, "manifest", max_len=120000)
    ecosystem = str(payload.get("ecosystem", "requirements")).lower()
    check_osv = bool(payload.get("check_osv", False))
    dependencies = []
    if ecosystem == "package":
        try:
            data = json.loads(manifest)
        except json.JSONDecodeError as exc:
            raise LogicError(f"manifest is not valid package.json: {exc.msg}")
        for section in ("dependencies", "devDependencies"):
            for name, constraint in (data.get(section) or {}).items():
                dependencies.append((name, str(constraint), section))
    else:
        for line in manifest.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith(("-", "git+", "http")):
                continue
            match = re.match(r"^([A-Za-z0-9_.-]+)\s*(.*)$", line)
            if match:
                dependencies.append((match.group(1), match.group(2).strip(), "runtime"))
    if not dependencies:
        raise LogicError("no dependencies were found in the manifest")
    findings, rows = [], []
    deprecated = {"request", "left-pad", "tslint", "node-sass"}
    advisories = []
    for name, constraint, section in dependencies[:200]:
        pinned = constraint.startswith("==") if ecosystem != "package" else bool(re.fullmatch(r"\d+\.\d+\.\d+", constraint))
        risky = []
        if not pinned:
            risky.append("not exactly pinned")
        if constraint.strip() in {"*", "latest", ""} or constraint.startswith(("^", "~", ">", "<")):
            risky.append("range or wildcard")
        if constraint.startswith(("git+", "http://", "https://", "file:")):
            risky.append("non-registry source")
        if name.lower() in deprecated:
            risky.append("commonly deprecated")
        rows.append([name, constraint, section, "pinned" if pinned else "floating", ", ".join(risky) or "ok"])
        if "non-registry source" in risky:
            findings.append({"title": "Unverified dependency source", "severity": "high", "detail": f"{name} is sourced outside the registry; verify provenance and integrity."})
        elif "not exactly pinned" in risky:
            findings.append({"title": "Floating version", "severity": "low", "detail": f"{name} ({constraint}) can change between installs."})
    if check_osv:
        try:
            import httpx

            for name, constraint, _ in dependencies[:30]:
                version = constraint[2:] if constraint.startswith("==") else (constraint if re.fullmatch(r"\d+\.\d+\.\d+", constraint) else None)
                if not version:
                    continue
                response = httpx.post(
                    "https://api.osv.dev/v1/query",
                    json={"package": {"name": name, "ecosystem": "PyPI" if ecosystem != "package" else "npm"}, "version": version},
                    timeout=8,
                )
                if response.status_code == 200:
                    for vuln in response.json().get("vulns", [])[:3]:
                        advisories.append([name, version, vuln.get("id", "unknown"), (vuln.get("summary") or "")[:120]])
        except Exception as exc:
            findings.append({"title": "Advisory lookup unavailable", "severity": "info", "detail": f"OSV lookup failed ({type(exc).__name__}); no advisory results are claimed."})
    for advisory in advisories:
        findings.append({"title": "OSV advisory", "severity": "high", "detail": f"{advisory[0]} {advisory[1]}: {advisory[2]} — {advisory[3]}"})
    score = max(0, 100 - len([f for f in findings if f["severity"] == "high"]) * 15 - len([f for f in findings if f["severity"] == "low"]) * 3)
    return _result(
        f"Reviewed {len(dependencies)} dependency entries; {len(advisories)} advisory record(s) returned.",
        {
            "metrics": {"dependencies": len(dependencies), "advisories": len(advisories), "score": score},
            "table": {"columns": ["Dependency", "Constraint", "Section", "Pinning", "Notes"], "rows": rows},
            "findings": findings,
        },
        ["Offline mode checks hygiene only. Enable check_osv for authoritative OSV advisory queries; no advisories are invented."],
    )


def agent_documentation_generator(payload):
    code = _text(payload, "code", max_len=80000)
    module_name = str(payload.get("module_name", "module")).strip() or "module"
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise LogicError(f"Python syntax error at line {exc.lineno}: {exc.msg}")
    rows = []
    parts = [f"# `{module_name}`", ""]
    doc = ast.get_docstring(tree)
    parts.append(doc if doc else "_No module docstring supplied._")
    parts += ["", "## Symbols", ""]
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            signature = f"{node.name}({ast.unparse(node.args)})"
            parts += [f"### `{signature}`", "", ast.get_docstring(node) or "_Undocumented._", ""]
            rows.append([node.name, "function", node.lineno, "yes" if ast.get_docstring(node) else "no"])
        elif isinstance(node, ast.ClassDef):
            parts += [f"### class `{node.name}`", "", ast.get_docstring(node) or "_Undocumented._", ""]
            rows.append([node.name, "class", node.lineno, "yes" if ast.get_docstring(node) else "no"])
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    parts += [f"- `{child.name}({ast.unparse(child.args)})` — {ast.get_docstring(child) or 'Undocumented.'}"]
                    rows.append([f"{node.name}.{child.name}", "method", child.lineno, "yes" if ast.get_docstring(child) else "no"])
            parts.append("")
    missing = sum(1 for row in rows if row[3] == "no")
    return _result(
        f"Generated documentation for {len(rows)} symbol(s); {missing} lack docstrings.",
        {"metrics": {"symbols": len(rows), "undocumented": missing}, "markdown": "\n".join(parts), "table": {"columns": ["Symbol", "Kind", "Line", "Docstring"], "rows": rows}},
        ["Documentation is extracted from source and docstrings; behavioral descriptions are not inferred."],
    )


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


def agent_data_quality_guardian(payload):
    columns, rows = _csv(payload, "csv")
    findings, table = [], []
    duplicate_keys = Counter(tuple(row[col] for col in columns) for row in rows)
    duplicate_rows = sum(count - 1 for count in duplicate_keys.values() if count > 1)
    total_missing = 0
    for column in columns:
        values = [row[column] for row in rows]
        non_empty = [v for v in values if v != ""]
        missing = len(values) - len(non_empty)
        total_missing += missing
        unique = len(set(non_empty))
        inferred, invalid = "text", 0
        if non_empty:
            sample = non_empty[:200]
            if all(re.fullmatch(r"-?\d+", v) for v in sample):
                inferred = "integer"
                invalid = sum(1 for v in non_empty if not re.fullmatch(r"-?\d+", v))
            elif all(re.fullmatch(r"-?\d+(\.\d+)?", v) for v in sample):
                inferred = "number"
                invalid = sum(1 for v in non_empty if not re.fullmatch(r"-?\d+(\.\d+)?", v))
            elif all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) for v in sample):
                inferred = "date"
                invalid = sum(1 for v in non_empty if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v))
            elif all(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v) for v in sample):
                inferred = "email"
                invalid = sum(1 for v in non_empty if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v))
        missing_rate = missing / len(rows)
        invalid_rate = invalid / max(1, len(non_empty))
        if missing_rate > 0.2:
            findings.append({"title": "High missing rate", "severity": "high" if missing_rate > 0.5 else "medium", "detail": f"Column '{column}' is {missing_rate:.0%} empty."})
        if invalid_rate > 0:
            findings.append({"title": "Invalid values", "severity": "medium", "detail": f"Column '{column}' has {invalid} value(s) that do not match inferred type {inferred}."})
        table.append([column, missing, f"{missing_rate:.0%}", unique, inferred, invalid])
    duplicate_rate = duplicate_rows / max(1, len(rows))
    if duplicate_rows:
        findings.append({"title": "Duplicate rows", "severity": "medium", "detail": f"{duplicate_rows} duplicate row(s) detected."})
    score = max(0, round(100 - (total_missing / max(1, len(rows) * len(columns))) * 40 - duplicate_rate * 30 - len([f for f in findings if f["title"] == "Invalid values"]) * 5))
    return _result(
        f"Quality score {score}/100 across {len(rows)} rows and {len(columns)} columns.",
        {
            "metrics": {"score": score, "rows": len(rows), "columns": len(columns), "duplicate_rows": duplicate_rows, "missing_cells": total_missing},
            "table": {"columns": ["Column", "Missing", "Missing %", "Unique", "Inferred type", "Invalid"], "rows": table},
            "findings": findings,
        },
        ["Type inference uses the first 200 non-empty values per column; review edge cases before loading."],
    )


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


def agent_csv_insights(payload):
    columns, rows = _csv(payload, "csv")
    numeric = {}
    for column in columns:
        values = []
        for row in rows:
            if row[column] == "":
                continue
            try:
                values.append(float(row[column]))
            except ValueError:
                pass
        if len(values) >= max(2, len(rows) * 0.5):
            numeric[column] = values
    stats_rows = []
    for column in columns:
        values = numeric.get(column)
        if values:
            stats_rows.append([column, "number", len(values), round(statistics.fmean(values), 3), round(statistics.median(values), 3), round(min(values), 3), round(max(values), 3)])
        else:
            counts = Counter(row[column] for row in rows if row[column])
            top = counts.most_common(1)[0] if counts else ("", 0)
            stats_rows.append([column, "text", len([r for r in rows if r[column]]), "", "", "", f"top: {top[0]} ({top[1]})"])
    correlations = []
    names = list(numeric)
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            try:
                value = statistics.correlation(numeric[left], numeric[right])
                correlations.append([left, right, round(value, 3)])
            except statistics.StatisticsError:
                pass
    chart = None
    if numeric:
        first = names[0]
        values = numeric[first]
        low, high = min(values), max(values)
        bins = [0] * 8
        width = (high - low) / 8 if high > low else 1
        for value in values:
            bins[min(7, int((value - low) / width))] += 1
        chart = {"labels": [f"{low + i * width:.1f}" for i in range(8)], "values": bins}
    markdown = f"## Dataset summary\n\n- Rows: **{len(rows)}**\n- Columns: **{len(columns)}**\n- Numeric columns: **{len(numeric)}**\n\n" + "\n".join(f"- `{column}`: {len(values)} numeric values" for column, values in numeric.items())
    return _result(
        f"Profiled {len(rows)} rows across {len(columns)} columns; {len(numeric)} numeric column(s).",
        {
            "metrics": {"rows": len(rows), "columns": len(columns), "numeric_columns": len(numeric), "correlations": len(correlations)},
            "table": {"columns": ["Column", "Kind", "Count", "Mean", "Median", "Min", "Max / Top"], "rows": stats_rows},
            "chart": chart,
            "markdown": markdown,
        },
        ["Summary statistics describe the supplied sample only; they are not population estimates."],
    )


def agent_schema_drift(payload):
    old = _json(payload, "old_schema", (dict, list))
    new = _json(payload, "new_schema", (dict, list))

    def normalize(schema):
        if isinstance(schema, dict):
            return {str(k): str(v) for k, v in schema.items()}
        result = {}
        for item in schema:
            if not isinstance(item, dict) or "name" not in item:
                raise LogicError("schema list entries need a 'name'")
            result[str(item["name"])] = str(item.get("type", "unknown"))
        return result

    before, after = normalize(old), normalize(new)
    rows, findings = [], []
    for name in sorted(set(before) | set(after)):
        if name not in after:
            rows.append([name, before[name], "-", "removed", "yes"])
            findings.append({"title": "Column removed", "severity": "high", "detail": f"'{name}' is absent from the new schema and may break consumers."})
        elif name not in before:
            rows.append([name, "-", after[name], "added", "no"])
        elif before[name] != after[name]:
            rows.append([name, before[name], after[name], "type changed", "yes"])
            findings.append({"title": "Column type changed", "severity": "high", "detail": f"'{name}' changed from {before[name]} to {after[name]}."})
    breaking = sum(1 for row in rows if row[4] == "yes")
    return _result(
        f"Detected {len(rows)} schema change(s); {breaking} breaking.",
        {
            "metrics": {"changes": len(rows), "breaking": breaking, "added": sum(1 for r in rows if r[3] == "added"), "removed": sum(1 for r in rows if r[3] == "removed")},
            "table": {"columns": ["Column", "Old type", "New type", "Change", "Breaking"], "rows": rows},
            "findings": findings,
        },
        ["Type compatibility is compared textually; database-specific widening rules are not applied."],
    )
