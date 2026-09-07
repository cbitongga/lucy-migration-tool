"""Configured command execution with durable jobs, deadlines, and bounded output."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from .engine import check, encode, identifier, integer, shape, text
from .discovery import hash_file, digest


def validate_commands(config, base):
    commands = config.get("commands", {})
    check(isinstance(commands, dict), "commands must be an object keyed by command ID")
    roots = {r["id"]: r for r in config["roots"]}
    for id, command in commands.items():
        identifier(id)
        shape(command, ["argv", "cwd_root", "purpose"], ["timeout_seconds", "max_output_bytes", "expected_artifacts"])
        check(command["cwd_root"] in roots, "Command cwd_root must name a registered root")
        check(command["purpose"] in {"build", "test", "capture", "setup"}, "Invalid command purpose")
        check(isinstance(command["argv"], list) and command["argv"] and all(isinstance(s, str) and s and "\0" not in s for s in command["argv"]), "argv must be a nonempty string array; shell strings are unsupported")
        integer(command.get("timeout_seconds", 120), 1, 3600, "command timeout_seconds")
        integer(command.get("max_output_bytes", 1000000), 256, 10000000, "command max_output_bytes")
        artifacts = command.get("expected_artifacts", [])
        check(isinstance(artifacts, list), "expected_artifacts must be an array")
        check(command["purpose"] != "build" or artifacts, "Build commands must declare expected_artifacts")
        for artifact in artifacts:
            shape(artifact, ["root", "path"])
            check(artifact["root"] in roots, "Artifact root must be registered")
            relative = Path(artifact["path"])
            check(relative.parts and not relative.is_absolute() and ".." not in relative.parts and "\\" not in artifact["path"], "Artifact path must stay within its root")


def artifact_hashes(engine, command):
    roots = {r["id"]: (engine.base / r["path"]).resolve() for r in engine.config["roots"]}
    hashes = {}
    for ref in command.get("expected_artifacts", []):
        p = roots[ref["root"]]
        for part in Path(ref["path"]).parts:
            p /= part
            check(not p.is_symlink(), "Artifact symlinks are unsupported")
        check(p.exists(), "Expected build artifact is missing: " + str(p))
        if p.is_file():
            sha = hash_file(p)
        else:
            files = sorted(p.rglob("*"))
            check(not any(f.is_symlink() for f in files), "Artifact tree contains a symlink")
            values = [(f.relative_to(p).as_posix(), hash_file(f)) for f in files if f.is_file()]
            check(values, "Expected build artifact directory is empty")
            sha = digest(encode(values).encode())
        hashes[ref["root"] + ":" + ref["path"]] = sha
    return hashes


def expand(engine, command):
    roots = {r["id"]: str((engine.base / r["path"]).resolve()) for r in engine.config["roots"]}
    replacements = {"{python}": sys.executable, "{control}": str(engine.base),
                    "{tool}": str(Path(__file__).resolve().parents[1]),
                    **{"{root:" + k + "}": v for k, v in roots.items()}}
    argv = []
    for arg in command["argv"]:
        for key, value in replacements.items():
            arg = arg.replace(key, value)
        argv.append(arg)
    return argv, roots[command["cwd_root"]]


def doctor(engine):
    results = []
    for id, command in engine.config.get("commands", {}).items():
        argv, cwd = expand(engine, command)
        executable = argv[0]
        resolved = shutil.which(executable) if not os.path.dirname(executable) else str((Path(cwd) / executable).resolve())
        available = bool(resolved and Path(resolved).is_file() and os.access(resolved, os.X_OK))
        results.append({"id": id, "executable": executable, "available": available,
                        "purpose": command["purpose"], "cwd": cwd})
    return {"commands": results, "ready": bool(results) and all(r["available"] for r in results),
            "note": "Executable availability only, not proof of dependency installation or a successful build."}


def stop_process(process):
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        elif process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
    except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
        if process.poll() is None:
            process.kill()


def process_capture(argv, cwd, timeout, maximum):
    process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=os.name == "posix")
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    lock, overflow = threading.Lock(), threading.Event()
    def drain(name, stream):
        while True:
            chunk = stream.read1(65536)
            if not chunk: break
            with lock:
                used = sum(len(x) for x in buffers.values())
                remaining = max(0, maximum - used)
                buffers[name].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    overflow.set()
                    break
    readers = [threading.Thread(target=drain, args=(name, getattr(process, name)), daemon=True) for name in buffers]
    for thread in readers: thread.start()
    deadline, state = time.monotonic() + timeout, None
    try:
        while process.poll() is None:
            if overflow.is_set():
                state = "output_limit"
                break
            if time.monotonic() >= deadline:
                state = "timed_out"
                break
            time.sleep(0.02)
    finally:
        stop_process(process)  # Also remove children left behind by a completed command.
        process.wait(timeout=10)
        for thread in readers: thread.join(timeout=2)
        for name in buffers: getattr(process, name).close()
    if overflow.is_set(): state = "output_limit"
    return {"state": state or ("passed" if process.returncode == 0 else "failed"),
            "exit_code": process.returncode, "stdout": bytes(buffers["stdout"]),
            "stderr": bytes(buffers["stderr"])}


def create_job(engine, command_id):
    command = engine.config.get("commands", {}).get(command_id)
    check(command is not None, f"Unknown configured command: {command_id}")
    id, now = str(uuid.uuid4()), time.time()
    fp, _ = engine.snapshot()
    engine.db.execute("INSERT INTO command_jobs VALUES(?,?,?,?,?,?,?,?)",
                      (id, command_id, "queued", fp, now + command.get("timeout_seconds", 120) + 60,
                       encode(command), "{}", now))
    engine.event("command_queued", {"job_id": id, "command_id": command_id})
    return id


def execute_job(engine, job_id):
    row = engine.db.execute("SELECT * FROM command_jobs WHERE id=?", (job_id,)).fetchone()
    check(row is not None, "Unknown command job")
    changed = engine.db.execute("UPDATE command_jobs SET state='running' WHERE id=? AND state='queued'", (job_id,)).rowcount
    check(changed == 1, "Job is already running or finished; never replay it automatically")
    command = json.loads(row["command"])
    directory = engine.state / "jobs" / job_id
    directory.mkdir(parents=True, exist_ok=False)
    result = {"state": "blocked", "exit_code": None}
    try:
        check(engine.config.get("commands", {}).get(row["command_id"]) == command, "Command changed after job creation")
        check(engine.snapshot()[0] == row["fingerprint"], "Inputs changed before command execution")
        argv, cwd = expand(engine, command)
        result = process_capture(argv, cwd, command.get("timeout_seconds", 120), command.get("max_output_bytes", 1000000))
        for name in ["stdout", "stderr"]:
            (directory / (name + ".bin")).write_bytes(result.pop(name))
        if result["state"] == "passed":
            result["artifact_hashes"] = artifact_hashes(engine, command)
        if engine.snapshot()[0] != row["fingerprint"]:
            result["state"] = "stale"
            result["error"] = "Inputs changed during command; declare generated output directories as exclusions and retry intentionally."
    except Exception as error:
        result = {"state": "blocked", "exit_code": None, "error": f"{type(error).__name__}: {error}"}
    result["job_id"] = job_id
    result["command_id"] = row["command_id"]
    result["output_directory"] = str(directory)
    engine.db.execute("UPDATE command_jobs SET state=?,result=? WHERE id=?", (result["state"], encode(result), job_id))
    engine.event("command_finished", {"job_id": job_id, "state": result["state"]})
    return result


def start_job(engine, command_id):
    id = create_job(engine, command_id)
    script = Path(__file__).resolve().parents[1] / "run_modernizer.py"
    entry = [str(script)] if script.is_file() else ["-m", "modernizer"]
    try:
        child = subprocess.Popen([sys.executable, *entry, "--manifest", str(engine.manifest), "_command-worker", id],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True, close_fds=True)
        threading.Thread(target=child.wait, daemon=True).start()
        return {"job_id": id, "state": "queued", "worker_pid": child.pid,
                "next": "Poll command_status; engine/client restarts do not turn an unfinished job into a pass."}
    except OSError as error:
        engine.db.execute("UPDATE command_jobs SET state='blocked',result=? WHERE id=?", (encode({"error": str(error)}), id))
        raise


def status(engine, job_id):
    row = engine.db.execute("SELECT * FROM command_jobs WHERE id=?", (job_id,)).fetchone()
    check(row is not None, "Unknown command job")
    result = {"job_id": job_id, "command_id": row["command_id"], "state": row["state"],
              "current": row["fingerprint"] == engine.snapshot()[0], "result": json.loads(row["result"])}
    if row["state"] in {"queued", "running"} and row["lease_until"] <= time.time():
        result["state"] = "interrupted"
    if row["state"] == "passed":
        try:
            result["current"] = result["current"] and artifact_hashes(engine, json.loads(row["command"])) == result["result"].get("artifact_hashes", {})
        except (OSError, ValueError):
            result["current"] = False
    return result


def current_command_states(engine, ids, fp):
    states = {}
    for id in ids:
        row = engine.db.execute("SELECT * FROM command_jobs WHERE command_id=? ORDER BY created DESC,rowid DESC LIMIT 1", (id,)).fetchone()
        states[id] = "unrun" if row is None else "stale" if row["fingerprint"] != fp else row["state"]
        if row is not None and states[id] == "passed":
            try:
                if artifact_hashes(engine, json.loads(row["command"])) != json.loads(row["result"]).get("artifact_hashes", {}):
                    states[id] = "stale"
            except (OSError, ValueError):
                states[id] = "stale"
    return states
