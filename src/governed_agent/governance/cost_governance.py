"""Cost Governance (budget enforcement).

Ported from the verified reference implementation at
D:\\Agent Governance Toolkit\\agentframewokr+agt\\path5_sre_for_agents\\
cost_governance.py -- agent_sre's CostPerTask SLI, confirmed importable in
this project's own .venv.

A REAL BUG in agent_sre, confirmed by testing in the reference project --
do NOT use CostPerTask.compliance(): the shared SLIValue.is_good property
universally computes `value >= target`, correct for "higher is better"
metrics but BACKWARDS for "lower is better" ones like cost (a cheap call
reports is_good=False, an expensive one reports is_good=True). We still use
CostPerTask.record() for its real rolling-window history (current_value()
is unaffected by the bug), but compute our OWN over-budget check with a
plain comparison instead of trusting .compliance().

Cost per call is estimated, not metered from a real Azure OpenAI usage
response -- a small fixed-plus-per-character heuristic to keep the numbers
realistic without needing to parse a live API response.
"""

from __future__ import annotations

from agent_sre.slo.indicators import CostPerTask

COST_TARGET_USD_PER_TASK = 0.02

_BASE_COST_USD = 0.001
_COST_PER_CHAR_USD = 0.00002


def build_cost_sli() -> CostPerTask:
    return CostPerTask(target_usd=COST_TARGET_USD_PER_TASK, window="1h")


def estimate_call_cost_usd(text: str) -> float:
    """Rough cost estimate for one tool call -- proportional to argument
    text length, standing in for token-based Azure OpenAI pricing without
    requiring a live call.
    """
    return _BASE_COST_USD + _COST_PER_CHAR_USD * len(text)


def record_call_cost(sli: CostPerTask, text: str) -> float:
    cost = estimate_call_cost_usd(text)
    sli.record(cost)
    return cost


def is_within_budget(sli: CostPerTask) -> bool | None:
    """Our own correct 'lower is better' check -- do not use
    sli.compliance(), see the module docstring for why.
    """
    current = sli.current_value()
    if current is None:
        return None
    return current <= sli.target
