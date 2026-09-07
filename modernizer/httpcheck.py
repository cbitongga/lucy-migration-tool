"""Small bounded HTTP observation adapter. Redirects are never followed."""
from __future__ import annotations

import base64
import hashlib
import http.client
import time
from urllib.parse import urlsplit


def validate_base(value: str) -> str:
    p = urlsplit(value)
    if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
        raise ValueError("Test base URL must be http(s), with a host and no embedded credentials")
    if p.query or p.fragment or p.path not in {"", "/"}:
        raise ValueError("Use a test origin without a path, query, or fragment")
    _ = p.port  # Validate malformed ports now.
    return value.rstrip("/")


def observe(base: str, scenario: dict, settings: dict) -> dict:
    p = urlsplit(validate_base(base))
    path = scenario["path"]
    if not path.startswith("/") or path.startswith("//") or "\r" in path or "\n" in path or "#" in path:
        raise ValueError("Scenario path must be an origin-relative path without a fragment")
    timeout = settings.get("timeout_seconds", 5)
    maximum = settings.get("max_response_bytes", 524288)
    cls = http.client.HTTPSConnection if p.scheme == "https" else http.client.HTTPConnection
    connection = cls(p.hostname, p.port, timeout=timeout)
    started = time.monotonic()
    try:
        connection.request("GET", path, headers={"Accept": "*/*", "Accept-Encoding": "identity"})
        response = connection.getresponse()
        pieces, size = [], 0
        while True:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("Response exceeded total observation deadline")
            if connection.sock:
                connection.sock.settimeout(remaining)
            block = response.read1(min(65536, maximum + 1 - size))
            if not block:
                break
            pieces.append(block)
            size += len(block)
            if size > maximum:
                raise ValueError("Response exceeds configured byte limit; comparison blocked")
        body = b"".join(pieces)
        selected = {key: response.headers.get_all(key, []) for key in scenario["compare_headers"]}
        return {"status": response.status, "headers": selected,
                "body_sha256": hashlib.sha256(body).hexdigest(),
                "body_base64": base64.b64encode(body).decode("ascii"),
                "bytes": len(body), "elapsed_ms": round((time.monotonic() - started) * 1000, 3)}
    finally:
        connection.close()


def compare(legacy: dict, target: dict, scenario: dict) -> tuple[str, list[str]]:
    if legacy["status"] != scenario["legacy_status"] or legacy["body_sha256"] != scenario["legacy_body_sha256"]:
        return "blocked", ["legacy_does_not_match_characterized_fixture"]
    differences = [k for k in ("status", "headers", "body_sha256") if legacy[k] != target[k]]
    return ("failed" if differences else "passed"), differences
