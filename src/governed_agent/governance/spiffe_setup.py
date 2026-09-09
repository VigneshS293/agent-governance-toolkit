"""Trust & Identity (agent identity with SPIFFE) -- now a real two-agent fleet.

Ported from the verified reference implementation at
D:\\Agent Governance Toolkit\\agentframewokr+agt\\path3_secure_agent_fleet\\
identity\\spiffe_setup.py -- confirmed importable in this project's own
.venv too (agent-governance-toolkit[full] installs agentmesh.identity.spiffe
either way):

    registry = SPIFFERegistry(trust_domain=...)
    identity = registry.register(agent_did=..., agent_name=...)
    svid = registry.issue_svid(agent_did)
    registry.validate_svid(svid)

No real Certificate Authority or PKI is involved -- SPIFFERegistry issues a
local, self-contained X.509 SVID for dev/test purposes, matching this
project's local-test scope.

Extended with a second, real identity: INVOICE_LOOKUP_SUBAGENT_DID. An
earlier version of this project had exactly one identity (FINANCE_AGENT_DID)
hardcoded as the sole caller of every tool -- every audit.jsonl entry showed
the same agent_did regardless of which tool ran, so "which identity called
this tool" could never actually be answered from the log; it was always the
same answer. This sub-agent is registered in the SAME registry (a fleet
shares one registry, per the reference project's own pattern) and is granted
a narrow capability set via capability_grants.py -- see that module and
governance_pipeline.py for how a caller's identity is now threaded through
every layer instead of a single hardcoded constant.
"""

from __future__ import annotations

from agentmesh.identity.spiffe import SPIFFERegistry, SVID

TRUST_DOMAIN = "quadrasystems.local"

FINANCE_AGENT_DID = "did:agentmesh:finance-assistant-sample"
INVOICE_LOOKUP_SUBAGENT_DID = "did:agentmesh:invoice-lookup-subagent"


def build_registry() -> SPIFFERegistry:
    registry = SPIFFERegistry(trust_domain=TRUST_DOMAIN)
    registry.register(agent_did=FINANCE_AGENT_DID, agent_name="finance-assistant-sample")
    registry.register(agent_did=INVOICE_LOOKUP_SUBAGENT_DID, agent_name="invoice-lookup-subagent")
    return registry


def issue_and_validate(registry: SPIFFERegistry, agent_did: str) -> SVID:
    svid = registry.issue_svid(agent_did)
    if svid is None:
        raise RuntimeError(f"No identity registered for {agent_did}")
    if not registry.validate_svid(svid):
        raise RuntimeError(f"SVID validation failed for {agent_did}")
    return svid
