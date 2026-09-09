"""
Standalone proof that the real Agent Control Specification (ACS) engine
correctly evaluates this project's 4 tool rules, expressed as genuine Rego
(policy/tools.rego), via the actual agent_control_specification SDK built
from source (see docs/implementation-notes.md for the build steps and why
this project's live agent does NOT use this engine by default).

This is NOT wired into governance_pipeline.py or maf_agent.py -- it's a
standalone verification you can run any time to confirm the real ACS build
still works, independent of whether it's the engine actually running the
Teams agent.

Requires: `agent_control_specification` built and installed (see
docs/implementation-notes.md, "Real ACS/Rego (optional, not wired into the
live agent)" -- a `maturin develop --release` build against the Rust source
cloned from microsoft/agent-governance-toolkit's policy-engine/ directory).
If that build hasn't been done, this script's import will fail with a clear
ModuleNotFoundError rather than a confusing downstream error.

Usage: python policies/acs/test_acs_policy.py
"""

from pathlib import Path

try:
    from agent_control_specification import AgentControl, HostSession
except ImportError as exc:
    raise SystemExit(
        "agent_control_specification is not built/installed in this venv.\n"
        "This is expected unless you've deliberately built the real ACS SDK "
        "-- see docs/implementation-notes.md for the build steps.\n"
        f"(original error: {exc})"
    ) from exc

MANIFEST_PATH = str(Path(__file__).parent / "manifest.yaml")

TESTS = [
    ("read_invoice", {"invoice_id": "INV-1004"}, "ALLOW"),
    ("drop_table", {"name": "invoices"}, "DENY"),
    ("send_email", {"to": "x@gmail.com", "dlp_ratchet": "restricted",
                     "recipient_is_external": True, "body_length": 50}, "DENY"),
    ("send_email", {"to": "x@quadrasystems.net", "dlp_ratchet": "public",
                     "recipient_is_external": False, "body_length": 50}, "ALLOW"),
    ("send_email", {"to": "x@gmail.com", "dlp_ratchet": "public",
                     "recipient_is_external": True, "body_length": 2500}, "DENY"),
    # ^ ESCALATE at the policy level, but with no approval_resolver wired
    # into this standalone test's HostSession, it fails closed to DENY
    # (reason: approval_denied) -- confirmed real behaviour, not a bug; see
    # docs/implementation-notes.md.
]


def main() -> None:
    control = AgentControl.from_path(MANIFEST_PATH)
    session = HostSession(control, agent_id="finance-assistant-sample", session_id="test-session")

    failures = 0
    for tool_name, args, expected in TESTS:
        result = session.pre_tool_call(tool_name=tool_name, args=args)
        actual = result.verdict.decision.name
        status = "PASS" if actual == expected else "FAIL"
        if status == "FAIL":
            failures += 1
        print(f"{status}: {tool_name}({args}) -> {actual} (expected {expected}), "
              f"reason={result.verdict.reason}")

    print()
    if failures:
        print(f"{failures} test(s) FAILED.")
        raise SystemExit(1)
    print("All real ACS/Rego policy tests passed.")


if __name__ == "__main__":
    main()
