"""Evidence-located source graph. Lexical candidates are never semantic proof."""
from __future__ import annotations

import json
import re
from bisect import bisect_right
import xml.etree.ElementTree as ET
from pathlib import Path

from .discovery import digest, inventory

TOKEN = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|@"(?:""|[^"])*"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_]\w*|=>|[^\s]', re.MULTILINE)
TYPE_WORDS = {"class", "interface", "record", "struct", "enum"}
CONTROL = {"if", "for", "foreach", "while", "switch", "catch", "using", "lock", "nameof", "typeof", "sizeof", "return", "new"}
DATA_TYPES = {"decimal", "double", "float", "int", "long", "uint", "ulong", "short", "byte", "bool", "string", "DateTime", "DateTimeOffset", "Guid", "BigInteger"}


def uid(*parts):
    return "N" + digest("\0".join(map(str, parts)).encode())[:20]


def tokens(source):
    result = []
    newlines = [m.start() for m in re.finditer("\n", source)]
    for match in TOKEN.finditer(source):
        value = match.group()
        if value.startswith(("//", "/*")):
            continue
        result.append({"value": value, "line": bisect_right(newlines, match.start()) + 1,
                       "start": match.start(), "end": match.end()})
    return result


def paired(items, opening, closing):
    stack, pairs = [], {}
    for i, item in enumerate(items):
        if item["value"] == opening:
            stack.append(i)
        elif item["value"] == closing and stack:
            pairs[stack.pop()] = i
    return pairs


def build_map(engine):
    before, _ = engine.snapshot(source_only=True)
    inv = inventory(engine.config, engine.base)
    nodes, edges, gaps = [], [], list(inv["gaps"])
    symbols, calls = {}, []
    files = {}
    def node(kind, label, ref, **extra):
        id = uid(kind, ref["root"], ref["path"], label, ref.get("start", 1))
        nodes.append({"id": id, "kind": kind, "label": label, "ref": ref,
                      "evidence": "source_location", **extra})
        return id
    def edge(source, target, relation, confidence="explicit", **extra):
        edges.append({"source": source, "target": target, "relation": relation,
                      "confidence": confidence, **extra})
    for file in inv["files"]:
        ref = {"root": file["root"], "path": file["path"]}
        kind = "source_file" if file["role"] == "source" else "target_file"
        fid = node(kind, file["path"], ref, sha256=file["sha256"])
        files[(file["root"], file["path"])] = fid
        if file["role"] != "source" or not file["text_eligible"]:
            continue
        path = engine.resolve_ref(ref, "source")
        try:
            source = path.read_text(encoding="utf-8-sig")
        except (UnicodeError, OSError):
            gaps.append({**ref, "reason": "unreadable_source_text"})
            continue
        suffix = path.suffix.lower()
        if suffix == ".csproj":
            try:
                tree = ET.fromstring(source)
                for item in tree.iter():
                    name = item.tag.rsplit("}", 1)[-1]
                    if name in {"ProjectReference", "PackageReference"} and item.get("Include"):
                        dep = node("project_dependency", item.get("Include"), ref,
                                   version=item.get("Version"), dependency_kind=name)
                        edge(fid, dep, "references")
            except ET.ParseError:
                gaps.append({**ref, "reason": "invalid_project_xml"})
        if suffix in {".cshtml", ".razor", ".aspx", ".ascx", ".html"}:
            view = node("ui", file["path"], ref)
            edge(fid, view, "declares")
            for m in re.finditer(r'(?:asp-action|asp-controller|action|href)\s*=\s*["\']([^"\']+)["\']', source):
                r = {**ref, "start": source.count("\n", 0, m.start()) + 1}
                dest = node("ui_navigation_candidate", m.group(1), r)
                edge(view, dest, "navigates_to_candidate", "lexical_candidate")
        if suffix == ".sql":
            for m in re.finditer(r'\b(?:CREATE\s+(?:TABLE|VIEW|PROCEDURE|TRIGGER)|FROM|JOIN|UPDATE|INTO)\s+([\w.\[\]"]+)', source, re.I):
                n = node("database_object_candidate", m.group(1), {**ref, "start": source.count("\n", 0, m.start()) + 1})
                edge(fid, n, "sql_reference_candidate", "lexical_candidate")
        if suffix != ".cs":
            continue
        t = tokens(source)
        braces, parens = paired(t, "{", "}"), paired(t, "(", ")")
        declarations = []
        def location(i, end=None):
            return {**ref, "start": t[i]["line"], "end": t[end if end is not None else i]["line"]}
        for i, tok in enumerate(t[:-1]):
            if tok["value"] in TYPE_WORDS and re.fullmatch(r'[A-Za-z_]\w*', t[i+1]["value"]):
                brace = next((j for j in range(i+2, min(i+100, len(t))) if t[j]["value"] in {"{", ";"}), None)
                end = braces.get(brace, i+1)
                n = node("type", t[i+1]["value"], location(i, end), declaration=tok["value"])
                declarations.append((i, end, n, t[i+1]["value"]))
                edge(fid, n, "declares")
                symbols.setdefault(t[i+1]["value"], []).append(n)
        methods = []
        for i, close in parens.items():
            if i < 2 or close+1 >= len(t):
                continue
            name, previous, after = t[i-1]["value"], t[i-2]["value"], t[close+1]["value"]
            owner = next((d for d in reversed(declarations) if d[0] < i < d[1]), None)
            if not owner or name in CONTROL or previous in {".", "new", "return", "="} or not re.fullmatch(r'[A-Za-z_]\w*', name):
                continue
            if after not in {"{", "=>"} or previous in {";", "{", "}", ")"}:
                continue
            end = braces.get(close+1, next((j for j in range(close+1, len(t)) if t[j]["value"] == ";"), close))
            label = owner[3] + "." + name
            n = node("method_candidate", label, location(i-1, end), confidence="lexical_candidate")
            edge(owner[2], n, "declares_candidate", "lexical_candidate")
            methods.append((i, end, n))
            symbols.setdefault(name, []).append(n)
        for i, tok in enumerate(t):
            value = tok["value"]
            owner = next((m[2] for m in reversed(methods) if m[0] <= i <= m[1]), fid)
            if value in DATA_TYPES:
                n = node("type_use", value, location(i), nullable=i+1 < len(t) and t[i+1]["value"] == "?")
                edge(owner, n, "uses_type")
            if value in {"throw", "catch", "DbSet", "DbContext", "SqlCommand", "FromSqlRaw", "ExecuteSqlRaw", "SaveChanges", "SaveChangesAsync"}:
                n = node("exception_path" if value in {"throw", "catch"} else "data_access", value, location(i))
                edge(owner, n, "contains")
            if value in {"HttpGet", "HttpPost", "HttpPut", "HttpDelete", "Route", "MapGet", "MapPost", "MapPut", "MapDelete"}:
                literal = next((x["value"] for x in t[i+1:i+5] if x["value"].startswith('"')), None)
                n = node("route_candidate", value + (" " + literal if literal else ""), location(i), confidence="lexical_candidate")
                edge(fid, n, "exposes_candidate", "lexical_candidate")
            if value == "(" and i > 0:
                name = t[i-1]["value"]
                if name not in CONTROL and re.fullmatch(r'[A-Za-z_]\w*', name) and not any(m[0] == i for m in methods):
                    calls.append((owner, name, location(i-1)))
        flags = []
        if '"""' in source: flags.append("raw_strings_need_semantic_adapter")
        if any(x["value"] in {"dynamic", "Reflection"} for x in t): flags.append("dynamic_binding")
        if re.search(r'^\s*#\s*(if|elif|else)', source, re.M): flags.append("conditional_compilation")
        gaps.extend({**ref, "reason": reason} for reason in flags)
    for owner, name, ref in calls:
        choices = symbols.get(name, [])
        if len(choices) == 1:
            edge(owner, choices[0], "calls_candidate", "name_match_only", ref=ref)
        else:
            n = node("unresolved_call", name, ref, candidate_count=len(choices))
            edge(owner, n, "invokes_unresolved", "unresolved")
    for feature in engine.records("feature"):
        n = uid("feature", feature["id"])
        nodes.append({"id": n, "kind": "feature", "label": feature["id"] + ": " + feature["title"], "evidence": "registered_contract"})
        for key, rel in [("source_refs", "implemented_in_legacy"), ("target_refs", "mapped_to_target")]:
            for ref in feature[key]:
                dest = files.get((ref["root"], ref["path"]))
                if dest:
                    edge(n, dest, rel, "registered")
        for dep in feature["depends_on"]:
            edge(n, uid("feature", dep), "depends_on", "registered")
    semantic_row = engine.db.execute("SELECT value FROM meta WHERE key='semantic_map'").fetchone()
    if semantic_row:
        semantic = json.loads(semantic_row[0])
        if semantic["fingerprint"] == engine.snapshot()[0]:
            nodes.extend(semantic["nodes"])
            edges.extend(semantic["edges"])
            gaps.extend({"reason": "semantic_diagnostic", "detail": d} for d in semantic.get("diagnostics", []))
    after, _ = engine.snapshot(source_only=True)
    graph = {"schema_version": 1, "source_fingerprint": before, "current": before == after,
             "nodes": list({n["id"]: n for n in nodes}.values()),
             "edges": list({json.dumps(e, sort_keys=True): e for e in edges}.values()),
             "gaps": gaps, "exclusions": inv["exclusions"],
             "semantic_complete": False,
             "limits": ["Syntax/name candidates are not a resolved call graph.",
                        "Overloads, inheritance, generated code, project variants and runtime dependencies require semantic/runtime evidence.",
                        "Registered feature mappings still require human/agent review."]}
    return graph


def reconcile(engine):
    """File-level source coverage; statements about a file are reviewed, not inferred."""
    inv = inventory(engine.config, engine.base)
    dispositions = engine.records("disposition")
    features = {f["id"]: f for f in engine.records("feature")}
    rows = []
    for file in inv["files"]:
        if file["role"] != "source":
            continue
        ref = {"root": file["root"], "path": file["path"]}
        linked = [id for id, f in features.items() if any(r["root"] == ref["root"] and r["path"] == ref["path"] for r in f["source_refs"])]
        d = next((d for d in dispositions if d["source_ref"] == ref), None)
        state = "unreviewed"
        if d:
            state = "stale" if d["source_sha256"] != file["sha256"] else "accounted"
            if d["disposition"] == "feature" and not set(d["feature_ids"]) <= set(linked):
                state = "invalid_feature_mapping"
        rows.append({"ref": ref, "sha256": file["sha256"], "state": state, "mapped_features": linked,
                     "disposition_id": d["id"] if d else None})
    deleted = [d["id"] for d in dispositions if not any(d["source_ref"] == r["ref"] for r in rows)]
    return {"files": rows, "total": len(rows), "accounted": sum(r["state"] == "accounted" for r in rows),
            "orphaned_dispositions": deleted, "gaps": inv["gaps"], "exclusions": inv["exclusions"],
            "meaning": "Reviewed file disposition coverage, not proof that all application behaviors were found."}


def mermaid(graph, max_nodes=80):
    selected = graph["nodes"][:max_nodes]
    ids = {n["id"] for n in selected}
    lines = ["# Application map", "", "Lexical candidates require review; this is not a complete semantic call graph.", "", "```mermaid", "flowchart TD"]
    for n in selected:
        label = (n["kind"] + ": " + n["label"]).replace('"', "'").replace("\n", " ").replace("<", "").replace(">", "").replace("`", "")
        lines.append(f'  {n["id"]}["{label[:140]}"]')
    for e in graph["edges"]:
        if e["source"] in ids and e["target"] in ids:
            lines.append(f'  {e["source"]} -->|{e["relation"]}| {e["target"]}')
    lines += ["```", "", f"Showing {len(selected)} of {len(graph['nodes'])} nodes. Full data is available from map --format json."]
    return "\n".join(lines) + "\n"
