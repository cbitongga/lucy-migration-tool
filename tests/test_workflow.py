import json
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from modernizer.engine import Engine, MigrationError
from modernizer.observations import decode_observation
from modernizer.runner import create_job, execute_job, process_capture
from tests.support import feature, project

ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="workflow space ")
        self.base = Path(self.temp.name)
        self.manifest = project(self.base)
        for name in ["legacy.sqlite", "target.sqlite"]:
            with sqlite3.connect(self.base / name) as db:
                db.execute("CREATE TABLE invoice(id INTEGER PRIMARY KEY, amount TEXT, note TEXT)")
                db.execute("INSERT INTO invoice VALUES(1,'9007199254740993.10',NULL)")
        config = json.loads(self.manifest.read_text())
        config["exclude_dirs"].append("build")
        config["commands"] = {
            "build-target": {"argv": ["{python}", "-c", "import pathlib; p=pathlib.Path('build'); p.mkdir(exist_ok=True); (p/'artifact').write_text('compiled fixture')"], "cwd_root": "target", "purpose": "build", "timeout_seconds": 5, "expected_artifacts": [{"root":"target","path":"build"}]},
            "legacy-capture": {"argv": ["{python}", "{tool}/adapters/sqlite_capture.py", "--database", "{control}/legacy.sqlite"], "cwd_root": "legacy", "purpose": "capture", "timeout_seconds": 5},
            "target-capture": {"argv": ["{python}", "{tool}/adapters/sqlite_capture.py", "--database", "{control}/target.sqlite"], "cwd_root": "target", "purpose": "capture", "timeout_seconds": 5}
        }
        config["evidence_inputs"] = ["legacy.sqlite", "target.sqlite"]
        self.manifest.write_text(json.dumps(config))
        self.engine = Engine(self.manifest)

    def tearDown(self):
        self.engine.close()
        self.temp.cleanup()

    def catalog(self):
        e = self.engine
        f = feature()
        f["required_dimensions"] = ["database"]
        f["required_scenarios"] = ["DB1"]
        e.put("feature", f)
        raw = subprocess.check_output([sys.executable, str(ROOT / "adapters/sqlite_capture.py"), "--database", str(self.base / "legacy.sqlite")])
        _, sha = decode_observation(raw, "database")
        e.put("scenario", {"id": "DB1", "feature_id": "F1", "adapter": "observation", "dimension": "database",
                          "legacy_command": "legacy-capture", "target_command": "target-capture", "legacy_observation_sha256": sha})
        e.put("type_mapping", {"id": "TM1", "feature_ids": ["F1"], "source_type": "decimal",
                "target_type": "BigDecimal serialized as text", "semantics": "Preserve value and scale, including browser boundary; synthetic fixture scope.",
                "scenario_ids": ["DB1"], "source_refs": f["source_refs"]})
        e.put("plan", {"id": "P1", "feature_id": "F1", "architecture": "Test-only fixture architecture, not an application proposal",
                "type_mapping_ids": ["TM1"], "required_commands": ["build-target"], "implementation_roles": ["backend"], "confirmed_by": "Explicit automated test fixture"})
        e.scan()
        file = next(f for f in e.list("files")["items"] if f["role"] == "source")
        e.put("disposition", {"id": "DS1", "source_ref": {"root": "legacy", "path": "Invoice.cs"}, "source_sha256": file["sha256"],
                "disposition": "feature", "feature_ids": ["F1"], "reason": "Test fixture belongs to F1", "reviewed_by": "automated fixture"})
        e.map()
        return f

    def implement(self):
        e = self.engine
        claim = e.claim("F1")
        e.put("stage", {"id": "ST1", "feature_id": "F1", "role": "backend", "summary": "Inert fixture target exists",
                        "output_refs": feature()["target_refs"]})
        e.implemented("F1", claim["token"])

    def test_next_action_build_capture_review_and_acceptance_gates(self):
        e = self.engine
        self.assertEqual(e.next_action()["operation"], "map")
        self.catalog()
        self.assertEqual(e.next_action()["agent"], "migration-backend")
        self.implement()
        self.assertEqual(e.next_action()["operation"], "run_commands")
        result = execute_job(e, create_job(e, "build-target"))
        self.assertEqual(result["state"], "passed", result)
        self.assertEqual(e.next_action()["operation"], "run_scenarios")
        self.assertEqual(e.run("DB1")["state"], "passed")
        self.assertEqual(e.next_action()["agent"], "migration-review")
        e.put("review", {"id": "R1", "feature_id": "F1", "reviewer": "test fixture reviewer",
              "summary": "Bounded test review only", "issues": [], "evidence_refs": feature()["source_refs"] + feature()["target_refs"]})
        report = e.report()
        self.assertTrue(report["ready_for_acceptance"])
        self.assertFalse(report["complete"])

    def test_sqlite_null_empty_and_decimal_regression(self):
        self.catalog()
        self.implement()
        with sqlite3.connect(self.base / "target.sqlite") as db:
            db.execute("UPDATE invoice SET amount='9007199254740992.00', note=''")
        result = self.engine.run("DB1")
        self.assertEqual(result["state"], "failed", result)
        self.assertIn("typed_observations_differ", result["differences"])

    def test_legacy_baseline_change_blocks_even_if_target_matches(self):
        self.catalog()
        self.implement()
        for name in ["legacy.sqlite", "target.sqlite"]:
            with sqlite3.connect(self.base / name) as db: db.execute("DELETE FROM invoice")
        self.assertEqual(self.engine.run("DB1")["state"], "blocked")

    def test_tracked_database_mutation_invalidates_previous_pass(self):
        self.catalog()
        self.implement()
        self.assertEqual(self.engine.run("DB1")["state"], "passed")
        with sqlite3.connect(self.base / "target.sqlite") as db: db.execute("DELETE FROM invoice")
        self.assertEqual(self.engine.report()["features"][0]["scenarios"]["DB1"], "stale")

    def test_subprocess_job_survives_parent_engine_close(self):
        self.catalog()
        job = self.engine.command_start("build-target")
        self.engine.close()
        self.engine = Engine(self.manifest)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = self.engine.command_status(job["job_id"])
            if status["state"] not in {"queued", "running"}: break
            time.sleep(0.05)
        self.assertEqual(status["state"], "passed", status)
        self.assertTrue(status["current"])

    def test_failed_command_and_timeout_are_not_passes(self):
        result = process_capture([sys.executable, "-c", "raise SystemExit(3)"], self.base, 2, 1024)
        self.assertEqual(result["state"], "failed")
        result = process_capture([sys.executable, "-c", "import time; time.sleep(4)"], self.base, 1, 1024)
        self.assertEqual(result["state"], "timed_out")

    def test_output_overflow_stops_process_and_bounds_output(self):
        result = process_capture([sys.executable, "-c", "print('x'*100000)"], self.base, 2, 512)
        self.assertEqual(result["state"], "output_limit")
        self.assertLessEqual(len(result["stdout"]) + len(result["stderr"]), 512)

    def test_changed_build_artifact_invalidates_build_gate(self):
        self.catalog()
        self.implement()
        result = execute_job(self.engine, create_job(self.engine, "build-target"))
        self.assertEqual(result["state"], "passed")
        (self.base / "target/build/artifact").write_text("corrupted")
        self.assertEqual(self.engine.report()["features"][0]["commands"]["build-target"], "stale")

    def test_release_replans_without_losing_target_edits(self):
        self.catalog()
        claim = self.engine.claim("F1")
        target = self.base / "target/Invoice.java"
        target.write_text("// work in progress\n")
        self.engine.release("F1", claim["token"])
        self.assertEqual(target.read_text(), "// work in progress\n")
        self.assertNotEqual(self.engine.claim("F1")["token"], claim["token"])

    def test_typed_json_does_not_coerce_values_or_drop_duplicates(self):
        def observation(value):
            return '{"schema_version":1,"dimension":"database","observations":{"v":' + value + '}}'
        hashes = [decode_observation(observation(v), "database")[1] for v in ["1", "1.0", "true", '"1"', "null", '""']]
        self.assertEqual(len(set(hashes)), len(hashes))
        with self.assertRaises(ValueError):
            decode_observation('{"schema_version":1,"dimension":"database","observations":{"v":1,"v":2}}', "database")

    def test_changed_source_invalidates_file_disposition(self):
        self.catalog()
        p = self.base / "legacy/Invoice.cs"
        p.write_text(p.read_text() + "// change\n")
        self.assertEqual(self.engine.reconcile()["accounted"], 0)
        self.assertEqual(self.engine.next_action()["agent"], "migration-discovery")

    def test_graph_locates_routes_types_exceptions_without_comment_routes(self):
        p = self.base / "legacy/Invoice.cs"
        p.write_text('''// [HttpGet("fake")]
public class Controller {
 [HttpGet("invoice")]
 public string Get() { try { return Helper(); } catch(Exception e) { throw; } }
 public string Helper() { return "x"; }
}''')
        result = self.engine.map()
        self.assertFalse(result["semantic_complete"])
        nodes = self.engine.list("map_nodes", limit=100)["items"]
        routes = [n["label"] for n in nodes if n["kind"] == "route_candidate"]
        self.assertEqual(len(routes), 1)
        self.assertIn("invoice", routes[0])
        self.assertTrue(any(n["kind"] == "exception_path" for n in nodes))


if __name__ == "__main__":
    unittest.main()
