"""Minimal stdio MCP adapter, negotiated 2025-11-25 / 2025-06-18.

No sampling, prompts, resources, background task, or newest-protocol support is
advertised. The CLI remains available independently of client compatibility.
"""
from __future__ import annotations

import json
import sys

from . import __version__
from .engine import Engine, MigrationError, check, encode

STRING = {"type": "string"}
INTEGER = {"type": "integer"}
OBJECT = {"type": "object"}


def tool(name, description, properties=None, required=(), read_only=False, external=False):
    return {"name": "migration_" + name, "description": description,
            "inputSchema": {"type": "object", "properties": properties or {},
                            "required": list(required), "additionalProperties": False},
            "annotations": {"readOnlyHint": read_only, "destructiveHint": not read_only,
                            "idempotentHint": read_only, "openWorldHint": external}}


TOOLS = [
    tool("map", "Build/save an evidence-located source graph. Call and route matches remain labeled candidates; inspect paginated map_nodes/map_edges/map_gaps."),
    tool("next_action", "Choose the next specialist agent and operation from current saved gates. The host client invokes the native agent.", read_only=True),
    tool("doctor", "Check configured executable availability without running builds.", read_only=True),
    tool("command_start", "Run a predefined manifest command as a durable background job. Commands may build/test/write within the configured scope. No arbitrary argv accepted.",
         {"command_id": STRING}, ["command_id"], external=True),
    tool("command_status", "Poll a saved command job and evidence freshness; does not replay the command.",
         {"job_id": STRING}, ["job_id"], read_only=True),
    tool("semantic_import", "Import source-hash-checked Roslyn declarations/call edges from a successful current configured adapter job.",
         {"job_id": STRING}, ["job_id"]),
    tool("scan", "Inventory registered roots. Produces heuristic candidates, not a verified feature catalog."),
    tool("list", "Read a page of features, scenarios, questions, defects, runs, files, candidates, gaps, or exclusions.",
         {"kind": STRING, "offset": INTEGER, "limit": INTEGER}, ["kind"], True),
    tool("put", "Register/update feature, scenario, question, defect, disposition, type_mapping, plan, stage or review. See docs/v0.2-workflow.md. Never invent source facts or approvals.",
         {"kind": STRING, "record": OBJECT}, ["kind", "record"]),
    tool("packet", "Read bounded source evidence, contracts, questions, defects and declared dependencies for one feature. Fails rather than truncate.",
         {"feature_id": STRING, "max_bytes": INTEGER}, ["feature_id"], True),
    tool("claim", "Lease one feature after checking questions and dependencies. Does not modify application code. Keep the returned token for heartbeat/completion.",
         {"feature_id": STRING, "lease_seconds": INTEGER}, ["feature_id"]),
    tool("heartbeat", "Renew an unexpired feature lease owned by this token.",
         {"feature_id": STRING, "token": STRING, "lease_seconds": INTEGER}, ["feature_id", "token"]),
    tool("release", "Release an owned in-progress feature after saving handoff notes. Retains target edits; useful when requirements change.",
         {"feature_id": STRING, "token": STRING}, ["feature_id", "token"]),
    tool("implemented", "Record current mapped target hashes using an active token. This records implementation only, never a verification pass.",
         {"feature_id": STRING, "token": STRING}, ["feature_id", "token"]),
    tool("run", "Run a characterized HTTP or typed browser/database/integration observation scenario in the configured test environment. Captures execute predefined commands; use isolated fixtures.",
         {"scenario_id": STRING}, ["scenario_id"], external=True),
    tool("report", "Current evidence and coverage counts, with paginated feature details. complete is always false in this alpha.",
         {"offset": INTEGER, "limit": INTEGER}, read_only=True),
    tool("recover", "Reset expired leases and mark abandoned HTTP runs interrupted. Does not replay requests or overwrite files."),
    tool("evidence", "Read a run's digests, metadata, and differences; response bodies remain in the local ledger.",
         {"run_id": STRING}, ["run_id"], True),
]


def validate_arguments(spec, arguments):
    check(isinstance(arguments, dict), "Tool arguments must be an object")
    schema = spec["inputSchema"]
    check(arguments.keys() <= schema["properties"].keys(), "Unexpected tool arguments")
    check(set(schema["required"]) <= arguments.keys(), "Missing required tool arguments")
    types = {"string": str, "integer": int, "object": dict}
    for name, value in arguments.items():
        check(type(value) is types[schema["properties"][name]["type"]], f"Invalid type for {name}")


def dispatch(engine, name, arguments):
    spec = next((t for t in TOOLS if t["name"] == name), None)
    check(spec is not None, "Unknown migration tool")
    validate_arguments(spec, arguments)
    method = name.removeprefix("migration_")
    if method == "report":
        from .engine import integer
        offset, limit = arguments.get("offset", 0), arguments.get("limit", 20)
        integer(offset, 0, 10_000_000, "offset")
        integer(limit, 1, 100, "limit")
        result = engine.report()
        total = len(result["features"])
        result["features"] = result["features"][offset:offset + limit]
        result["next_offset"] = offset + limit if offset + limit < total else None
    else:
        result = getattr(engine, method)(**arguments)
    check(len(encode(result).encode()) <= 200000, "Tool output exceeds 200000 bytes; request a smaller page/packet")
    return {"content": [{"type": "text", "text": encode(result)}], "isError": False}


class Server:
    def __init__(self, manifest):
        self.manifest = manifest
        self.initialized = False
        self.ready = False

    def handle(self, message):
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return {"jsonrpc": "2.0", "id": message.get("id") if isinstance(message, dict) else None,
                    "error": {"code": -32600, "message": "Invalid Request"}}
        id, method = message.get("id"), message["method"]
        notification = "id" not in message
        if notification:
            if method == "notifications/initialized" and self.initialized:
                self.ready = True
            return None
        response = {"jsonrpc": "2.0", "id": id}
        params = message.get("params", {})
        if not isinstance(params, dict):
            return {**response, "error": {"code": -32602, "message": "params must be an object"}}
        if method == "initialize":
            if self.initialized:
                return {**response, "error": {"code": -32600, "message": "Already initialized"}}
            supported = ["2025-11-25", "2025-06-18"]
            version = params.get("protocolVersion")
            self.initialized = True
            return {**response, "result": {"protocolVersion": version if version in supported else supported[0],
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "migration-workbench", "version": __version__},
                    "instructions": "Use migration_report to resume. Preserve defects. Only bounded declared HTTP evidence is supported; never claim full migration completion."}}
        if method == "ping":
            return {**response, "result": {}}
        if not self.ready:
            return {**response, "error": {"code": -32000, "message": "Initialize and send notifications/initialized first"}}
        if method == "tools/list":
            return {**response, "result": {"tools": TOOLS}}
        if method == "tools/call":
            try:
                with Engine(self.manifest) as engine:
                    result = dispatch(engine, params.get("name"), params.get("arguments", {}))
            except Exception as error:
                result = {"content": [{"type": "text", "text": f"{type(error).__name__}: {error}"}], "isError": True}
            return {**response, "result": result}
        return {**response, "error": {"code": -32601, "message": "Method not found"}}


def serve(manifest):
    server = Server(manifest)
    for line in sys.stdin:
        try:
            if len(line.encode("utf-8")) > 1_000_000:
                raise ValueError("Request exceeds one megabyte")
            message = json.loads(line)
            result = server.handle(message)
        except (ValueError, UnicodeError):
            result = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error or oversized request"}}
        if result is not None:
            sys.stdout.write(encode(result) + "\n")
            sys.stdout.flush()
