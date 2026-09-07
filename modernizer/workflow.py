"""Durable agent handoffs; agents provide work, executable evidence supplies gates."""
from .discovery import hash_file
from .engine import check, identifier, shape, text

CONTRACT_KINDS = {"disposition", "type_mapping", "plan"}
OTHER_KINDS = {"stage", "review"}


def validate_record(engine, kind, record):
    if kind == "disposition":
        shape(record, ["id", "source_ref", "source_sha256", "disposition", "feature_ids", "reason", "reviewed_by"])
        shape(record["source_ref"], ["root", "path"])
        p = engine.resolve_ref(record["source_ref"], "source")
        check(record["source_sha256"] == hash_file(p), "Disposition must reference current source hash")
        check(record["disposition"] in {"feature", "support", "generated", "out_of_scope"}, "Invalid disposition")
        check(isinstance(record["feature_ids"], list), "feature_ids must be an array")
        check(record["disposition"] != "feature" or record["feature_ids"], "Feature disposition needs feature IDs")
        for id in record["feature_ids"]: engine.get("feature", id)
        text(record["reason"], "reason")
        text(record["reviewed_by"], "reviewed_by")
        for d in engine.records("disposition"):
            check(d["id"] == record["id"] or d["source_ref"] != record["source_ref"], "Each source file has one disposition record")
    elif kind == "type_mapping":
        shape(record, ["id", "feature_ids", "source_type", "target_type", "semantics", "scenario_ids", "source_refs"])
        for key in ["source_type", "target_type", "semantics"]: text(record[key], key)
        for key in ["feature_ids", "scenario_ids", "source_refs"]:
            check(isinstance(record[key], list) and record[key], f"{key} must be nonempty")
        for id in record["feature_ids"]: engine.get("feature", id)
        for id in record["scenario_ids"]: identifier(id)
        for ref in record["source_refs"]: engine.resolve_ref(ref, "source")
    elif kind == "plan":
        shape(record, ["id", "feature_id", "architecture", "type_mapping_ids", "required_commands", "implementation_roles", "confirmed_by"])
        engine.get("feature", record["feature_id"])
        text(record["architecture"], "architecture")
        text(record["confirmed_by"], "confirmed_by (user or cited policy/evidence)")
        for key in ["type_mapping_ids", "required_commands", "implementation_roles"]:
            check(isinstance(record[key], list) and record[key], f"{key} must be nonempty")
        check(set(record["implementation_roles"]) <= {"backend", "ui"}, "Implementation roles are backend/ui")
        for id in record["type_mapping_ids"]:
            mapping = engine.get("type_mapping", id)
            check(record["feature_id"] in mapping["feature_ids"], "Type mapping belongs to another feature")
        for id in record["required_commands"]:
            command = engine.config.get("commands", {}).get(id)
            check(command is not None and command["purpose"] in {"build", "test"}, "Plan commands must be configured build/test commands")
        for p in engine.records("plan"):
            check(p["id"] == record["id"] or p["feature_id"] != record["feature_id"], "One plan per feature")
    elif kind == "stage":
        shape(record, ["id", "feature_id", "role", "summary", "output_refs"], ["source_fingerprint", "output_hashes"])
        f = engine.get("feature", record["feature_id"])
        check(record["role"] in {"backend", "ui"}, "Stage role must be backend/ui")
        text(record["summary"], "summary")
        check(isinstance(record["output_refs"], list) and record["output_refs"], "Stage needs existing output refs")
        allowed = {(r["root"], r["path"]) for r in f["target_refs"]}
        hashes = {}
        for ref in record["output_refs"]:
            check((ref["root"], ref["path"]) in allowed, "Stage output must be a declared feature target")
            hashes[ref["root"] + ":" + ref["path"]] = hash_file(engine.resolve_ref(ref, "target"))
        record = {**record, "source_fingerprint": engine.snapshot(source_only=True)[0], "output_hashes": hashes}
    elif kind == "review":
        shape(record, ["id", "feature_id", "reviewer", "summary", "issues", "evidence_refs"], ["fingerprint"])
        engine.get("feature", record["feature_id"])
        text(record["reviewer"], "reviewer")
        text(record["summary"], "summary")
        check(isinstance(record["issues"], list) and all(isinstance(i, str) and i for i in record["issues"]), "issues must contain text; empty means no issues found in this review")
        check(isinstance(record["evidence_refs"], list) and record["evidence_refs"], "Review needs source/target evidence")
        for ref in record["evidence_refs"]: engine.resolve_ref(ref)
        record = {**record, "fingerprint": engine.snapshot()[0]}
    return record


def stage_current(engine, feature_id, role, source_fp):
    entries = [s for s in engine.records("stage") if s["feature_id"] == feature_id and s["role"] == role]
    for stage in entries:
        if stage["source_fingerprint"] != source_fp: continue
        try:
            hashes = {r["root"] + ":" + r["path"]: hash_file(engine.resolve_ref(r, "target")) for r in stage["output_refs"]}
            if hashes == stage["output_hashes"]: return True
        except (OSError, ValueError): pass
    return False


def next_action(engine):
    report = engine.report()
    def action(role, operation, reason, **extra):
        return {"agent": "migration-" + role, "operation": operation, "reason": reason, **extra,
                "execution": "The selected Copilot/Claude coordinator invokes native subagents; the Python engine does not call a model itself."}
    row = engine.db.execute("SELECT value FROM meta WHERE key='application_map'").fetchone()
    if row is None:
        return action("discovery", "map", "Build the evidence-located source graph first")
    if not engine.records("feature"):
        return action("discovery", "register_features", "Review source graph and runtime entry points; register features without inventing behavior")
    questions = [q for q in engine.records("question") if q["blocking"] and q["answer"] is None]
    global_questions = [q for q in questions if not q["feature_ids"]]
    if global_questions:
        return action("coordinator", "ask_user", "Required global evidence is missing", question_ids=[q["id"] for q in global_questions])
    coverage = report["reconciliation"]
    if coverage["accounted"] < coverage["total"] or coverage["orphaned_dispositions"]:
        return action("discovery", "reconcile", "Every current source file needs an evidenced, reviewed disposition", accounted=coverage["accounted"], total=coverage["total"])
    fp = engine.snapshot(source_only=True)[0]
    ordered, seen = [], set()
    for feature in engine.records("feature"):
        try:
            for item in engine.closure(feature["id"]):
                if item["id"] not in seen: ordered.append(item); seen.add(item["id"])
        except ValueError:
            return action("planning", "resolve_dependencies", "A declared feature dependency has no definition", feature_id=feature["id"])
    blocked_ids = set()
    for f in ordered:
        id = f["id"]
        blockers = engine.blockers([x["id"] for x in engine.closure(id)])
        if blockers:
            blocked_ids.update(q["id"] for q in blockers)
            continue
        plan = next((p for p in engine.records("plan") if p["feature_id"] == id), None)
        if plan is None:
            return action("planning", "plan", "Record evidenced architecture choices, type mappings, build/test commands and implementation roles", feature_id=id)
        row = next(r for r in report["features"] if r["id"] == id)
        if any(s == "missing_definition" for s in row["scenarios"].values()):
            return action("verification", "characterize_legacy", "Required scenarios need definitions and legacy observations", feature_id=id)
        for role in plan["implementation_roles"]:
            if not stage_current(engine, id, role, fp):
                return action(role, "implement_stage", "Load a bounded packet; preserve contracts and defects; record target stage evidence", feature_id=id)
        if not row["implementation_current"]:
            return action("coordinator", "implemented", "Use a current lease to checkpoint the mapped target files", feature_id=id)
        if any(s != "passed" for s in row["commands"].values()):
            return action("verification", "run_commands", "Run or repair required builds/tests using configured commands", feature_id=id, commands=row["commands"])
        if not row["verified_for_declared_scope"]:
            return action("verification", "run_scenarios", "Run all required dimensions; investigate mismatches and unobserved behavior", feature_id=id, dimensions=row["dimension_states"])
        if not row["review_current"]:
            return action("review", "review", "Inspect omission risks and current evidence; register review findings", feature_id=id)
    if blocked_ids:
        return action("coordinator", "ask_user", "Remaining features need evidence; independent eligible work has been considered", question_ids=sorted(blocked_ids))
    if not report["application_map"]["current"]:
        return action("discovery", "map", "Refresh the map for the current contracts and source inventory")
    if not report["ready_for_acceptance"]:
        return action("coordinator", "resolve_remaining_gaps", "Feature checks pass but unresolved inventory gaps, evidence inputs or questions still block acceptance", ready_for_acceptance=False)
    return action("coordinator", "present_acceptance_evidence", "All declared feature gates pass; request review of runtime coverage and preserved defects. This is not proof of every possible behavior.", ready_for_acceptance=True)
