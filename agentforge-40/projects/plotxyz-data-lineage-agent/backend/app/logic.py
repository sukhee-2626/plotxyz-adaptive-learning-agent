"""Original deterministic implementation for Data Lineage (plotxyz-data-lineage-agent)."""
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


def agent_data_lineage(payload):
    lineage = _json(payload, "lineage", dict)
    raw_nodes = lineage.get("nodes", [])
    raw_edges = lineage.get("edges", [])
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise LogicError("lineage.nodes and lineage.edges must be lists")
    nodes = {}
    for item in raw_nodes:
        if isinstance(item, str):
            node_id, kind = item, "dataset"
        elif isinstance(item, dict) and (item.get("id") or item.get("name")):
            node_id = str(item.get("id") or item.get("name"))
            kind = str(item.get("type", "dataset"))
        else:
            raise LogicError("each lineage node needs an id")
        if node_id in nodes:
            raise LogicError(f"duplicate lineage node '{node_id}'")
        nodes[node_id] = kind
    if not nodes:
        raise LogicError("at least one lineage node is required")
    edges, adjacency, reverse = [], defaultdict(list), defaultdict(list)
    for item in raw_edges:
        if not isinstance(item, dict):
            raise LogicError("each lineage edge must be an object")
        source = str(item.get("from") or item.get("source") or "")
        target = str(item.get("to") or item.get("target") or "")
        if source not in nodes or target not in nodes:
            raise LogicError(f"edge references an unknown node: {source} -> {target}")
        label = str(item.get("transform") or item.get("label") or "")
        edges.append({"source": source, "target": target, "label": label})
        adjacency[source].append(target)
        reverse[target].append(source)
    target = str(payload.get("target", "")).strip() or list(nodes)[-1]
    if target not in nodes:
        raise LogicError(f"target node '{target}' was not found")
    def walk(start, graph):
        seen, queue = set(), deque(graph[start])
        while queue:
            node = queue.popleft()
            if node in seen:
                continue
            seen.add(node)
            queue.extend(graph[node])
        return sorted(seen)
    upstream, downstream = walk(target, reverse), walk(target, adjacency)
    state, cycle = {}, False
    def visit(node):
        nonlocal cycle
        if state.get(node) == 1:
            cycle = True
            return
        if state.get(node) == 2:
            return
        state[node] = 1
        for nxt in adjacency[node]:
            visit(nxt)
        state[node] = 2
    for node in nodes:
        visit(node)
    findings = []
    if cycle:
        findings.append({"title": "Lineage cycle", "severity": "high", "detail": "The declared graph contains a cycle, so upstream/downstream impact is ambiguous."})
    orphans = [node for node in nodes if not adjacency[node] and not reverse[node] and node != target]
    if orphans:
        findings.append({"title": "Disconnected nodes", "severity": "low", "detail": f"{len(orphans)} node(s) have no declared relationship: {', '.join(orphans[:6])}."})
    rows = [[edge["source"], edge["target"], edge["label"] or "-"] for edge in edges]
    graph = {
        "nodes": [{"id": node, "label": node, "type": kind} for node, kind in nodes.items()],
        "edges": [{"source": edge["source"], "target": edge["target"], "label": edge["label"]} for edge in edges],
    }
    return _result(
        f"{target} has {len(upstream)} upstream and {len(downstream)} downstream node(s).",
        {
            "metrics": {"nodes": len(nodes), "edges": len(edges), "upstream": len(upstream), "downstream": len(downstream), "cycle": cycle},
            "graph": graph,
            "table": {"columns": ["From", "To", "Transform"], "rows": rows},
            "items": [f"Upstream: {', '.join(upstream) or 'none'}", f"Downstream: {', '.join(downstream) or 'none'}"],
            "findings": findings,
        },
        ["Lineage reflects only the declared graph; runtime lineage is not observed."],
    )


run = agent_data_lineage
