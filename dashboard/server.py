"""
AGT Activity Dashboard -- local server.

Reads logs/audit.jsonl fresh on every request (fetch-on-demand, the same
pattern already proven in governed_agent/dashboard_fetch_demo.py earlier in
this project's history), verifies its HMAC hash chain, and serves it as one
JSON array the frontend renders as an activity feed -- one card per real
governed tool call, built entirely from fields genuinely present in the
audit log (see docs/feature-implemented.md for exactly which fields exist
and which don't -- e.g. cost/SLO/rate-limit-remaining were only added to
audit.jsonl recently; older entries written before that change will show
those fields as null, which the frontend renders as "not recorded", not a
fabricated value).

No new dependencies -- stdlib http.server only.

Usage:
    python dashboard/server.py
    (then open http://localhost:8787 in a browser)
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDIT_LOG_PATH = PROJECT_ROOT / "logs" / "audit.jsonl"
DASHBOARD_DIR = Path(__file__).resolve().parent
PORT = int(os.environ.get("DASHBOARD_PORT", "8787"))

# Must match governance_pipeline.py's _AUDIT_SECRET_KEY default exactly, or
# verification will report every real entry as tampered. See that module's
# docstring for why this is a fixed, publicly-visible local-test key, not a
# production secret.
_DEFAULT_AUDIT_KEY = "local-test-only-not-a-real-secret-see-governance_pipeline.py"

sys.path.insert(0, str(PROJECT_ROOT / "src"))


def read_activity() -> dict:
    """Reads and verifies audit.jsonl, returns a dict shaped for the frontend.

    Mirrors the real available/reason/entries contract already used by
    governed_agent/dashboard_fetch_demo.py -- never raises past this
    function, so a missing file or a broken chain becomes a clear message
    on screen instead of a stack trace.
    """
    if not AUDIT_LOG_PATH.exists():
        return {"available": False, "reason": "No audit log yet -- send a message to the agent first.", "entries": []}

    try:
        from agentmesh.governance import FileAuditSink
        secret_key = os.environ.get("AGT_AUDIT_SECRET_KEY", _DEFAULT_AUDIT_KEY).encode()
        sink = FileAuditSink(AUDIT_LOG_PATH, secret_key=secret_key)
        ok, error = sink.verify_integrity()
        chain_valid = ok
        chain_error = error
    except Exception as exc:  # noqa: BLE001 - report, never crash the server
        chain_valid = False
        chain_error = f"verification error: {exc}"

    entries = []
    with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))

    entries.sort(key=lambda e: e["timestamp"], reverse=True)

    shaped = []
    for e in entries:
        data = e.get("data") or {}
        shaped.append({
            "entry_id": e.get("entry_id"),
            "timestamp": e.get("timestamp"),
            "agent_did": e.get("agent_did"),
            "action": e.get("action"),
            "policy_decision": e.get("policy_decision"),
            "outcome": e.get("outcome"),
            "matched_rule": data.get("matched_rule"),
            "blocked_by": data.get("blocked_by"),
            "compliance_violations": data.get("compliance_violations"),
            "estimated_cost_usd": data.get("estimated_cost_usd"),
            "within_budget": data.get("within_budget"),
            "slo_status": data.get("slo_status"),
            "rate_limit_remaining": data.get("rate_limit_remaining"),
            "trust_score": data.get("trust_score"),
            "injection_type": data.get("injection_type"),
            "threat_level": data.get("threat_level"),
            "confidence": data.get("confidence"),
            "args": data.get("args"),
        })

    return {
        "available": True,
        "chain_valid": chain_valid,
        "chain_error": chain_error,
        "entry_count": len(shaped),
        "entries": shaped,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # noqa: A002 - quiet the default access log
        pass

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - required method name
        if self.path.startswith("/api/activity"):
            self._send_json(read_activity())
            return
        if self.path in ("/", "/index.html"):
            html_path = DASHBOARD_DIR / "index.html"
            body = html_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    # A real bug was found (not fixed here, just guarded against): starting
    # this server multiple times without stopping the previous one left
    # several processes simultaneously bound to the same port on this
    # machine's Windows/WSL socket stack, and curl/the browser would then
    # get routed to whichever stale process happened to still be alive --
    # serving OLD code (missing fields added in a later edit) even after
    # the file on disk was fixed. ThreadingHTTPServer's default socket
    # options didn't raise "address already in use" the way a plain TCP
    # server normally would, so this went undetected for a while. Setting
    # allow_reuse_address = False here makes a genuine port conflict raise
    # a clear OSError immediately instead of silently coexisting.
    ThreadingHTTPServer.allow_reuse_address = False
    try:
        server = ThreadingHTTPServer(("localhost", PORT), Handler)
    except OSError as exc:
        print(f"Could not start on port {PORT}: {exc}")
        print("Another dashboard server is likely still running -- stop it first "
              "(check for old terminal windows, or find/kill the process holding "
              f"port {PORT}) before starting a new one.")
        raise SystemExit(1) from exc
    print(f"AGT Activity Dashboard running at http://localhost:{PORT}")
    print(f"Reading: {AUDIT_LOG_PATH}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
