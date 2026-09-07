from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from modernizer.engine import Engine, initialize

LEGACY_BODY = b'{"amount":"9007199254740993.10","emptyNameError":"Name required!"}'


@contextmanager
def service(body=LEGACY_BODY, status=200, content_type="application/json"):
    state = {"body": body, "status": status, "content_type": content_type, "hits": 0}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["hits"] += 1
            self.send_response(state["status"])
            self.send_header("Content-Type", state["content_type"])
            self.send_header("Content-Length", str(len(state["body"])))
            self.end_headers()
            self.wfile.write(state["body"])
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def project(base: Path, legacy_url=None, target_url=None):
    source, target = base / "legacy", base / "target"
    source.mkdir(parents=True)
    target.mkdir()
    (source / "Invoice.cs").write_text('''// Inert source fixture for engine tests; not a compiled application.
public class Invoice {
    public decimal Amount = 9007199254740993.10m;
    public string EmptyNameError = "Name required!"; // preserve legacy punctuation
}
''', encoding="utf-8")
    (target / "Invoice.java").write_text('''// Inert target fixture, not a generated or compiled migration.
class Invoice {
    java.math.BigDecimal amount = new java.math.BigDecimal("9007199254740993.10");
    String emptyNameError = "Name required!";
}
''', encoding="utf-8")
    manifest = base / "migration.json"
    initialize(str(manifest), str(source), str(target))
    if legacy_url:
        c = json.loads(manifest.read_text())
        c["http"] = {"legacy_base_url": legacy_url, "target_base_url": target_url,
                     "environment_id": "synthetic-local-demo", "legacy_build_id": "python-fixture-old-v1",
                     "target_build_id": "python-fixture-new-v1", "timeout_seconds": 2, "max_response_bytes": 1024}
        manifest.write_text(json.dumps(c), encoding="utf-8")
    return manifest


def feature(id="F1", depends_on=None, dimensions=None):
    return {"id": id, "title": "Invoice boundary fixture", "contract": "Return the exact legacy amount string and error punctuation.",
            "source_refs": [{"root": "legacy", "path": "Invoice.cs", "start": 1, "end": 5}],
            "target_refs": [{"root": "target", "path": "Invoice.java"}],
            "depends_on": depends_on or [], "required_scenarios": ["S" + id],
            "required_dimensions": dimensions or ["http"]}


def scenario(id="F1"):
    return {"id": "S" + id, "feature_id": id, "path": "/invoice", "legacy_status": 200,
            "legacy_body_sha256": hashlib.sha256(LEGACY_BODY).hexdigest(), "compare_headers": ["content-type"]}


def register(engine, id="F1", **kwargs):
    engine.put("feature", feature(id, **kwargs))
    engine.put("scenario", scenario(id))


def implement(engine, id="F1"):
    claim = engine.claim(id)
    return engine.implemented(id, claim["token"])
