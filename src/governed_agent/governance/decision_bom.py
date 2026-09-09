"""Decision BOM (audit artifacts).

Ported verbatim from the reference implementation at
D:\\Agent Governance Toolkit\\agentframewokr+agt\\path4_compliance_and_audit\\
decision_bom.py -- domain-agnostic, no invoice/finance-specific content.

AGT's real design here (per ADR-0018, "Reconstructible Decision BOM over
prebuilt") is that a Decision BOM is NOT a separate artifact type the
toolkit stores as you go -- there is no `DecisionBOM` class in the
installed package. Instead, it's RECONSTRUCTED on demand from the
tamper-evident audit chain (agentmesh.governance.AuditLog).

A "Decision BOM" here means: for a given time window (or agent), take every
audit entry -- what policy fired, what verdict it produced, when, for whom
-- and export it as one reviewable document, with the merkle_root proving
none of those entries were altered after the fact.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from agentmesh.governance import AuditLog


def build_decision_bom(audit: AuditLog) -> dict[str, Any]:
    """Reconstruct a Decision BOM from the audit log's full export."""
    export = audit.export()
    decisions = [
        {
            "entry_id": entry["entry_id"],
            "timestamp": entry["timestamp"].isoformat() if isinstance(entry["timestamp"], datetime) else entry["timestamp"],
            "agent_did": entry["agent_did"],
            "action": entry["action"],
            "policy_decision": entry["policy_decision"],
            "matched_rule": entry.get("matched_rule") or (entry.get("data") or {}).get("matched_rule"),
            "outcome": entry["outcome"],
            "data": entry["data"],
        }
        for entry in export["entries"]
    ]
    return {
        "bom_generated_at": datetime.now().isoformat(),
        "merkle_root": export["merkle_root"],
        "entry_count": export["entry_count"],
        "decisions": decisions,
    }


def summarize_bom(bom: dict[str, Any]) -> str:
    """A short, human-readable summary of a Decision BOM."""
    lines = [
        f"Decision BOM ({bom['entry_count']} decisions, merkle_root={bom['merkle_root'][:16]}...)",
    ]
    for d in bom["decisions"]:
        lines.append(
            f"  [{d['timestamp']}] {d['agent_did']} -> {d['action']}: "
            f"{d['policy_decision']} (rule: {d['matched_rule'] or '-'}, outcome: {d['outcome']})"
        )
    return "\n".join(lines)
