from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import Engine, initialize


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evidence-led C# to Java/React migration workbench (alpha)")
    parser.add_argument("--manifest", default="migration.json", help="Manifest path; keep outside application roots")
    subs = parser.add_subparsers(dest="command", required=True)
    p = subs.add_parser("init")
    p.add_argument("--source", required=True)
    p.add_argument("--target", required=True)
    for name in ["scan", "recover", "mcp", "next-action", "doctor", "reconcile"]:
        subs.add_parser(name)
    p = subs.add_parser("map")
    p.add_argument("--format", choices=["summary", "json", "mermaid"], default="summary")
    p.add_argument("--output")
    p = subs.add_parser("agents-install")
    p.add_argument("--destination", default=".")
    p = subs.add_parser("command")
    p.add_argument("command_id")
    p.add_argument("--wait", action="store_true")
    p = subs.add_parser("command-status")
    p.add_argument("job_id")
    p = subs.add_parser("semantic-import")
    p.add_argument("job_id")
    p = subs.add_parser("_command-worker", help=argparse.SUPPRESS)
    p.add_argument("job_id")
    p = subs.add_parser("observation-digest")
    p.add_argument("file")
    p.add_argument("--dimension", required=True, choices=["ui", "database", "integration", "performance"])
    for name in ["vscode-config", "claude-config"]:
        p = subs.add_parser(name)
        p.add_argument("--output", help="Merge into a JSON config; preserve unrelated entries and reject a conflicting server")
    p = subs.add_parser("report")
    p.add_argument("--output", help="Optional JSON report output path")
    p = subs.add_parser("list")
    p.add_argument("kind")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--limit", type=int, default=20)
    p = subs.add_parser("put")
    p.add_argument("kind", choices=["feature", "scenario", "question", "defect", "disposition", "type_mapping", "plan", "stage", "review"])
    p.add_argument("file", help="JSON record path, or - for stdin")
    p = subs.add_parser("packet")
    p.add_argument("feature_id")
    p.add_argument("--max-bytes", type=int)
    for name in ["claim", "heartbeat", "implemented", "release"]:
        p = subs.add_parser(name)
        p.add_argument("feature_id")
        if name != "claim":
            p.add_argument("--token", required=True)
        if name not in {"implemented", "release"}:
            p.add_argument("--lease-seconds", type=int, default=1800)
    p = subs.add_parser("run")
    p.add_argument("scenario_id")
    p = subs.add_parser("evidence")
    p.add_argument("run_id")
    p = subs.add_parser("backup")
    p.add_argument("destination")
    args = vars(parser.parse_args(argv))
    manifest, command = args.pop("manifest"), args.pop("command")
    output = None
    try:
        if command == "mcp":
            from .mcp import serve
            serve(manifest)
            return 0
        if command == "agents-install":
            from .agents import install_agents
            result = install_agents(args["destination"])
        elif command == "observation-digest":
            from .observations import decode_observation
            _, sha = decode_observation(Path(args["file"]).read_bytes(), args["dimension"])
            result = {"dimension": args["dimension"], "legacy_observation_sha256": sha}
        elif command == "init":
            result = initialize(manifest, **args)
        elif command in {"vscode-config", "claude-config"}:
            from .clients import configuration, write_configuration
            result = configuration(manifest, "claude" if command == "claude-config" else "vscode")
            if args["output"]:
                result = write_configuration(result, args["output"])
        else:
            output = args.pop("output", None)
            if command == "put":
                file = args.pop("file")
                args["record"] = json.load(sys.stdin) if file == "-" else json.loads(Path(file).read_text(encoding="utf-8"))
            with Engine(manifest) as engine:
                if command == "map":
                    result = engine.map()
                    if args["format"] != "summary":
                        graph = json.loads(engine.db.execute("SELECT value FROM meta WHERE key='application_map'").fetchone()[0])
                        if args["format"] == "mermaid":
                            from .mapping import mermaid
                            result = mermaid(graph)
                        else:
                            result = graph
                elif command == "command":
                    from .runner import create_job, execute_job, start_job
                    result = execute_job(engine, create_job(engine, args["command_id"])) if args["wait"] else start_job(engine, args["command_id"])
                elif command == "_command-worker":
                    from .runner import execute_job
                    result = execute_job(engine, args["job_id"])
                else:
                    result = getattr(engine, command.replace("-", "_"))(**args)
            if output:
                Path(output).write_text(result if isinstance(result, str) else json.dumps(result, indent=2) + "\n", encoding="utf-8")
        rendered = {"output": str(Path(output).resolve()), "saved": True} if output else result
        print(rendered if isinstance(rendered, str) else json.dumps(rendered, indent=2))
        if command in {"run", "_command-worker"} and result["state"] != "passed":
            return 2
        if command == "command" and args.get("wait") and result["state"] != "passed":
            return 2
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"error": str(error), "type": type(error).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
