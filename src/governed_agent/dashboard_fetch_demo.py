"""
Proof-of-concept: what a dashboard backend's "fetchAgentDecisions" function
would actually do, using the SAME shape this project's unified dashboard
already uses for every Graph capability (see docs/data-sources.md):

  - one independent, named fetcher per capability
  - returns structured data + an explicit availability/fallback state,
    never throws past its own boundary
  - the caller (a real dashboard's frontend) decides what to render from
    that shape -- this function's job stops at "here is the data, and
    here is whether it's trustworthy"

This is NOT a real HTTP endpoint -- no FastAPI/Flask app is stood up here.
It's the plain Python logic a real endpoint would wrap, demonstrated by
calling it directly and printing what a frontend would receive as JSON.
Run it after generating some real decisions (e.g. via governance_pipeline.py)
to see genuine data, not fabricated rows.

Usage: python -m governed_agent.dashboard_fetch_demo
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

AUDIT_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "logs" / "audit.jsonl"
_DEFAULT_KEY = "local-test-only-not-a-real-secret-see-governance_pipeline.py"


def fetch_agent_decisions(agent_id: str | None = None, limit: int = 50) -> dict[str, Any]:
    """The AGT equivalent of this project's fetchAgentIdentities.

    Reads audit.jsonl fresh on every call (fetch-on-demand, matching how
    every other capability in docs/data-sources.md works) -- no caching,
    no persistent connection to the agent process. Verifies the HMAC chain
    before returning anything, the same way a real dashboard should never
    show data it hasn't checked.

    Returns a dict shaped like this project's other capabilities:
      - available: bool -- false if the file is missing or the chain is broken
      - reason: str | None -- why, when available is false
      - entries: list[dict] -- the decisions themselves, newest first
      - truncated: bool -- true if `limit` cut off older entries
    """
    if not AUDIT_LOG_PATH.exists():
        return {"available": False, "reason": "no audit log written yet", "entries": [], "truncated": False}

    try:
        from agentmesh.governance import FileAuditSink
        secret_key = os.environ.get("AGT_AUDIT_SECRET_KEY", _DEFAULT_KEY).encode()
        sink = FileAuditSink(AUDIT_LOG_PATH, secret_key=secret_key)
        ok, error = sink.verify_integrity()
        if not ok:
            return {"available": False, "reason": f"audit chain integrity check failed: {error}", "entries": [], "truncated": False}
    except Exception as exc:  # noqa: BLE001 - report, don't crash the caller
        return {"available": False, "reason": f"verification error: {exc}", "entries": [], "truncated": False}

    entries = []
    with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))

    if agent_id:
        entries = [e for e in entries if e.get("agent_did") == agent_id]

    entries.sort(key=lambda e: e["timestamp"], reverse=True)
    truncated = len(entries) > limit
    entries = entries[:limit]

    shaped = [
        {
            "entry_id": e["entry_id"],
            "timestamp": e["timestamp"],
            "agent_did": e["agent_did"],
            "action": e["action"],
            "decision": e["policy_decision"],
            "outcome": e["outcome"],
            "matched_rule": (e.get("data") or {}).get("matched_rule"),
            "args": (e.get("data") or {}).get("args"),
        }
        for e in entries
    ]

    return {"available": True, "reason": None, "entries": shaped, "truncated": truncated}


if __name__ == "__main__":
    result = fetch_agent_decisions()
    print(json.dumps(result, indent=2))
