"""Agent Reliability (SLOs and error budgets).

Ported from the verified reference implementation at
D:\\Agent Governance Toolkit\\agentframewokr+agt\\path5_sre_for_agents\\
reliability.py -- agent_sre's SLO/error-budget tracking, confirmed
importable in this project's own .venv.

IMPORTANT, confirmed by testing in the reference project: SLO.record_event
(good) ONLY feeds the ErrorBudget -- it does NOT call .record() on the SLI.
These are two separate tracks that must be fed independently, or
slo.evaluate() falls back to SLOStatus.UNKNOWN forever. record_call_outcome
below does both calls so this can't be gotten wrong at the call site.

Real SLOStatus values (confirmed by inspection, not guessed): HEALTHY /
WARNING / CRITICAL / EXHAUSTED / UNKNOWN.

Tracks one SLO for this agent: what fraction of governed tool calls it
processes successfully (a clean allow/deny/escalate verdict plus, if
allowed, a successful tool execution) as opposed to the tool call itself
erroring out.
"""

from __future__ import annotations

from agent_sre import SLO, ErrorBudget
from agent_sre.slo.indicators import TaskSuccessRate

SUCCESS_RATE_TARGET = 0.95


def build_reliability_slo(agent_id: str) -> SLO:
    sli = TaskSuccessRate(target=SUCCESS_RATE_TARGET, window="1h")
    budget = ErrorBudget(total=100, window_seconds=3600)
    return SLO(
        name="finance-assistant-task-success",
        indicators=[sli],
        error_budget=budget,
        agent_id=agent_id,
        description="Fraction of governed tool calls processed without a tool-call error",
    )


def record_call_outcome(slo: SLO, succeeded: bool) -> None:
    """Feed both tracks SLO.evaluate() actually depends on."""
    for sli in slo.indicators:
        sli.record(1.0 if succeeded else 0.0)
    slo.record_event(succeeded)
