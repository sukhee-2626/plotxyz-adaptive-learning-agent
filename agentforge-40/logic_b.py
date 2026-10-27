"""Deterministic logic for PlotXYZ.ai agents 21-40 (original implementations)."""
from __future__ import annotations

import json
import math
import re
import statistics
from collections import Counter, defaultdict, deque

from logic_common import (
    LogicError,
    _csv,
    _json,
    _num,
    _result,
    _sentences,
    _text,
    _tokens,
)


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


def agent_sql_performance(payload):
    explain = _text(payload, "explain", max_len=60000)
    query = str(payload.get("query", "")).strip()
    node_pattern = re.compile(r"\b(Seq Scan|Index Scan|Index Only Scan|Bitmap Heap Scan|Nested Loop|Hash Join|Merge Join|Sort|Aggregate|Limit|CTE Scan)\b", re.I)
    cost_pattern = re.compile(r"cost=(\d+(?:\.\d+)?)\.\.(\d+(?:\.\d+)?)")
    rows_pattern = re.compile(r"rows=(\d+)")
    nodes, findings = [], []
    for line in explain.splitlines():
        match = node_pattern.search(line)
        if not match:
            continue
        cost_match = cost_pattern.search(line)
        rows_match = rows_pattern.search(line)
        cost = float(cost_match.group(2)) if cost_match else None
        estimate = int(rows_match.group(1)) if rows_match else None
        kind = match.group(1)
        issue = "-"
        if kind.lower() == "seq scan" and (estimate is None or estimate > 1000):
            issue = "large sequential scan"
            findings.append({"title": "Sequential scan on a large relation", "severity": "high", "detail": f"Plan reports a Seq Scan with estimated rows {estimate}. Consider a selective index."})
        elif kind.lower() == "nested loop" and estimate and estimate > 10000:
            issue = "high-row nested loop"
            findings.append({"title": "Expensive nested loop", "severity": "medium", "detail": f"Nested loop estimates {estimate} rows; verify join indexes and statistics."})
        elif kind.lower() == "sort" and "external" in line.lower():
            issue = "external sort"
            findings.append({"title": "External sort", "severity": "medium", "detail": "Increase work_mem or reduce the sorted row count."})
        elif kind.lower() in {"hash join", "merge join"} and cost and cost > 100000:
            issue = "high-cost join"
            findings.append({"title": "High-cost join", "severity": "medium", "detail": f"Join cost reaches {cost:g}; inspect cardinality estimates."})
        nodes.append([kind, round(cost, 2) if cost is not None else "-", estimate if estimate is not None else "-", issue])
    if not nodes:
        findings.append({"title": "No recognized plan nodes", "severity": "info", "detail": "The supplied text does not contain common EXPLAIN node names."})
    seq_scans = sum(1 for node in nodes if node[0].lower() == "seq scan")
    score = max(0, 100 - seq_scans * 12 - len([f for f in findings if f["severity"] == "high"]) * 10 - len([f for f in findings if f["severity"] == "medium"]) * 5)
    suggestions = []
    if seq_scans:
        suggestions.append("Add or adjust indexes for predicates that filter many rows.")
    if "order by" in (query + explain).lower():
        suggestions.append("Consider an index matching the ORDER BY columns to avoid a sort.")
    suggestions += ["Refresh table statistics after large data changes.", "Compare estimated rows with actual rows to detect stale statistics."]
    return _result(
        f"Plan review score {score}/100 across {len(nodes)} recognized node(s).",
        {
            "metrics": {"score": score, "seq_scans": seq_scans, "nodes": len(nodes)},
            "table": {"columns": ["Node", "Total cost", "Estimated rows", "Issue"], "rows": nodes},
            "findings": findings,
            "items": suggestions,
        },
        ["This analyzes supplied EXPLAIN text; it does not connect to or modify a database."],
    )


def agent_data_documentation(payload):
    schema = _json(payload, "schema", (dict, list))
    sample_text = str(payload.get("sample_csv", "")).strip()
    sample_rows = []
    sample_columns = []
    if sample_text:
        sample_columns, sample_rows = _csv({"sample_csv": sample_text}, "sample_csv", max_rows=1000)
    if isinstance(schema, dict):
        columns = [{"name": str(k), "type": str(v)} for k, v in schema.items()]
    else:
        columns = []
        for item in schema:
            if not isinstance(item, dict) or "name" not in item:
                raise LogicError("schema entries need a name")
            columns.append({"name": str(item["name"]), "type": str(item.get("type", "unknown")), "description": str(item.get("description", ""))})
    if not columns:
        raise LogicError("schema must describe at least one column")
    rows, missing = [], 0
    for column in columns:
        name = column["name"]
        description = column.get("description") or ""
        if not description:
            words = re.sub(r"[_-]+", " ", name).split()
            description = " ".join(word.capitalize() for word in words)
            if name.endswith("_id"):
                description += " identifier"
            missing += 1
        sample_info = ""
        if name in sample_columns:
            values = [row[name] for row in sample_rows if row.get(name)]
            unique = len(set(values))
            sample_info = f"{len(values)} non-empty, {unique} distinct"
        rows.append([name, column["type"], description, sample_info or "-"])
    markdown = "## Data dictionary\n\n| Column | Type | Description | Sample |\n| :-- | :-- | :-- | :-- |\n" + "\n".join(f"| `{r[0]}` | {r[1]} | {r[2]} | {r[3]} |" for r in rows)
    return _result(
        f"Documented {len(columns)} column(s); {missing} description(s) inferred from names.",
        {
            "metrics": {"columns": len(columns), "inferred_descriptions": missing, "sample_rows": len(sample_rows)},
            "table": {"columns": ["Column", "Type", "Description", "Sample"], "rows": rows},
            "markdown": markdown,
        },
        ["Inferred descriptions are naming heuristics, not verified business definitions."],
    )


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


def agent_knowledge_graph(payload):
    text = _text(payload, "text", max_len=60000)
    sentences = _sentences(text)
    if not sentences:
        raise LogicError("no readable sentences were supplied")
    ignore = {"The", "This", "That", "These", "Those", "A", "An", "In", "On", "For", "With", "And", "But", "It", "We", "They", "Our", "Your", "However", "When", "While"}
    counts = Counter()
    relations = Counter()
    for sentence in sentences:
        found = []
        for match in re.finditer(r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)\b", sentence):
            entity = match.group(1).strip()
            if entity in ignore or len(entity) < 3:
                continue
            found.append(entity)
            counts[entity] += 1
        unique = sorted(set(found))
        for i, left in enumerate(unique):
            for right in unique[i + 1:]:
                relations[(left, right)] += 1
    if not counts:
        raise LogicError("no entity-like capitalized phrases were found")
    top = [entity for entity, _ in counts.most_common(20)]
    allowed = set(top)
    edges = [{"source": a, "target": b, "weight": weight, "label": f"co-occurs ({weight})"} for (a, b), weight in relations.most_common(60) if a in allowed and b in allowed]
    nodes = [{"id": entity, "label": entity, "count": counts[entity]} for entity in top]
    rows = [[entity, counts[entity]] for entity in top[:15]]
    return _result(
        f"Extracted {len(nodes)} entities and {len(edges)} co-occurrence edges from {len(sentences)} sentences.",
        {
            "metrics": {"entities": len(nodes), "edges": len(edges), "sentences": len(sentences)},
            "graph": {"nodes": nodes, "edges": edges},
            "table": {"columns": ["Entity", "Mentions"], "rows": rows},
            "items": [f"{edge['source']} ↔ {edge['target']}" for edge in edges[:6]],
        },
        ["Entity extraction is capitalization-based; it does not perform named-entity recognition or resolve aliases."],
    )


def agent_document_to_action(payload):
    text = _text(payload, "text", max_len=60000)
    lines = [line.strip(" -•\t") for line in re.split(r"\n+|(?<=[.!?])\s+", text) if line.strip()]
    verbs = re.compile(r"\b(will|should|must|need to|needs to|action|todo|to-do|follow up|prepare|send|review|schedule|confirm|create|update|fix|deliver)\b", re.I)
    actions = []
    for line in lines:
        if not verbs.search(line) and not line.startswith(("TODO", "Action")):
            continue
        owner_match = re.search(r"@([A-Za-z0-9_.-]+)", line) or re.search(r"^([A-Z][a-z]+)\s+(?:will|should|must|needs? to)\b", line)
        owner = owner_match.group(1) if owner_match else "unassigned"
        due_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", line) or re.search(r"\b(?:by|before)\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b", line, re.I)
        due = due_match.group(1) if due_match else "not specified"
        priority = "high" if re.search(r"\b(urgent|asap|critical|blocker)\b", line, re.I) else "normal"
        cleaned = re.sub(r"@[A-Za-z0-9_.-]+", "", line).strip()
        actions.append([cleaned[:300], owner, due, priority])
    if not actions:
        raise LogicError("no action-like statements were detected; add explicit tasks or modal verbs")
    table = {"columns": ["Task", "Owner", "Due", "Priority"], "rows": actions}
    markdown = "## Action checklist\n\n" + "\n".join(f"- [ ] **{a[1]}** — {a[0]} (due: {a[2]}, {a[3]})" for a in actions)
    findings = []
    unassigned = sum(1 for action in actions if action[1] == "unassigned")
    if unassigned:
        findings.append({"title": "Unassigned tasks", "severity": "medium", "detail": f"{unassigned} action(s) have no explicit owner."})
    if any(action[2] == "not specified" for action in actions):
        findings.append({"title": "Missing due dates", "severity": "low", "detail": "Some actions have no explicit deadline."})
    return _result(
        f"Extracted {len(actions)} action item(s); {len(actions) - unassigned} have owners.",
        {"metrics": {"actions": len(actions), "unassigned": unassigned}, "table": table, "markdown": markdown, "findings": findings},
        ["Extraction is rule-based; confirm owners and dates with the source document."],
    )


def agent_evidence_verification(payload):
    claims_text = _text(payload, "claims", max_len=30000)
    sources = _text(payload, "sources", max_len=120000)
    claims = [line.strip(" -•") for line in claims_text.splitlines() if line.strip()]
    sentences = _sentences(sources)
    if not claims or not sentences:
        raise LogicError("supply at least one claim and one source sentence")
    negation = re.compile(r"\b(not|no|never|none|cannot|can't|without)\b", re.I)
    rows, findings = [], []
    for claim in claims[:30]:
        claim_tokens = set(_tokens(claim))
        best_score, best_sentence = 0.0, ""
        for sentence in sentences:
            sentence_tokens = set(_tokens(sentence))
            overlap = len(claim_tokens & sentence_tokens) / max(1, len(claim_tokens))
            if bool(negation.search(claim)) != bool(negation.search(sentence)):
                overlap *= 0.5
            if overlap > best_score:
                best_score, best_sentence = overlap, sentence
        label = "supported" if best_score >= 0.65 else "partial" if best_score >= 0.35 else "unsupported"
        if label == "unsupported":
            findings.append({"title": "Unsupported claim", "severity": "high", "detail": claim[:180]})
        elif label == "partial":
            findings.append({"title": "Weakly supported claim", "severity": "medium", "detail": claim[:180]})
        rows.append([claim[:240], label, round(best_score, 2), best_sentence[:240] if best_sentence else "-"])
    return _result(
        f"Checked {len(rows)} claim(s): {sum(1 for r in rows if r[1] == 'supported')} supported, {sum(1 for r in rows if r[1] == 'partial')} partial, {sum(1 for r in rows if r[1] == 'unsupported')} unsupported.",
        {
            "metrics": {"claims": len(rows), "supported": sum(1 for r in rows if r[1] == "supported"), "unsupported": sum(1 for r in rows if r[1] == "unsupported")},
            "table": {"columns": ["Claim", "Assessment", "Lexical score", "Best evidence"], "rows": rows},
            "findings": findings,
        },
        ["This is lexical overlap with negation checks, not entailment or fact-checking. Absence of evidence is not proof of falsehood."],
    )


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


def agent_meeting_intelligence(payload):
    transcript = _text(payload, "transcript", max_len=120000)
    lines = [line.strip() for line in transcript.splitlines() if line.strip()]
    speakers = Counter()
    actions, decisions = [], []
    warnings = []
    labelled = 0
    for line in lines:
        match = re.match(r"^([A-Z][A-Za-z .'-]{0,40}):\s*(.+)$", line)
        if match:
            labelled += 1
            speaker, content = match.group(1).strip(), match.group(2).strip()
            speakers[speaker] += 1
        else:
            speaker, content = "Unknown", line
        if re.search(r"\b(decided|agreed|approved|conclusion|we will go with)\b", content, re.I):
            decisions.append([speaker, content[:300]])
        if re.search(r"\b(will|should|action|todo|follow up|next step|owns|by Friday|by Monday)\b", content, re.I):
            owner = speaker if speaker != "Unknown" else "unassigned"
            due = re.search(r"\b(?:by|before)\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|\d{4}-\d{2}-\d{2})\b", content, re.I)
            actions.append([content[:300], owner, due.group(1) if due else "not specified"])
    if not labelled:
        warnings.append("No 'Name: text' speaker labels were detected; owners default to 'Unknown'.")
    if not actions and not decisions:
        warnings.append("No decisions or action items were detected with the current rules.")
    table = {"columns": ["Action", "Owner", "Due"], "rows": actions}
    markdown = "## Minutes\n\n### Decisions\n" + ("\n".join(f"- **{d[0]}**: {d[1]}" for d in decisions) or "- None detected.") + "\n\n### Action items\n" + ("\n".join(f"- [ ] {a[1]} — {a[0]} (due: {a[2]})" for a in actions) or "- None detected.")
    return _result(
        f"Processed {len(lines)} transcript line(s): {len(decisions)} decision(s), {len(actions)} action(s), {len(speakers)} speaker(s).",
        {
            "metrics": {"lines": len(lines), "speakers": len(speakers), "decisions": len(decisions), "actions": len(actions)},
            "table": table,
            "markdown": markdown,
            "items": [f"{speaker}: {count} turns" for speaker, count in speakers.most_common(8)],
        },
        warnings + ["Extraction is keyword-based; verify minutes against the recording."],
    )


def agent_contract_review(payload):
    text = _text(payload, "text", max_len=120000)
    lowered = text.lower()
    categories = {
        "Payment": r"\b(payment|fee|invoice|compensation|price)\b",
        "Termination": r"\b(terminate|termination|notice period)\b",
        "Liability": r"\b(liability|liable|indemnif|damages)\b",
        "Confidentiality": r"\b(confidential|non-disclosure|nda)\b",
        "Renewal": r"\b(renew|renews|renewal|renewed|auto-renew|automatically renew)\b",
        "Intellectual property": r"\b(intellectual property|ip ownership|copyright|license)\b",
        "Governing law": r"\b(governing law|jurisdiction|venue)\b",
    }
    rows, findings = [], []
    score = 100
    for label, pattern in categories.items():
        match = re.search(pattern, lowered)
        if match:
            start = max(0, match.start() - 80)
            excerpt = text[start:match.end() + 160].replace("\n", " ").strip()
            rows.append([label, "detected", excerpt[:260]])
        else:
            rows.append([label, "not detected", "-"])
            findings.append({"title": f"{label} clause not detected", "severity": "info", "detail": "Not detected in the supplied excerpt; this does not prove the clause is absent."})
    risks = [
        ("Automatic renewal", r"auto(?:matically)?[- ]renew", "high"),
        ("Unlimited liability", r"unlimited liability", "high"),
        ("Sole discretion", r"sole discretion", "medium"),
        ("Unilateral termination", r"(?:terminate|modify)[^.]{0,60}(?:sole|unilateral|without cause)", "medium"),
        ("Broad indemnity", r"indemnif", "medium"),
    ]
    for label, pattern, severity in risks:
        if re.search(pattern, lowered):
            findings.append({"title": label, "severity": severity, "detail": f"Potentially one-sided language detected: {label.lower()}."})
            score -= 12 if severity == "high" else 6
    score = max(0, score)
    return _result(
        f"Detected {sum(1 for r in rows if r[1] == 'detected')} of {len(categories)} clause categories; review score {score}/100.",
        {
            "metrics": {"clauses_detected": sum(1 for r in rows if r[1] == "detected"), "risk_flags": sum(1 for f in findings if f["severity"] in {"high", "medium"}), "score": score},
            "table": {"columns": ["Clause", "Status", "Excerpt"], "rows": rows},
            "findings": findings,
        },
        ["This is not legal advice. Clause extraction is keyword-based; a qualified professional must review the full contract."],
    )


def agent_knowledge_gap(payload):
    notes = _text(payload, "notes", max_len=80000)
    questions_text = _text(payload, "questions", max_len=20000)
    questions = [line.strip(" -•") for line in questions_text.splitlines() if line.strip()]
    if not questions:
        raise LogicError("supply at least one research question")
    note_tokens = set(_tokens(notes))
    rows, findings = [], []
    for question in questions[:30]:
        tokens = set(_tokens(question))
        if not tokens:
            continue
        covered = tokens & note_tokens
        coverage = len(covered) / len(tokens)
        missing = sorted(tokens - note_tokens)
        status = "covered" if coverage >= 0.75 else "partial" if coverage >= 0.35 else "gap"
        if status != "covered":
            findings.append({"title": "Knowledge gap", "severity": "medium" if status == "gap" else "low", "detail": f"Question '{question[:100]}' is missing evidence for: {', '.join(missing[:6]) or 'most terms'}."})
        rows.append([question[:220], status, f"{coverage:.0%}", ", ".join(missing[:8]) or "-"])
    gaps = sum(1 for row in rows if row[1] == "gap")
    return _result(
        f"Assessed {len(rows)} question(s): {len(rows) - gaps} covered or partial, {gaps} explicit gap(s).",
        {
            "metrics": {"questions": len(rows), "gaps": gaps, "coverage_avg": round(statistics.fmean([float(r[2].rstrip('%')) for r in rows]) / 100, 3) if rows else 0},
            "table": {"columns": ["Question", "Status", "Term coverage", "Missing terms"], "rows": rows},
            "items": [f"Search for: {row[3]}" for row in rows if row[3] != "-"][:8],
            "findings": findings,
        },
        ["Coverage is lexical: notes may address a question using different vocabulary."],
    )


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


def agent_startup_cofounder(payload):
    idea = _text(payload, "idea", max_len=6000)
    audience = _text(payload, "audience", max_len=2000)
    constraints = str(payload.get("constraints", "")).strip()
    weeks = int(_num(payload, "timeline_weeks", default=8, lo=4, hi=24))
    lowered = idea.lower()
    feature_pool = [
        (("ai", "agent", "model"), "AI-assisted core workflow with human review"),
        (("market", "seller", "buyer"), "Two-sided marketplace onboarding"),
        (("data", "analytic", "dashboard"), "Analytics dashboard and export"),
        (("health", "fitness", "wellness"), "Progress tracking and reminders"),
        (("learn", "course", "student"), "Personalized learning path"),
        (("finance", "payment", "invoice"), "Payments and reconciliation"),
        (("collab", "team", "project"), "Shared workspace and roles"),
    ]
    features = [label for keywords, label in feature_pool if any(keyword in lowered for keyword in keywords)]
    features = (features + ["Onboarding and account setup", "Core CRUD workflow", "Notification preferences", "Admin reporting"])[:6]
    personas = [
        {"name": "Primary user", "need": audience, "success": "Completes the core job in under five minutes."},
        {"name": "Operations owner", "need": "Visibility into usage, exceptions, and support requests.", "success": "Resolves issues without engineering help."},
    ]
    phases = [("Discovery", 0.15), ("MVP build", 0.40), ("Private beta", 0.25), ("Launch", 0.20)]
    roadmap, start = [], 1
    for name, share in phases:
        duration = max(1, round(weeks * share))
        roadmap.append([name, f"Week {start}–{start + duration - 1}", f"{duration} week(s)"])
        start += duration
    backlog = []
    for index, feature in enumerate(features, 1):
        estimate = 2 + (index % 3)
        priority = "P0" if index <= 2 else "P1" if index <= 4 else "P2"
        backlog.append([feature, priority, estimate, "product + engineering"])
    risks = []
    if "ai" in lowered:
        risks.append({"title": "Model quality risk", "severity": "medium", "detail": "Define an evaluation set and a deterministic fallback before launch."})
    if "market" in lowered:
        risks.append({"title": "Cold-start marketplace risk", "severity": "high", "detail": "Pick one side of the market and seed supply manually."})
    risks.append({"title": "Scope risk", "severity": "medium", "detail": f"A {weeks}-week plan with {len(features)} MVP features leaves little buffer; cut P2 items first."})
    markdown = f"""## MVP specification

**Idea:** {idea}

**Audience:** {audience}

### Value proposition
A focused product that helps {audience} achieve the core outcome with less manual work and clear human oversight.

### Personas
""" + "\n".join(f"- **{p['name']}** — {p['need']} Success: {p['success']}" for p in personas) + """

### MVP features
""" + "\n".join(f"{i}. {feature}" for i, feature in enumerate(features, 1)) + f"""

### Roadmap ({weeks} weeks)
""" + "\n".join(f"- **{r[0]}** ({r[1]}): {r[2]}" for r in roadmap) + """

### Constraints
""" + (constraints or "No explicit constraints supplied; assume a small founding team and a fixed budget.")
    return _result(
        f"Generated an MVP spec with {len(features)} features and a {weeks}-week roadmap.",
        {
            "metrics": {"features": len(features), "weeks": weeks, "backlog_items": len(backlog), "risks": len(risks)},
            "table": {"columns": ["Backlog item", "Priority", "Estimate (days)", "Owner"], "rows": backlog},
            "markdown": markdown,
            "findings": risks,
            "items": [f"{r[0]}: {r[1]}" for r in roadmap],
        },
        ["Planning output is a rule-based first draft; validate demand and estimates with real users."],
    )


def agent_workflow_builder(payload):
    data = _json(payload, "data")
    workflow = _json(payload, "workflow", list)
    if not workflow:
        raise LogicError("'workflow' must contain at least one step")
    if len(workflow) > 50:
        raise LogicError("workflow is limited to 50 steps")

    def get_path(document, path):
        current = document
        for part in str(path).split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
            else:
                raise LogicError(f"path not found: {path}")
        return current

    def set_path(document, path, value):
        parts = str(path).split(".")
        current = document
        for part in parts[:-1]:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                raise LogicError(f"path not found: {path}")
        if not isinstance(current, dict):
            raise LogicError(f"cannot set path: {path}")
        current[parts[-1]] = value

    log = []
    for index, step in enumerate(workflow, 1):
        if not isinstance(step, dict) or "op" not in step:
            raise LogicError(f"step {index} must be an object with an 'op'")
        op = str(step["op"]).lower()
        try:
            if op == "set":
                set_path(data, step.get("path", ""), step.get("value"))
            elif op in {"uppercase", "lowercase"}:
                path = step.get("path", "")
                value = get_path(data, path)
                if not isinstance(value, str):
                    raise LogicError("value is not a string")
                set_path(data, path, value.upper() if op == "uppercase" else value.lower())
            elif op == "replace":
                path = step.get("path", "")
                value = get_path(data, path)
                if not isinstance(value, str):
                    raise LogicError("value is not a string")
                set_path(data, path, value.replace(str(step.get("find", "")), str(step.get("replace", ""))))
            elif op == "extract":
                set_path(data, step.get("as", "result"), get_path(data, step.get("path", "")))
            elif op == "append":
                path = step.get("path", "")
                value = get_path(data, path)
                if not isinstance(value, list):
                    raise LogicError("value is not a list")
                value.append(step.get("value"))
            elif op == "multiply":
                path = step.get("path", "")
                value = get_path(data, path)
                set_path(data, path, float(value) * float(step.get("factor", 1)))
            elif op == "filter":
                path = step.get("path", "")
                items = get_path(data, path)
                if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
                    raise LogicError("filter target must be a list of objects")
                field = str(step.get("field", ""))
                comparator = str(step.get("op_type", "eq")).lower()
                target = step.get("value")
                if comparator == "eq":
                    kept = [item for item in items if item.get(field) == target]
                elif comparator == "ne":
                    kept = [item for item in items if item.get(field) != target]
                elif comparator == "contains":
                    kept = [item for item in items if str(target).lower() in str(item.get(field, "")).lower()]
                elif comparator in {"gt", "lt"}:
                    kept = []
                    for item in items:
                        try:
                            left, right = float(item.get(field)), float(target)
                        except (TypeError, ValueError):
                            continue
                        if (comparator == "gt" and left > right) or (comparator == "lt" and left < right):
                            kept.append(item)
                else:
                    raise LogicError(f"unsupported filter comparison '{comparator}'")
                set_path(data, path, kept)
            else:
                raise LogicError(f"unsupported op '{op}'")
            log.append([index, op, "ok", ""])
        except LogicError as exc:
            log.append([index, op, "failed", str(exc)])
            raise LogicError(f"step {index} ({op}): {exc}")
    return _result(
        f"Executed {len(workflow)} workflow step(s) with allowlisted operations.",
        {
            "metrics": {"steps": len(workflow), "succeeded": sum(1 for row in log if row[2] == "ok")},
            "table": {"columns": ["Step", "Op", "Status", "Detail"], "rows": log},
            "data": data,
            "items": ["Workflow used only in-memory set/transform/filter operations; no shell or HTTP calls are available."],
        },
        ["Inspect the output data before using it downstream. Workflow operations are intentionally limited."],
    )


def agent_multi_agent_project_manager(payload):
    brief = _text(payload, "brief", max_len=8000)
    tasks_text = _text(payload, "tasks", max_len=20000)
    team_size = int(_num(payload, "team_size", default=3, lo=1, hi=50))
    deadline = int(_num(payload, "deadline_days", default=10, lo=1, hi=365))
    tasks = [line.strip(" -•") for line in tasks_text.splitlines() if line.strip()]
    if not tasks:
        raise LogicError("supply at least one task")
    tasks = tasks[:40]

    def planner(task):
        lowered = task.lower()
        if any(word in lowered for word in ("research", "interview", "discover", "spec")):
            return "Discovery"
        if any(word in lowered for word in ("design", "mock", "prototype", "architecture")):
            return "Design"
        if any(word in lowered for word in ("test", "qa", "review", "audit")):
            return "Validation"
        if any(word in lowered for word in ("launch", "deploy", "release", "migrate")):
            return "Launch"
        return "Build"

    def estimator(task):
        days = 1 + min(len(task) / 60, 2)
        lowered = task.lower()
        for keyword, extra in (("integration", 2), ("migration", 3), ("security", 2), ("payment", 2), ("auth", 1.5)):
            if keyword in lowered:
                days += extra
        return round(min(10, days), 1)

    def risk_handler(task):
        lowered = task.lower()
        flags = []
        if any(word in lowered for word in ("auth", "payment", "security")):
            flags.append("security-sensitive")
        if any(word in lowered for word in ("migration", "legacy")):
            flags.append("data-migration")
        if any(word in lowered for word in ("third-party", "vendor", "external")):
            flags.append("external dependency")
        return flags

    def reviewer(task):
        phase = planner(task)
        return {
            "Discovery": "Acceptance: problem statement, user segment, and success metric agreed.",
            "Design": "Acceptance: reviewed flow, edge cases, and accessibility notes.",
            "Build": "Acceptance: tests pass, error states covered, and docs updated.",
            "Validation": "Acceptance: risks tested, regressions checked, and sign-off recorded.",
            "Launch": "Acceptance: rollback plan, monitoring, and owner on call.",
        }[phase]

    rows, findings = [], []
    total_estimate = 0
    for task in tasks:
        phase = planner(task)
        estimate = estimator(task)
        total_estimate += estimate
        flags = risk_handler(task)
        rows.append([task[:180], phase, estimate, flags[0] if flags else "none", reviewer(task)])
        for flag in flags:
            findings.append({"title": f"{flag.title()} task", "severity": "medium", "detail": task[:140]})
    capacity = team_size * deadline
    feasible = total_estimate <= capacity
    if not feasible:
        findings.append({"title": "Plan exceeds capacity", "severity": "high", "detail": f"Estimated {total_estimate:.1f} person-days against {capacity} available person-days. Cut scope or extend the deadline."})
    markdown = f"""## Delivery plan

**Brief:** {brief}

**Team:** {team_size} people · **Deadline:** {deadline} days · **Estimated effort:** {total_estimate:.1f} person-days · **Capacity:** {capacity} person-days

### Delegation table
| Task | Phase | Estimate | Risk | Acceptance |
| :-- | :-- | --: | :-- | :-- |
""" + "\n".join(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |" for r in rows) + """

### Recommendation
""" + ("The plan fits within capacity; keep a 15% buffer for review and rework." if feasible else "The plan does not fit. Remove P2 scope or extend the deadline before committing.")
    return _result(
        f"Delegated {len(tasks)} task(s) across {team_size} people; estimated {total_estimate:.1f} person-days against {capacity} available.",
        {
            "metrics": {"tasks": len(tasks), "estimate_days": round(total_estimate, 1), "capacity_days": capacity, "feasible": feasible},
            "table": {"columns": ["Task", "Phase", "Estimate (days)", "Risk", "Acceptance"], "rows": rows},
            "markdown": markdown,
            "findings": findings,
        },
        ["Handlers are local deterministic rules; no external project-management system is modified."],
    )


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


def agent_what_if_simulator(payload):
    baseline = _json(payload, "baseline", dict)
    scenarios = _json(payload, "scenarios", list)
    if not scenarios:
        raise LogicError("supply at least one scenario")
    try:
        revenue = float(baseline.get("revenue", 0))
        growth = float(baseline.get("growth_rate_pct", 0))
        churn = float(baseline.get("churn_rate_pct", 0))
        margin = float(baseline.get("gross_margin_pct", 70))
        months = int(baseline.get("months", 12))
    except (TypeError, ValueError):
        raise LogicError("baseline values must be numeric")
    if revenue <= 0:
        raise LogicError("baseline.revenue must be positive")
    if not 1 <= months <= 36:
        raise LogicError("baseline.months must be between 1 and 36")
    clean = []
    for scenario in scenarios[:8]:
        if not isinstance(scenario, dict):
            raise LogicError("each scenario must be an object")
        name = str(scenario.get("name") or f"Scenario {len(clean) + 1}")
        try:
            clean.append({
                "name": name,
                "growth_delta": float(scenario.get("growth_delta_pct", 0)),
                "churn_delta": float(scenario.get("churn_delta_pct", 0)),
                "margin_delta": float(scenario.get("margin_delta_pct", 0)),
            })
        except (TypeError, ValueError):
            raise LogicError("scenario deltas must be numeric")
    projections = {}
    rows = []
    for month in range(1, months + 1):
        row = [month]
        for scenario in clean:
            effective_growth = (growth + scenario["growth_delta"]) / 100
            effective_churn = (churn + scenario["churn_delta"]) / 100
            value = revenue * ((1 + effective_growth) * (1 - effective_churn)) ** month
            effective_margin = max(0, min(100, margin + scenario["margin_delta"])) / 100
            projections.setdefault(scenario["name"], []).append(round(value, 2))
            row.append(round(value, 2))
        rows.append(row)
    chart = {"labels": [s["name"] for s in clean], "values": [projections[s["name"]][-1] for s in clean]}
    findings = []
    for scenario in clean:
        final = projections[scenario["name"]][-1]
        if final < revenue:
            findings.append({"title": f"{scenario['name']} declines", "severity": "medium", "detail": f"Projected revenue falls from {revenue:,.0f} to {final:,.0f} by month {months}."})
        if (growth + scenario["growth_delta"]) < (churn + scenario["churn_delta"]):
            findings.append({"title": "Churn exceeds growth", "severity": "high", "detail": f"{scenario['name']}: effective churn is higher than effective growth, so the base shrinks."})
    best = max(clean, key=lambda s: projections[s["name"]][-1]) if clean else None
    return _result(
        f"Projected {months} month(s) across {len(clean)} scenario(s); best final revenue: {best['name'] if best else 'none'}.",
        {
            "metrics": {"months": months, "scenarios": len(clean), "baseline_revenue": revenue, "best_final": projections[best["name"]][-1] if best else 0},
            "table": {"columns": ["Month"] + [s["name"] for s in clean], "rows": rows},
            "chart": chart,
            "items": [
                "Formula: revenue × ((1 + growth + scenario delta) × (1 − churn − scenario delta))^month.",
                "Gross margin is reported separately and does not change revenue.",
                "All assumptions are explicit in the supplied baseline and scenarios.",
            ],
            "findings": findings,
        },
        ["Deterministic arithmetic on your assumptions. This is not a forecast or financial advice."],
    )


def agent_cost_tracker(payload):
    usage = _json(payload, "usage", list)
    budget = _num(payload, "budget_usd", default=None, lo=0)
    if not usage:
        raise LogicError("supply at least one usage record")
    rows, by_provider, by_model, total = [], defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0}), defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0}), 0.0
    for index, record in enumerate(usage[:500]):
        if not isinstance(record, dict):
            raise LogicError(f"usage record {index} must be an object")
        model = str(record.get("model") or "unknown")
        provider = str(record.get("provider") or "default")
        tokens_in = float(record.get("tokens_in", 0) or 0)
        tokens_out = float(record.get("tokens_out", 0) or 0)
        calls = float(record.get("calls", 1) or 1)
        rate = float(record.get("rate_per_1k", 0) or 0)
        tokens = tokens_in + tokens_out
        cost = (tokens / 1000) * rate
        total += cost
        rows.append([index + 1, provider, model, int(calls), int(tokens), round(cost, 6)])
        p = by_provider[provider]
        p["calls"] += calls
        p["tokens"] += tokens
        p["cost"] += cost
        m = by_model[model]
        m["calls"] += calls
        m["tokens"] += tokens
        m["cost"] += cost
    findings = []
    if budget is not None:
        remaining = budget - total
        status = "on track" if remaining >= 0 else "over budget"
        findings.append({"title": f"Budget {status}", "severity": "high" if remaining < 0 else "info", "detail": f"Spent {total:.2f} USD of {budget:.2f} USD; {remaining:.2f} USD remaining."})
        if remaining < 0:
            findings.append({"title": "Budget exceeded", "severity": "high", "detail": f"Spending exceeds the configured budget by {abs(remaining):.2f} USD."})
    provider_rows = [[p, d["calls"], d["tokens"], round(d["cost"], 4)] for p, d in sorted(by_provider.items(), key=lambda kv: -kv[1]["cost"])]
    model_rows = [[m, d["calls"], d["tokens"], round(d["cost"], 4)] for m, d in sorted(by_model.items(), key=lambda kv: -kv[1]["cost"])]
    return _result(
        f"Tracked {len(usage)} usage record(s) across {len(by_provider)} provider(s): {total:.2f} USD total.",
        {
            "metrics": {"records": len(usage), "providers": len(by_provider), "models": len(by_model), "total_usd": round(total, 4)},
            "table": {"columns": ["#", "Provider", "Model", "Calls", "Tokens", "Cost (USD)"], "rows": rows},
            "provider_breakdown": provider_rows,
            "model_breakdown": model_rows,
            "findings": findings,
            "items": ["Cache repeated prompts to reduce token volume.", "Route simple tasks to cheaper models.", "Set per-model rate alerts before the next billing cycle."],
        },
        [],
    )


def agent_token_analyzer(payload):
    text = _text(payload, "text", max_len=50000)
    model = str(payload.get("model", "default")).lower()
    calls_per_day = _num(payload, "calls_per_day", default=100, lo=1, hi=100000)
    rate_per_1k = _num(payload, "rate_per_1k_usd", default=0.0, lo=0)
    tokens = len(_tokens(text))
    words = len(text.split())
    avg_tokens_per_word = round(tokens / words, 3) if words else 0
    cost_per_call = (tokens / 1000) * rate_per_1k
    daily_cost = cost_per_call * calls_per_day
    monthly_cost = daily_cost * 30
    suggestions = []
    if avg_tokens_per_word > 1.6:
        suggestions.append("Text is token-dense; consider shorter sentences and removing filler words.")
    if tokens > 4000:
        suggestions.append("Long inputs consume many tokens; summarize or chunk before sending.")
    if rate_per_1k > 0 and monthly_cost > 50:
        suggestions.append("Estimated monthly cost is high; reduce call volume or switch to a lower-cost model.")
    findings = []
    findings.append({"title": f"Estimated tokens: {tokens}", "severity": "info", "detail": f"{words} words at ~{avg_tokens_per_word} tokens per word."})
    if rate_per_1k > 0:
        findings.append({"title": f"Estimated monthly cost: {monthly_cost:.2f} USD", "severity": "high" if monthly_cost > 100 else "info", "detail": f"{calls_per_day} calls/day × {cost_per_call:.6f} USD/call."})
    return _result(
        f"Analyzed {tokens} token(s) in {words} word(s); estimated {monthly_cost:.2f} USD/month at {calls_per_day} calls/day.",
        {
            "metrics": {"tokens": tokens, "words": words, "avg_tokens_per_word": avg_tokens_per_word, "cost_per_call_usd": round(cost_per_call, 6), "daily_cost_usd": round(daily_cost, 4), "monthly_cost_usd": round(monthly_cost, 4), "calls_per_day": int(calls_per_day)},
            "table": {"columns": ["Metric", "Value"], "rows": [["Input tokens", tokens], ["Words", words], ["Avg tokens/word", avg_tokens_per_word], ["Cost per call (USD)", round(cost_per_call, 6)], ["Calls per day", int(calls_per_day)], ["Estimated daily cost (USD)", round(daily_cost, 4)], ["Estimated monthly cost (USD)", round(monthly_cost, 4)]]},
            "chart": {"labels": ["Input tokens", "Est. daily cost", "Est. monthly cost"], "values": [float(tokens), round(daily_cost, 2), round(monthly_cost, 2)]},
            "suggestions": suggestions,
            "findings": findings,
        },
        [],
    )


def agent_prompt_optimizer(payload):
    prompt = _text(payload, "prompt", max_len=10000)
    task_type = str(payload.get("task_type", "general")).lower()
    audience = str(payload.get("audience", "general")).strip()
    original_tokens = len(_tokens(prompt))
    optimized = prompt.strip()
    improvements = []
    if not optimized.endswith((".", "?", "!")):
        optimized = optimized.rstrip() + "."
        improvements.append("Added terminal punctuation for clarity.")
    if "please" not in optimized.lower() and task_type in {"coding", "analysis", "review"}:
        optimized = optimized.rstrip() + " Be specific and show your reasoning."
        improvements.append("Added instruction to be specific and show reasoning.")
    if audience == "beginner" and "example" not in optimized.lower():
        optimized = optimized.rstrip() + " Include a concrete example."
        improvements.append("Added request for a concrete example for beginners.")
    if task_type == "coding" and "```" not in optimized:
        optimized = optimized.rstrip() + " Return code in fenced blocks with the language tag."
        improvements.append("Requested fenced code blocks for coding tasks.")
    if task_type == "summary" and "bullet" not in optimized.lower():
        optimized = optimized.rstrip() + " Present key points as bullets."
        improvements.append("Requested bullet points for summary tasks.")
    optimized_tokens = len(_tokens(optimized))
    savings = max(0, original_tokens - optimized_tokens)
    score = min(100, 60 + len(improvements) * 10 + (10 if len(optimized) > len(prompt) else 0))
    return _result(
        f"Optimized prompt: {len(improvements)} improvement(s), {original_tokens} → {optimized_tokens} token(s).",
        {
            "metrics": {"original_tokens": original_tokens, "optimized_tokens": optimized_tokens, "token_savings": savings, "improvements": len(improvements), "clarity_score": score},
            "patches": [{"before": prompt, "after": optimized, "title": "Optimized prompt"}],
            "findings": [{"title": improvement, "severity": "info", "detail": ""} for improvement in improvements],
            "items": ["Test the optimized prompt on a few real inputs before deploying.", "Keep instructions concise and unambiguous.", "Add one example if the task is format-sensitive."],
        },
        [],
    )


def agent_dependency_update(payload):
    manifest = _text(payload, "manifest", max_len=20000)
    ecosystem = str(payload.get("ecosystem", "requirements")).lower()
    if ecosystem not in {"requirements", "package"}:
        raise LogicError("ecosystem must be 'requirements' or 'package'")
    lines = [line.strip() for line in manifest.splitlines() if line.strip() and not line.startswith("#")]
    packages, findings, rows = [], [], []
    if ecosystem == "requirements":
        for line in lines:
            name = re.split(r"[=<>!~\[\];\s]", line, 1)[0].strip()
            if not name:
                continue
            pinned = "==" in line or "===" in line
            version = ""
            m = re.search(r"(?:==|===)\s*([0-9A-Za-z.\*]+)", line)
            if m:
                version = m.group(1)
            packages.append({"name": name, "pinned": pinned, "version": version})
            rows.append([name, "pinned" if pinned else "unpinned", version or "—"])
            if not pinned:
                findings.append({"title": f"Unpinned dependency: {name}", "severity": "medium", "detail": "Pin exact versions to avoid surprise upgrades."})
    else:
        for line in lines:
            if line.startswith("{") or line.startswith("["):
                continue
            parts = line.split()
            name = parts[0].strip('"').strip("'") if parts else ""
            version = parts[1].strip('"').strip("'") if len(parts) > 1 else ""
            if not name:
                continue
            pinned = not version.startswith(("^", "~", ">= ", "> ", "< "))
            packages.append({"name": name, "pinned": pinned, "version": version or "latest"})
            rows.append([name, "pinned" if pinned else "unpinned", version or "latest"])
            if not pinned:
                findings.append({"title": f"Semver range: {name}@{version or 'latest'}", "severity": "low", "detail": "Ranges can pull breaking changes; consider pinning in production."})
    risky = [p["name"] for p in packages if not p["pinned"]]
    score = max(0, 100 - len(risky) * 10)
    return _result(
        f"Reviewed {len(packages)} package(s): {len(risky)} unpinned or ranged.",
        {
            "metrics": {"packages": len(packages), "unpinned": len(risky), "pinned": len(packages) - len(risky), "score": score},
            "table": {"columns": ["Package", "Pin status", "Version"], "rows": rows[:100]},
            "findings": findings,
            "items": ["Run 'pip list --outdated' or 'npm outdated' for current versions.", "Test updates in a staging environment before production.", "Enable Dependabot or Renovate for automated PRs."],
        },
        [],
    )


def agent_config_validator(payload):
    content = _text(payload, "config", max_len=20000)
    fmt = str(payload.get("format", "json")).lower()
    required_raw = str(payload.get("required_fields", "")).strip()
    required = [f.strip() for f in required_raw.split(",") if f.strip()] if required_raw else []
    errors, warnings, rows = [], [], []
    parsed = None
    try:
        if fmt == "yaml":
            try:
                import yaml
                parsed = yaml.safe_load(content)
            except ImportError:
                errors.append("PyYAML is not installed; YAML validation is limited to structural checks.")
                parsed = None
        else:
            parsed = json.loads(content)
    except Exception as exc:
        errors.append(f"Parse error: {exc}")
    if isinstance(parsed, dict):
        for field in required:
            if field not in parsed:
                errors.append(f"Missing required field: {field}")
                rows.append([field, "missing", "—"])
            else:
                rows.append([field, "present", str(parsed[field])[:60]])
        for key, value in parsed.items():
            key_lower = str(key).lower()
            value_str = str(value).lower()
            if any(token in key_lower or token in value_str for token in ["password", "secret", "api_key", "token"]):
                warnings.append(f"Possible secret in field '{key}'")
                rows.append([key, "possible secret", "—"])
        if not errors and not warnings:
            findings = [{"title": "Config valid", "severity": "info", "detail": "All required fields present and no obvious secrets detected."}]
        else:
            findings = [{"title": f"{len(errors)} error(s), {len(warnings)} warning(s)", "severity": "high" if errors else "medium", "detail": "Review and fix before deploying."}]
    else:
        errors.append("Top-level value must be an object/map.")
        findings = [{"title": "Invalid config structure", "severity": "high", "detail": "Expected a JSON object or YAML mapping at the top level."}]
    return _result(
        f"Validated {fmt} config: {len(errors)} error(s), {len(warnings)} warning(s).",
        {
            "metrics": {"errors": len(errors), "warnings": len(warnings), "fields_checked": len(required)},
            "table": {"columns": ["Field", "Status", "Value"], "rows": rows[:100]},
            "findings": findings,
            "items": ["Never commit real secrets; use environment variables.", "Validate config at application startup, not only in CI.", "Keep required-field lists in sync with deployment docs."],
        },
        errors,
    )


def agent_secret_scanner(payload):
    code = _text(payload, "code", max_len=50000)
    file_hint = str(payload.get("file", "unknown")).strip()
    patterns = [
        (r"sk-[A-Za-z0-9]{20,}", "OpenAI API key", "high"),
        (r"ghp_[A-Za-z0-9]{20,}", "GitHub personal access token", "high"),
        (r"github_pat_[A-Za-z0-9_]{20,}", "GitHub fine-grained token", "high"),
        (r"AKIA[0-9A-Z]{16}", "AWS access key ID", "high"),
        (r"[0-9a-zA-Z/+]{40}", "AWS secret access key (heuristic)", "medium"),
        (r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"]?[A-Za-z0-9_-]{16,}", "Generic API key assignment", "medium"),
        (r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?[^\s'\"]{6,}", "Possible hardcoded password", "medium"),
        (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "Private key block", "high"),
        (r"(?i)(mongodb|postgres|mysql|redis)://[^:\s]+:[^@\s]+@", "Database connection string with credentials", "medium"),
    ]
    findings, rows = [], []
    for pattern, label, severity in patterns:
        for match in re.finditer(pattern, code):
            start = max(0, match.start() - 40)
            end = min(len(code), match.end() + 40)
            context = code[start:end].replace("\n", "\\n")
            findings.append({"title": label, "severity": severity, "detail": f"{file_hint}: ...{context}..."})
            rows.append([label, severity, context[:80]])
    score = max(0, 100 - len(findings) * 15)
    return _result(
        f"Scanned {len(code.splitlines())} line(s): {len(findings)} potential secret(s) found.",
        {
            "metrics": {"findings": len(findings), "score": score, "lines": len(code.splitlines())},
            "table": {"columns": ["Finding", "Severity", "Context"], "rows": rows[:50]},
            "items": ["Move secrets to environment variables or a secrets manager.", "Add this scanner to pre-commit hooks.", "Rotate any credential that may have been committed."],
        },
        [],
    )


def agent_performance_profiler(payload):
    code = _text(payload, "code", max_len=20000)
    timing = payload.get("timing")
    if isinstance(timing, str) and timing.strip():
        timing = _json(payload, "timing", list)
    findings, rows, hot_spots = [], [], []
    loops = len(re.findall(r"\bfor\b|\bwhile\b", code))
    nested_loops = len(re.findall(r"\bfor\b.*\n.*\bfor\b|\bwhile\b.*\n.*\bwhile\b", code, re.DOTALL))
    regex_calls = len(re.findall(r"\bre\.(match|search|sub|findall|split)\b", code))
    json_parses = len(re.findall(r"\bjson\.(loads|load)\b", code))
    db_queries = len(re.findall(r"\b(execute|executemany|query|find|aggregate)\b", code, re.IGNORECASE))
    if loops:
        hot_spots.append(("Loop detected", loops, "Review loop body for repeated expensive work."))
    if nested_loops:
        hot_spots.append(("Nested loop detected", nested_loops, "O(n²) risk; consider indexing or hashing."))
    if regex_calls > 5:
        hot_spots.append(("Frequent regex calls", regex_calls, "Compile patterns once and reuse them."))
    if json_parses > 3:
        hot_spots.append(("Repeated JSON parsing", json_parses, "Parse once and reuse the object."))
    if db_queries > 3:
        hot_spots.append(("Multiple database queries", db_queries, "Batch queries or use joins where possible."))
    rows = [[title, count, detail] for title, count, detail in hot_spots]
    score = max(0, 100 - len(hot_spots) * 12)
    timing_notes = []
    if isinstance(timing, list):
        for entry in timing[:20]:
            if isinstance(entry, dict):
                name = str(entry.get("function") or entry.get("name") or "unknown")
                ms = float(entry.get("ms", 0) or 0)
                timing_notes.append([name, round(ms, 2)])
                if ms > 100:
                    findings.append({"title": f"Slow function: {name}", "severity": "medium", "detail": f"{ms:.1f} ms per call."})
    return _result(
        f"Profiled {len(code.splitlines())} line(s): {len(hot_spots)} hot spot(s), {score}/100 score.",
        {
            "metrics": {"score": score, "hot_spots": len(hot_spots), "loops": loops, "nested_loops": nested_loops, "regex_calls": regex_calls, "json_parses": json_parses, "db_queries": db_queries},
            "table": {"columns": ["Hot spot", "Count", "Recommendation"], "rows": rows[:50]},
            "timing": timing_notes,
            "findings": findings,
            "items": ["Profile with real workloads, not just static patterns.", "Cache results of pure functions called repeatedly.", "Benchmark before and after any optimization."],
        },
        [],
    )


def agent_compliance_checker(payload):
    policy = _text(payload, "policy", max_len=20000)
    system = str(payload.get("system_description", "")).strip()
    regulation = str(payload.get("regulation", "GDPR")).upper()
    if regulation not in {"GDPR", "SOC2", "HIPAA", "PCI-DSS", "ISO27001"}:
        raise LogicError("regulation must be GDPR, SOC2, HIPAA, PCI-DSS, or ISO27001")
    checks = {
        "GDPR": ["data minimization", "consent", "right to erasure", "breach notification", "data protection officer", "privacy by design"],
        "SOC2": ["access control", "change management", "monitoring", "incident response", "encryption", "vendor management"],
        "HIPAA": ["access controls", "audit controls", "integrity", "transmission security", "workforce training", "business associate agreements"],
        "PCI-DSS": ["firewall configuration", "default passwords", "stored cardholder data", "transmission encryption", "vulnerability program", "access restriction"],
        "ISO27001": ["information security policy", "asset management", "access control", "cryptography", "incident management", "business continuity"],
    }[regulation]
    rows, findings, covered, missing = [], [], 0, []
    combined = (policy + " " + system).lower()
    for control in checks:
        present = any(term in combined for term in control.split())
        status = "covered" if present else "missing"
        if present:
            covered += 1
        else:
            missing.append(control)
            findings.append({"title": f"Missing control: {control}", "severity": "medium", "detail": f"No evidence for {control} in the supplied policy or system description."})
        rows.append([control, status, "Evidence found" if present else "No evidence found"])
    score = round(100 * covered / len(checks))
    return _result(
        f"{regulation} compliance: {covered}/{len(checks)} controls covered ({score}%).",
        {
            "metrics": {"regulation": regulation, "controls": len(checks), "covered": covered, "missing": len(missing), "score": score},
            "table": {"columns": ["Control", "Status", "Evidence"], "rows": rows},
            "findings": findings,
            "items": ["Map each control to a specific policy document or system feature.", "Assign an owner for every missing control.", "Re-check after any system or policy change."],
        },
        [],
    )


def agent_deployment_readiness(payload):
    config = _text(payload, "config", max_len=10000)
    environment = str(payload.get("environment", "production")).strip()
    has_rollback = bool(payload.get("has_rollback", False))
    checks = [
        ("version_pinned", "Application version is pinned", "version" in config.lower() or "tag" in config.lower()),
        ("health_check", "Health check endpoint defined", "health" in config.lower() or "readiness" in config.lower()),
        ("rollback_plan", "Rollback plan documented", has_rollback or "rollback" in config.lower()),
        ("resource_limits", "CPU/memory limits set", "cpu" in config.lower() or "memory" in config.lower() or "limit" in config.lower()),
        ("secret_injection", "Secrets use environment variables", "env" in config.lower() or "secret" in config.lower()),
        ("monitoring", "Monitoring or alerting configured", "monitor" in config.lower() or "alert" in config.lower() or "metric" in config.lower()),
    ]
    rows, findings, passed = [], [], 0
    for key, title, ok in checks:
        status = "pass" if ok else "fail"
        if ok:
            passed += 1
        else:
            findings.append({"title": f"Missing: {title}", "severity": "high", "detail": f"{title} is not evident in the deployment config."})
        rows.append([title, status, "Present" if ok else "Not found"])
    score = round(100 * passed / len(checks))
    ready = score >= 80
    return _result(
        f"Deployment readiness for {environment}: {score}% ({'ready' if ready else 'not ready'}).",
        {
            "metrics": {"environment": environment, "score": score, "checks_passed": passed, "checks_total": len(checks), "ready": ready},
            "table": {"columns": ["Check", "Status", "Detail"], "rows": rows},
            "findings": findings,
            "items": ["Pin container images to exact digests or versions.", "Test rollback in staging before production.", "Add health checks and alerts before traffic shifts."],
        },
        [],
    )


def agent_incident_responder(payload):
    description = _text(payload, "description", max_len=10000)
    affected = str(payload.get("affected_services", "")).strip()
    user_reported = bool(payload.get("user_reported", False))
    lowered = description.lower()
    severity = "low"
    if any(w in lowered for w in ["outage", "down", "unavailable", "critical", "sev1"]):
        severity = "critical"
    elif any(w in lowered for w in ["slow", "degraded", "error", "sev2", "partial"]):
        severity = "high"
    elif any(w in lowered for w in ["warning", "minor", "sev3"]):
        severity = "medium"
    actions = []
    if severity == "critical":
        actions = ["Page on-call engineer immediately.", "Open incident bridge.", "Post public status page update within 15 minutes.", "Roll back recent deployments if correlated."]
    elif severity == "high":
        actions = ["Assign incident lead within 30 minutes.", "Gather logs from affected services.", "Prepare rollback plan.", "Notify stakeholders within 1 hour."]
    elif severity == "medium":
        actions = ["Create incident ticket.", "Investigate during business hours.", "Monitor for recurrence."]
    else:
        actions = ["Log as a minor event.", "Review at next team meeting."]
    if user_reported:
        actions.insert(0, "Acknowledge user report and set expectations.")
    timeline = []
    if severity in {"critical", "high"}:
        timeline = [("T+0 min", "Incident detected and severity assigned"), ("T+15 min", "Initial response and stakeholder notification"), ("T+60 min", "Mitigation or rollback decision"), ("T+24 h", "Post-incident review published")]
    else:
        timeline = [("T+0 min", "Ticket created and triaged"), ("T+24 h", "Investigation started"), ("T+3 d", "Resolution or planned work item")]
    rows = [[t, d] for t, d in timeline]
    affected_list = [s.strip() for s in affected.split(",") if s.strip()] if affected else ["not specified"]
    return _result(
        f"Incident triaged as {severity.upper()}: {len(actions)} immediate action(s), {len(affected_list)} affected service(s).",
        {
            "metrics": {"severity": severity, "actions": len(actions), "affected_services": len(affected_list), "user_reported": user_reported},
            "table": {"columns": ["Time", "Action"], "rows": rows},
            "items": actions,
            "findings": [{"title": f"Severity: {severity.upper()}", "severity": severity, "detail": f"Affected: {', '.join(affected_list)}"}],
        },
        [],
    )
