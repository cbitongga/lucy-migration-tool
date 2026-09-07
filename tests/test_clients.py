import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from modernizer.clients import configuration, write_configuration
from modernizer.engine import Engine, MigrationError
from tests.support import project, register


class ClientTests(unittest.TestCase):
    def test_clients_use_same_server_command_and_ledger(self):
        with tempfile.TemporaryDirectory(prefix="migration space ") as temp:
            manifest = project(Path(temp))
            a = configuration(manifest, "claude")["mcpServers"]["migration-workbench"]
            b = configuration(manifest, "vscode")["servers"]["migration-workbench"]
            self.assertEqual(a, b)
            with Engine(manifest) as engine:
                register(engine)
                engine.claim("F1")
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "clientInfo": {"name": "claude-config-test", "version": "1"}, "capabilities": {}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "migration_report", "arguments": {}}}
            ]
            result = subprocess.run([a["command"], *a["args"]], cwd=temp,
                input="\n".join(json.dumps(r) for r in requests) + "\n", text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            replies = [json.loads(x) for x in result.stdout.splitlines()]
            self.assertFalse(replies[-1]["result"]["isError"])
            report = json.loads(replies[-1]["result"]["content"][0]["text"])
            self.assertEqual(report["features"][0]["id"], "F1")
            self.assertEqual(report["features"][0]["task_state"], "in_progress")

    def test_merge_preserves_existing_settings_and_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / ".mcp.json"
            original = '{"mcpServers":{"other":{"command":"other-tool"}},"custom":true}\n'
            p.write_text(original)
            config = configuration(Path(temp) / "migration.json", "claude")
            result = write_configuration(config, p)
            merged = json.loads(p.read_text())
            self.assertEqual(merged["mcpServers"]["other"], {"command": "other-tool"})
            self.assertTrue(merged["custom"])
            self.assertEqual(Path(result["backup"]).read_text(), original)
            self.assertFalse(write_configuration(config, p)["changed"])

    def test_conflicting_server_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / ".mcp.json"
            original = '{"mcpServers":{"migration-workbench":{"command":"different"}}}'
            p.write_text(original)
            with self.assertRaisesRegex(MigrationError, "different configuration"):
                write_configuration(configuration("migration.json", "claude"), p)
            self.assertEqual(p.read_text(), original)

    def test_malformed_config_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / ".mcp.json"
            p.write_text("not JSON")
            with self.assertRaises(ValueError):
                write_configuration(configuration("migration.json", "claude"), p)
            self.assertEqual(p.read_text(), "not JSON")

    def test_cli_writes_claude_config(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / ".mcp.json"
            run = subprocess.run([sys.executable, "-m", "modernizer", "--manifest", str(Path(temp) / "migration.json"),
                                  "claude-config", "--output", str(p)], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("mcpServers", json.loads(p.read_text()))
            self.assertTrue(json.loads(run.stdout)["changed"])

    def test_claude_instructions_import_shared_rules(self):
        root = Path(__file__).resolve().parents[1]
        self.assertIn("@.github/copilot-instructions.md", (root / "CLAUDE.md").read_text())
        self.assertIn("Copilot and Claude Code", (root / ".github/copilot-instructions.md").read_text())
