"""
Standalone verifier for logs/audit.jsonl -- run this any time you want to
prove the audit trail hasn't been tampered with.

Uses agentmesh.governance.AuditLog's own real, built-in verify_integrity()
method -- an HMAC-signed, hash-chained check confirmed real by direct
inspection, not a hand-rolled reimplementation (an earlier version of this
script computed its own SHA-256 chain by hand; that's been replaced now that
the real AGT AuditLog + FileAuditSink are wired into governance_pipeline.py
directly, since duplicating what AGT itself already verifies would just be
two things that could disagree).

Requires the same HMAC secret key the audit log was written with. Uses the
same default as governance_pipeline.py (a fixed, publicly-visible
local-test-only key -- NOT a real secret; see that module's docstring) so
this verifies correctly out of the box, unless AGT_AUDIT_SECRET_KEY was
overridden when the agent ran, in which case set it the same way here too.

Usage:  python -m governed_agent.verify_audit
"""

import os
import sys
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "logs" / "audit.jsonl"

_DEFAULT_KEY = "local-test-only-not-a-real-secret-see-governance_pipeline.py"


def verify(path: Path) -> tuple[bool, str | None]:
    """Uses FileAuditSink.verify_integrity() directly, NOT AuditLog.verify_integrity().

    Confirmed by reading the installed package's source
    (agentmesh.governance.audit.AuditLog.verify_integrity) that AuditLog's
    version checks an in-memory chain built up by calls to .log() during
    the CURRENT process's lifetime -- it never reads the file at all, so a
    freshly-constructed AuditLog (as this script necessarily has, since it
    runs in a separate process from whatever wrote the log) always reports
    "OK" on an empty chain, even for a file that was actually tampered with.
    Confirmed directly: this bug silently passed a deliberately-tampered
    copy of this project's own audit.jsonl during testing.
    FileAuditSink.verify_integrity() is the one that actually does what its
    docstring says ("Read back the file and verify hash chain + HMAC
    signatures") -- confirmed by testing it correctly flags the same
    tampered file AuditLog's version missed.
    """
    from agentmesh.governance import FileAuditSink

    secret_key = os.environ.get("AGT_AUDIT_SECRET_KEY", _DEFAULT_KEY).encode()
    sink = FileAuditSink(path, secret_key=secret_key)
    return sink.verify_integrity()


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    if not path.exists():
        print(f"No audit log found at {path} yet -- it's created on the first governed tool "
              f"call. Send a message that triggers a tool (e.g. \"show me invoice INV-1004\") "
              f"via Teams or a terminal test, then run this again.")
        sys.exit(0)

    ok, error = verify(path)
    if ok:
        print(f"OK -- {path} verified, no tampering or chain breaks detected.")
    else:
        print(f"PROBLEM in {path}: {error}")
        sys.exit(1)
