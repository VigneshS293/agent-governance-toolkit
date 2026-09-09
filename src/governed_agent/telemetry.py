"""
OTel wiring for this agent's governance pipeline.

enable_otel lives at agentmesh.governance.otel_observability.enable_otel(
service_name='agt-governance', endpoint=None) -> None -- confirmed by direct
inspection of the installed agent-governance-toolkit[full]==4.1.0 package.

The real, structured audit trail is agentmesh.governance.AuditLog, owned by
GovernancePipeline (see governance_pipeline.py) -- not this module. An
earlier version of this project had a hand-rolled hash-chained AuditLog
here; it's been removed now that the real one from agentmesh.governance is
wired in directly, so there is exactly one audit trail, not two.
"""

import json
import logging
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

OTEL_LOG_PATH = LOG_DIR / "otel.log"

logger = logging.getLogger("governed_agent")


def _try_enable_otel(service_name: str) -> str:
    """Verified against the installed agent-governance-toolkit==4.1.0 package by direct inspection."""
    try:
        from agentmesh.governance.otel_observability import enable_otel
        enable_otel(service_name=service_name)
        return "agentmesh.governance.otel_observability.enable_otel"
    except (ImportError, AttributeError):
        pass

    return "unavailable"


def init_otel(service_name: str = "finance-assistant-sample") -> None:
    file_handler = logging.FileHandler(OTEL_LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    otel_logger = logging.getLogger("governed_agent.otel")
    otel_logger.setLevel(logging.INFO)
    otel_logger.addHandler(file_handler)
    otel_logger.addHandler(logging.StreamHandler())

    result = _try_enable_otel(service_name)
    otel_logger.info(json.dumps({"event": "otel_init", "resolved_path": result}))
    if result == "unavailable":
        logger.warning(
            "No enable_otel() entry point found in the installed agent-governance-toolkit "
            "package. OTel spans/metrics will not be emitted this run -- the governance "
            "pipeline's audit log (agentmesh.governance.AuditLog) is unaffected."
        )
