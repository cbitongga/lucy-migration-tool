"""Exercise the ledger using synthetic HTTP servers; this is not a .NET migration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from modernizer.engine import Engine
from tests.support import LEGACY_BODY, feature, implement, project, register, service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="demo-output", help="New demo directory; existing directories are never overwritten")
    destination = Path(parser.parse_args().output).resolve()
    if destination.exists():
        parser.error("Choose a new output directory; this demo does not overwrite prior work")
    with service() as (legacy, _), service() as (target, target_state):
        manifest = project(destination, legacy, target)
        with Engine(manifest) as engine:
            discovery = engine.scan()
            register(engine, dimensions=["http", "ui", "database"])
            engine.put("defect", {"id": "D1", "feature_id": "F1",
                                  "description": "Synthetic compatibility requirement: preserve the legacy error punctuation exactly.",
                                  "source_refs": feature()["source_refs"], "scenario_ids": ["SF1"]})
            engine.put("question", {"id": "QSCHEMA", "question": "Supply the actual database schema before implementing database verification.",
                                    "feature_ids": [], "blocking": False, "answer": None})
            packet = engine.packet("F1")
            (destination / "packet.json").write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
            claim = engine.claim("F1")
        # Reopen the ledger to demonstrate loss of in-memory/chat state.
        with Engine(manifest) as engine:
            engine.implemented("F1", claim["token"])
            matching = engine.run("SF1")
            # The synthetic target simulates loss of numeric precision.
            target_state["body"] = LEGACY_BODY.replace(b"9007199254740993.10", b"9007199254740992.00")
            mismatching = engine.run("SF1")
            # Reproduce the legacy behavior again; no production application is modified.
            target_state["body"] = LEGACY_BODY
            restored = engine.run("SF1")
            report = engine.report()
            (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            (destination / "evidence.json").write_text(json.dumps(engine.evidence(restored["run_id"]), indent=2) + "\n", encoding="utf-8")
            engine.backup(str(destination / "ledger-backup.sqlite3"))
            summary = {"demo": "Synthetic engine demonstration, not a compiled C#/Java/React migration",
                       "discovery": discovery, "restart_resumed": True,
                       "matching_response": matching["state"], "precision_regression": mismatching["state"],
                       "restored_response": restored["state"], "complete": report["complete"],
                       "unsupported_dimensions": report["features"][0]["unsupported_dimensions"],
                       "report": str(destination / "report.json"),
                       "note": "Demo HTTP servers stop on exit. Start a new demo to rerun comparisons."}
            print(json.dumps(summary, indent=2))
            assert matching["state"] == restored["state"] == "passed"
            assert mismatching["state"] == "failed"
            assert report["complete"] is False


if __name__ == "__main__":
    main()
