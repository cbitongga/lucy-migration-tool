from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from modernizer.mcp import Server
from tests.support import project


class MCPTests(unittest.TestCase):
    def test_stdio_lifecycle_and_tools_in_fresh_process(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = project(Path(temp))
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "migration_scan", "arguments": {}}},
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "migration_report", "arguments": {}}},
                {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "migration_list", "arguments": {"kind": "files", "limit": "bad"}}},
            ]
            result = subprocess.run([sys.executable, "-m", "modernizer", "--manifest", str(manifest), "mcp"],
                                    input="\n".join(json.dumps(r) for r in requests) + "\n", text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            messages = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(len(messages), 5)
            self.assertEqual(messages[0]["result"]["protocolVersion"], "2025-11-25")
            self.assertGreater(len(messages[1]["result"]["tools"]), 5)
            report = json.loads(messages[3]["result"]["content"][0]["text"])
            self.assertFalse(report["complete"])
            self.assertTrue(messages[4]["result"]["isError"])

    def test_uninitialized_request_rejected(self):
        result = Server("unused").handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(result["error"]["code"], -32000)

    def test_invalid_request_and_notification(self):
        server = Server("unused")
        self.assertEqual(server.handle([])["error"]["code"], -32600)
        self.assertIsNone(server.handle({"jsonrpc": "2.0", "method": "notifications/cancelled"}))

    def test_newer_protocol_negotiates_supported_version(self):
        result = Server("unused").handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "future-version"}})
        self.assertEqual(result["result"]["protocolVersion"], "2025-11-25")


if __name__ == "__main__":
    unittest.main()
