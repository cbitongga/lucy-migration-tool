"""Client configuration: both agents run the same engine and manifest."""
from __future__ import annotations
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from .engine import check


def configuration(manifest, client):
    check(client in {"claude", "vscode"}, "Unknown MCP client")
    script = Path(__file__).resolve().parents[1] / "run_modernizer.py"
    entry = [str(script)] if script.is_file() else ["-m", "modernizer"]
    server = {"type": "stdio", "command": sys.executable,
              "args": entry + ["--manifest", str(Path(manifest).resolve()), "mcp"]}
    return {"mcpServers" if client == "claude" else "servers": {"migration-workbench": server}}


def write_configuration(config, destination):
    """Merge one server, preserving other settings; reject conflicting registration."""
    p = Path(destination).absolute()
    check(not p.is_symlink(), "Configuration destination may not be a symlink")
    original = p.read_bytes() if p.exists() else None
    existing = json.loads(original.decode("utf-8")) if original is not None else {}
    check(isinstance(existing, dict), "Existing configuration must be a JSON object")
    key = next(iter(config))
    entries = existing.get(key, {})
    check(isinstance(entries, dict), f"Existing {key} must be a JSON object")
    desired = config[key]["migration-workbench"]
    old = entries.get("migration-workbench")
    check(old is None or old == desired,
          "migration-workbench already points to a different configuration. Review and update that entry explicitly; nothing was changed.")
    if old == desired:
        return {"path": str(p), "changed": False, "backup": None}
    merged = {**existing, key: {**entries, "migration-workbench": desired}}
    p.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if original is not None:
        backup = p.with_name(p.name + ".backup-" + uuid.uuid4().hex)
        with backup.open("xb") as handle:
            handle.write(original)
        backup.chmod(0o600)
    fd, temporary = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=p.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(merged, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        check(not p.is_symlink(), "Configuration became a symlink; retry after review")
        check((p.read_bytes() if p.exists() else None) == original, "Configuration changed during setup; retry after review")
        os.replace(temporary, p)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"path": str(p), "changed": True, "backup": str(backup) if backup else None}
