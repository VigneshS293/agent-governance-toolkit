"""Compliance Verification (SOC2/GDPR, per the real installed engine).

Ported from the verified reference implementation at
D:\\Agent Governance Toolkit\\agentframewokr+agt\\path4_compliance_and_audit\\
compliance_check.py -- agentmesh.ComplianceEngine, confirmed importable in
this project's own .venv.

Real ComplianceFramework enum values (confirmed by inspection in the
reference project, not guessed): EU_AI_ACT, SOC2, HIPAA, GDPR -- OWASP/NIST
mappings exist only as prose on the AGT docs site, not as enum values in
this installed version, so this project uses what's actually runnable.

An invoice read or a query against the invoice database carries personal
data (a customer's identity tied to a financial record), so GDPR's consent
check is the one that can actually fire here: if a read/query is processed
without recorded consent, that's a real (if illustrative) GDPR-ART22
violation this engine will surface. Every read_invoice/query_database call
in this project is an "automated_decision" in the same sense the reference
project's expense approvals are -- the agent acts on customer financial
data without a human confirming each individual read.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agentmesh import ComplianceEngine, ComplianceFramework, ComplianceReport
from agentmesh.governance.compliance import ComplianceViolation

FRAMEWORKS = [ComplianceFramework.SOC2, ComplianceFramework.GDPR]


def build_engine() -> ComplianceEngine:
    return ComplianceEngine(frameworks=FRAMEWORKS)


def check_data_access(
    engine: ComplianceEngine, agent_did: str, action_type: str, context: dict, consent_verified: bool,
) -> list[ComplianceViolation]:
    """Check one governed data-access call (read_invoice, query_database)
    against the compliance engine.

    consent_verified models whether the customer has an on-file consent
    record for their financial data being processed by an automated agent
    -- a real-world prerequisite this project's mock data doesn't track, so
    it's passed in explicitly rather than always assumed true.
    """
    return engine.check_compliance(
        agent_did=agent_did,
        action_type=action_type,
        context={**context, "personal_data": True, "consent_verified": consent_verified},
    )


def generate_gdpr_report(engine: ComplianceEngine, agent_ids: list[str]) -> ComplianceReport:
    now = datetime.now(timezone.utc)
    return engine.generate_report(
        framework=ComplianceFramework.GDPR,
        period_start=now - timedelta(days=1),
        period_end=now,
        agent_ids=agent_ids,
    )
