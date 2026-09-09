"""Multi-Agent Fleet Capabilities (least-privilege delegation).

Ported from the verified reference implementation at
D:\\Agent Governance Toolkit\\agentframewokr+agt\\path3_secure_agent_fleet\\
fleet_delegation.py -- agentmesh.CapabilityRegistry, confirmed real and
importable in this project's own .venv (not just the reference project's).

Fleet shape for this project:
  - finance-assistant-sample (main): full access -- read_invoice,
    query_database, send_email, drop_table (still all gated by the usual
    9-layer pipeline and policies/manifest.yaml; this registry adds an
    identity-scoped ceiling ON TOP of that, it doesn't replace it)
  - invoice-lookup-subagent: delegated ONLY invoice:read and invoice:query --
    it has no grant for email:send or db:drop at all, so
    CapabilityRegistry.check() returns False for those regardless of what
    policies/manifest.yaml would otherwise allow.

This is the real mechanism that makes "which identity called this tool"
meaningful in the audit log: a capability check is keyed on the CALLER's own
verified agent_did, not a shared credential or a hardcoded constant. See
governance_pipeline.py for where this is consulted (a new layer, before
policy evaluation) and tools.py/maf_agent.py for how the sub-agent's own
governed tool wrappers are kept deliberately narrower than the main agent's.
"""

from __future__ import annotations

from agentmesh import CapabilityGrant, CapabilityRegistry

from governed_agent.governance.spiffe_setup import FINANCE_AGENT_DID, INVOICE_LOOKUP_SUBAGENT_DID

# Maps each governed tool to the capability name that guards it.
TOOL_CAPABILITIES = {
    "read_invoice": "invoice:read",
    "query_database": "invoice:query",
    "send_email": "email:send",
    "drop_table": "db:drop",
}


def build_fleet_registry() -> CapabilityRegistry:
    """The main agent grants the sub-agent ONLY read-side invoice capabilities.

    email:send and db:drop are never granted to the sub-agent -- there is no
    line below that does so, which is the point: CapabilityRegistry.check()
    for those two capabilities will correctly return False for the
    sub-agent's DID, confirmed by direct testing (see
    docs/feature-implemented.md).
    """
    registry = CapabilityRegistry()
    registry.grant(capability="invoice:read", to_agent=INVOICE_LOOKUP_SUBAGENT_DID, from_agent=FINANCE_AGENT_DID)
    registry.grant(capability="invoice:query", to_agent=INVOICE_LOOKUP_SUBAGENT_DID, from_agent=FINANCE_AGENT_DID)
    return registry


def can_perform(registry: CapabilityRegistry, agent_did: str, tool_name: str) -> bool:
    """Whether `agent_did` may call `tool_name` at all, per the fleet's capability grants.

    The main agent (FINANCE_AGENT_DID) is treated as the fleet owner and can
    perform every governed tool -- capability grants in this module only
    ever narrow a SUB-agent's surface, they never need to grant the main
    agent anything, since it's the grantor.
    """
    if agent_did == FINANCE_AGENT_DID:
        return True
    capability = TOOL_CAPABILITIES.get(tool_name)
    if capability is None:
        return False
    return registry.check(agent_did, capability)
