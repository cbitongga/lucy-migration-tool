from __future__ import annotations

import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from modernizer.engine import Engine, MigrationError
from tests.support import LEGACY_BODY, feature, implement, project, register, scenario, service


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.manifest = project(self.base)
        self.engine = Engine(self.manifest)

    def tearDown(self):
        self.engine.close()
        self.temp.cleanup()

    def test_inventory_candidates_do_not_become_features(self):
        scan = self.engine.scan()
        self.assertGreater(scan["candidates"], 0)
        self.assertEqual(self.engine.report()["counts"]["features_registered"], 0)
        self.assertFalse(self.engine.report()["complete"])

    def test_inventory_exclusions_and_unsupported_files_remain_visible(self):
        (self.base / "legacy/bin").mkdir()
        (self.base / "legacy/blob.dat").write_bytes(b"\x00\x01")
        self.engine.scan()
        self.assertEqual(self.engine.list("exclusions")["total"], 1)
        self.assertIn("not_text_analyzed", [g["reason"] for g in self.engine.list("gaps")["items"]])

    def test_fresh_process_resumes_and_completes_lease(self):
        register(self.engine)
        claim = self.engine.claim("F1")
        self.engine.close()
        self.engine = Engine(self.manifest)
        self.engine.heartbeat("F1", claim["token"])
        result = self.engine.implemented("F1", claim["token"])
        self.assertFalse(result["verified"])
        self.assertTrue(self.engine.report()["features"][0]["implementation_current"])

    def test_only_one_active_lease(self):
        register(self.engine)
        self.engine.claim("F1")
        with Engine(self.manifest) as other:
            with self.assertRaisesRegex(MigrationError, "already leased"):
                other.claim("F1")

    def test_expiry_recovery_never_marks_work_done(self):
        register(self.engine)
        claim = self.engine.claim("F1")
        self.engine.db.execute("UPDATE tasks SET lease_until=0")
        recovered = self.engine.recover()
        self.assertEqual(recovered["recovered_tasks"], 1)
        with self.assertRaises(MigrationError):
            self.engine.implemented("F1", claim["token"])
        self.assertEqual(self.engine.report()["features"][0]["task_state"], "ready")

    def test_packet_never_silently_truncates(self):
        register(self.engine)
        (self.base / "legacy/Invoice.cs").write_text("x" * 5000 + "\n" * 5)
        with self.assertRaisesRegex(MigrationError, "budget exceeded"):
            self.engine.packet("F1", max_bytes=1024)
        packet = self.engine.packet("F1")
        self.assertIn("x" * 5000, packet["source"][0]["text"])

    def test_missing_source_range_is_rejected(self):
        register(self.engine)
        (self.base / "legacy/Invoice.cs").write_text("one line\n")
        with self.assertRaisesRegex(MigrationError, "range no longer exists"):
            self.engine.packet("F1")

    def test_source_change_blocks_old_claim(self):
        register(self.engine)
        claim = self.engine.claim("F1")
        p = self.base / "legacy/Invoice.cs"
        p.write_text(p.read_text() + "// changed\n")
        with self.assertRaisesRegex(MigrationError, "source/contracts changed"):
            self.engine.implemented("F1", claim["token"])

    def test_target_change_invalidates_implementation(self):
        register(self.engine)
        implement(self.engine)
        (self.base / "target/Invoice.java").write_text("changed")
        self.assertFalse(self.engine.report()["features"][0]["implementation_current"])

    def test_target_build_outputs_do_not_invalidate_source_claim(self):
        register(self.engine)
        claim = self.engine.claim("F1")
        (self.base / "target/node_modules").mkdir()
        (self.base / "target/Invoice.java").write_text("// actual target edit during claim\n")
        self.engine.implemented("F1", claim["token"])
        self.assertTrue(self.engine.report()["features"][0]["implementation_current"])

    def test_unknown_blocking_questions_prevent_claim(self):
        register(self.engine)
        q = {"id": "Q1", "question": "Which rounding rule?", "feature_ids": ["F1"], "blocking": True, "answer": None}
        self.engine.put("question", q)
        with self.assertRaisesRegex(MigrationError, "Blocking questions"):
            self.engine.claim("F1")
        q["answer"] = "Preserve the observed decimal fixture; confirmed by test owner."
        self.engine.put("question", q)
        self.engine.claim("F1")

    def test_dependencies_in_packet_and_execution_order(self):
        register(self.engine, "F1")
        register(self.engine, "F2", depends_on=["F1"])
        packet = self.engine.packet("F2")
        self.assertEqual([f["id"] for f in packet["features_in_dependency_order"]], ["F1", "F2"])
        with self.assertRaisesRegex(MigrationError, "dependencies first"):
            self.engine.claim("F2")
        implement(self.engine, "F1")
        implement(self.engine, "F2")

    def test_cycle_rejected_and_missing_dependency_reported(self):
        self.engine.put("feature", feature("F1", depends_on=["F2"]))
        with self.assertRaisesRegex(MigrationError, "Dependency cycle"):
            self.engine.put("feature", feature("F2", depends_on=["F1"]))
        self.assertIn("missing_dependency", self.engine.report()["features"][0]["blocking_questions"])

    def test_source_path_traversal_and_symlinks_rejected(self):
        f = feature()
        f["source_refs"][0]["path"] = "../migration.json"
        with self.assertRaises(MigrationError):
            self.engine.put("feature", f)
        link = self.base / "legacy/linked.cs"
        try:
            link.symlink_to(self.base / "legacy/Invoice.cs")
        except OSError:
            self.skipTest("Symlinks unavailable")
        f["source_refs"][0]["path"] = "linked.cs"
        with self.assertRaisesRegex(MigrationError, "Symlink"):
            self.engine.put("feature", f)

    def test_missing_target_not_marked_implemented(self):
        f = feature()
        f["target_refs"][0]["path"] = "Future.java"
        self.engine.put("feature", f)
        claim = self.engine.claim("F1")
        with self.assertRaisesRegex(MigrationError, "does not exist"):
            self.engine.implemented("F1", claim["token"])

    def test_consistent_backup_restores_feature_and_task(self):
        register(self.engine)
        implement(self.engine)
        dest = self.base / "backup.sqlite3"
        self.engine.backup(str(dest))
        with sqlite3.connect(dest) as backup:
            self.assertEqual(backup.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(backup.execute("SELECT state FROM tasks").fetchone()[0], "implemented")


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def configured(self, legacy, target, dimensions=None):
        manifest = project(self.base, legacy, target)
        engine = Engine(manifest)
        self.addCleanup(engine.close)
        register(engine, dimensions=dimensions)
        return engine

    def test_exact_match_and_preserved_defect(self):
        with service() as (old, _), service() as (new, _):
            e = self.configured(old, new)
            e.put("defect", {"id": "D1", "feature_id": "F1", "description": "Preserve legacy punctuation", "source_refs": feature()["source_refs"], "scenario_ids": ["SF1"]})
            implement(e)
            self.assertEqual(e.run("SF1")["state"], "passed")
            report = e.report()
            self.assertEqual(report["counts"]["scenarios_passed"], 1)
            self.assertTrue(report["features"][0]["preserved_defects"][0]["verified"])
            self.assertFalse(report["complete"])

    def test_numeric_precision_change_fails(self):
        changed = LEGACY_BODY.replace(b"9007199254740993.10", b"9007199254740992.00")
        with service() as (old, _), service(changed) as (new, _):
            e = self.configured(old, new)
            implement(e)
            result = e.run("SF1")
            self.assertEqual(result["state"], "failed")
            self.assertIn("body_sha256", result["differences"])

    def test_both_systems_broken_is_not_a_pass(self):
        with service(b"unavailable", 503) as (old, _), service(b"unavailable", 503) as (new, _):
            e = self.configured(old, new)
            implement(e)
            self.assertEqual(e.run("SF1")["state"], "blocked")

    def test_status_and_selected_header_mismatch(self):
        with service() as (old, _), service(status=201, content_type="text/plain") as (new, _):
            e = self.configured(old, new)
            implement(e)
            result = e.run("SF1")
            self.assertEqual(set(result["differences"]), {"status", "headers"})

    def test_latest_failure_overrides_previous_pass(self):
        with service() as (old, _), service() as (new, state):
            e = self.configured(old, new)
            implement(e)
            self.assertEqual(e.run("SF1")["state"], "passed")
            state["body"] = b"regression"
            self.assertEqual(e.run("SF1")["state"], "failed")
            self.assertEqual(e.report()["counts"]["scenarios_passed"], 0)

    def test_source_target_and_contract_changes_stale_prior_evidence(self):
        with service() as (old, _), service() as (new, _):
            e = self.configured(old, new)
            implement(e)
            e.run("SF1")
            p = self.base / "target/Invoice.java"
            original = p.read_text()
            p.write_text(original + "// change\n")
            self.assertEqual(e.report()["features"][0]["scenarios"]["SF1"], "stale")
            p.write_text(original)
            f = feature()
            f["contract"] += " New contract."
            e.put("feature", f)
            self.assertEqual(e.report()["counts"]["scenarios_passed"], 0)

    def test_ui_database_claim_cannot_pass_from_http_evidence(self):
        with service() as (old, _), service() as (new, _):
            e = self.configured(old, new, dimensions=["http", "ui", "database"])
            implement(e)
            e.run("SF1")
            row = e.report()["features"][0]
            self.assertTrue(row["http_scenarios_passing"])
            self.assertFalse(row["verified_for_declared_scope"])
            self.assertEqual(row["unsupported_dimensions"], ["database", "ui"])

    def test_response_over_limit_blocks_instead_of_truncating(self):
        with service(b"x" * 2048) as (old, _), service() as (new, _):
            e = self.configured(old, new)
            implement(e)
            self.assertEqual(e.run("SF1")["state"], "blocked")

    def test_input_change_during_observation_stales_result(self):
        with service() as (old, _), service() as (new, _):
            e = self.configured(old, new)
            implement(e)
            from modernizer.httpcheck import observe
            def changing(*args):
                result = observe(*args)
                p = self.base / "target/Invoice.java"
                p.write_text(p.read_text() + "// changed during run\n")
                return result
            with patch("modernizer.engine.observe", side_effect=changing):
                self.assertEqual(e.run("SF1")["state"], "stale")

    def test_interrupted_run_cannot_pass(self):
        with service() as (old, _), service() as (new, _):
            e = self.configured(old, new)
            implement(e)
            with patch("modernizer.engine.observe", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    e.run("SF1")
            self.assertEqual(e.report()["counts"]["scenarios_passed"], 0)
            e.db.execute("UPDATE runs SET lease_until=0")
            self.assertEqual(e.recover()["interrupted_runs"], 1)
            self.assertEqual(e.report()["features"][0]["scenarios"]["SF1"], "interrupted")


if __name__ == "__main__":
    unittest.main()
