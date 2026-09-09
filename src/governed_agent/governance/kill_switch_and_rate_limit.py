"""Kill Switch & Rate Limiting (emergency controls).

Ported from the verified reference implementation at
D:\\Agent Governance Toolkit\\agentframewokr+agt\\path5_sre_for_agents\\
kill_switch_and_rate_limit.py. Two independent, real mechanisms, confirmed
importable in this project's own .venv:

1. Kill switch -- agent_os.circuit_breaker.CircuitBreaker. After
   failure_threshold consecutive failures, the circuit trips OPEN and every
   subsequent call is rejected immediately with CircuitBreakerOpen --
   without even attempting the underlying call.

2. Rate limiting -- agent_os.MCPSlidingRateLimiter. max_calls_per_window
   allows exactly that many calls per window, then rejects further calls,
   with get_remaining_budget() reporting the correct remaining count.

Applied to every governed tool call in this project (see
governance_pipeline.py): the rate limiter caps how many tool calls one
agent can make per minute (abuse protection), and the circuit breaker trips
if the underlying tool call itself starts failing repeatedly (dependency
protection). These guard against different failure modes and are
deliberately kept separate rather than merged into one mechanism.
"""

from __future__ import annotations

from agent_os import MCPSlidingRateLimiter
from agent_os.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpen, CircuitState

RATE_LIMIT_MAX_CALLS = 5
RATE_LIMIT_WINDOW_SECONDS = 60.0

CIRCUIT_FAILURE_THRESHOLD = 3
CIRCUIT_RECOVERY_TIMEOUT_SECONDS = 30.0


def build_rate_limiter() -> MCPSlidingRateLimiter:
    return MCPSlidingRateLimiter(
        max_calls_per_window=RATE_LIMIT_MAX_CALLS,
        window_size=RATE_LIMIT_WINDOW_SECONDS,
    )


def build_circuit_breaker(agent_id: str) -> CircuitBreaker:
    config = CircuitBreakerConfig(
        failure_threshold=CIRCUIT_FAILURE_THRESHOLD,
        recovery_timeout_seconds=CIRCUIT_RECOVERY_TIMEOUT_SECONDS,
    )
    return CircuitBreaker(agent_id=agent_id, config=config)
