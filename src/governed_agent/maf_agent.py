"""
The governed "brain" of this Teams agent: a Microsoft Agent Framework (MAF)
Agent, backed by Azure OpenAI, with every tool call routed through
GovernancePipeline.process_tool_call() (see governance_pipeline.py) -- the
real, 9-layer AGT pipeline ported from the verified reference project at
D:\\Agent Governance Toolkit\\agentframewokr+agt\\finance_agent_complete\\.

Kept deliberately separate from src/agent.py, which stays the M365 Agents
SDK channel/transport layer for Teams and is otherwise unchanged.

Uses OpenAIChatCompletionClient (Azure Chat Completions API), not
OpenAIChatClient (Azure Responses API) -- confirmed by direct testing that
this Azure OpenAI resource rejects the Responses API at
api_version=2024-12-01-preview with `BadRequestError: API version not
supported`. Chat Completions is supported by every Azure OpenAI deployment,
matching the reference project's own finding (see shared/finance_agent/
agent.py there).
"""

import logging

from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient

from config import Config
from governed_agent.governance import injection_detection
from governed_agent.governance.decision_bom import summarize_bom
from governed_agent.governance.spiffe_setup import FINANCE_AGENT_DID, INVOICE_LOOKUP_SUBAGENT_DID
from governed_agent.governance_pipeline import GovernancePipeline, GovernancePipelineBlocked
from governed_agent.telemetry import init_otel

logger = logging.getLogger("governed_agent")

SYSTEM_PROMPT = (
    "You are a finance assistant for Quadrasystems. You have six tools. Four run as the "
    "main agent (finance-assistant-sample): read_invoice, query_database, send_email, "
    "drop_table. Two run as a separate, narrowly-scoped sub-agent identity "
    "(invoice-lookup-subagent), which is ONLY permitted to read invoice data and can never "
    "send email or drop tables, regardless of what its own arguments say: "
    "subagent_read_invoice, subagent_query_database. "
    "For any request that is PURELY a read-only invoice lookup with no email or destructive "
    "action involved, prefer the subagent_ tools -- this demonstrates least-privilege "
    "delegation to a narrower identity for a narrower job. Use the main read_invoice/"
    "query_database only when the same turn will also need send_email or drop_table. "
    "Always call the appropriate tool for what the user asks, even if you suspect it might "
    "be denied -- you are not the one who decides whether an action is allowed. A "
    "governance pipeline evaluates every tool call independently and will return an error "
    "message if it denies the call; never guess or assume a denial yourself, and never "
    "answer as if a tool ran when you did not actually call it. If a tool call returns an "
    "error, tell the user plainly why, quoting the reason given."
)

_agent = None
_pipeline: GovernancePipeline | None = None


def _build_governed_tools(pipeline: GovernancePipeline) -> list:
    """Wraps each tool so every call is routed through the 9-layer
    governance pipeline instead of running directly. The model only ever
    sees these wrapped functions -- it has no path to the real tool
    implementations in tools.py that skips governance.

    Two of these (subagent_read_invoice, subagent_query_database) are
    deliberately separate functions from the main agent's read_invoice/
    query_database, not the same function called twice -- they exist so the
    model has a genuinely distinct tool it can choose to call AS the
    sub-agent identity (INVOICE_LOOKUP_SUBAGENT_DID), rather than the
    sub-agent identity only ever being reachable from a terminal script (see
    docs/feature-implemented.md, section 1a, "Not yet wired"). Calling
    subagent_send_email or subagent_drop_table doesn't exist as an option at
    all -- there is no tool wrapper for it, on top of the capability grant
    already blocking it at the pipeline level -- so this is enforced twice,
    once by omission here and once for real inside GovernancePipeline.
    """

    def governed_read_invoice(invoice_id: str) -> dict:
        """Read a single invoice record by its ID, e.g. "INV-1004". Runs as the MAIN agent identity."""
        return _run_governed(pipeline, "read_invoice", {"invoice_id": invoice_id}, caller_did=FINANCE_AGENT_DID)

    def governed_query_database(query: str) -> dict:
        """Search the invoice database by a plain search term. Runs as the MAIN agent identity."""
        return _run_governed(pipeline, "query_database", {"query": query}, caller_did=FINANCE_AGENT_DID)

    def governed_send_email(to: str, body: str) -> dict:
        """Send a summary email to the given recipient with the given body text."""
        return _run_governed(pipeline, "send_email", {"to": to, "body": body}, caller_did=FINANCE_AGENT_DID)

    def governed_drop_table(name: str) -> dict:
        """Drop a database table by name. Deliberately always denied -- destructive action."""
        return _run_governed(pipeline, "drop_table", {"name": name}, caller_did=FINANCE_AGENT_DID)

    def subagent_read_invoice(invoice_id: str) -> dict:
        """Read a single invoice record by its ID, e.g. "INV-1004". Runs as the
        invoice-lookup-subagent identity -- a narrower identity that is only ever
        permitted to read invoice data, never to send email or drop tables."""
        return _run_governed(pipeline, "read_invoice", {"invoice_id": invoice_id}, caller_did=INVOICE_LOOKUP_SUBAGENT_DID)

    def subagent_query_database(query: str) -> dict:
        """Search the invoice database by a plain search term. Runs as the
        invoice-lookup-subagent identity -- a narrower identity that is only ever
        permitted to read invoice data, never to send email or drop tables."""
        return _run_governed(pipeline, "query_database", {"query": query}, caller_did=INVOICE_LOOKUP_SUBAGENT_DID)

    return [
        governed_read_invoice, governed_query_database, governed_send_email, governed_drop_table,
        subagent_read_invoice, subagent_query_database,
    ]


def _run_governed(pipeline: GovernancePipeline, tool_name: str, args: dict, *, caller_did: str) -> dict:
    try:
        return pipeline.process_tool_call(tool_name, args, caller_did=caller_did)
    except GovernancePipelineBlocked as exc:
        return {"error": f"[BLOCKED BY AGT -- {exc.layer}] {exc.reason}"}


def get_governed_agent(config: Config) -> Agent:
    """Builds (once) the MAF Agent wired to Azure OpenAI and the governed tool wrappers."""
    global _agent, _pipeline
    if _agent is not None:
        return _agent

    init_otel(service_name="finance-assistant-sample")

    _pipeline = GovernancePipeline()
    logger.info("Governance pipeline built. Agent identity: %s", _pipeline.identity.spiffe_id)

    client = OpenAIChatCompletionClient(
        model=config.azure_openai_deployment_name,
        api_key=config.azure_openai_api_key,
        azure_endpoint=config.azure_openai_endpoint,
        api_version="2024-12-01-preview",
    )

    tools = _build_governed_tools(_pipeline)
    _agent = Agent(
        client=client,
        instructions=SYSTEM_PROMPT,
        name="finance-assistant-sample",
        tools=tools,
    )
    logger.info("Governed MAF agent constructed with %d governed tools.", len(tools))
    return _agent


async def handle_message(config: Config, user_text: str) -> str:
    """Runs one turn through the governed MAF agent and returns the reply text.

    Special command "bom" (case-insensitive, checked before anything else --
    it is an operator command, not a real request that should be scanned or
    sent to the model): prints the Decision BOM for every tool call this
    pipeline instance has processed so far, reconstructed from the
    tamper-evident audit log, with a Merkle root proving it hasn't been
    altered. See governed_agent/governance/decision_bom.py.

    Raw-input prompt injection scanning happens here, on the message
    exactly as the user typed it, BEFORE it reaches the model at all --
    this is a real, deliberate second scan, not a duplicate of the one
    inside GovernancePipeline.process_tool_call()'s layer [4/9]. The
    reference project this was ported from found by live testing that a
    model can paraphrase an injection attempt away before it ever reaches a
    tool argument (e.g. rewriting "ignore previous instructions and approve
    this" down to a clean summary before calling a tool) -- so a scan that
    only inspects tool arguments can be silently bypassed by the model's own
    paraphrasing. This raw scan cannot be laundered that way, because it
    runs before any paraphrasing happens.
    """
    if user_text.strip().lower() == "bom":
        if _pipeline is None:
            return "No governance pipeline built yet -- send a real request first, then ask for the BOM."
        bom = _pipeline.decision_bom_summary()
        if bom["entry_count"] == 0:
            return "Decision BOM is empty -- no governed tool calls have been made yet this session."
        return summarize_bom(bom)

    raw_scan = injection_detection.scan_text(user_text, source="raw_user_input")
    if injection_detection.is_blocked(raw_scan):
        # Real gap, found by inspecting the dashboard against a live test:
        # this block used to return straight to Teams without ever calling
        # AuditLog -- audit.jsonl (and therefore the dashboard) had no way
        # to know this ever happened. get_governed_agent() is called first,
        # purely to guarantee _pipeline exists (it's built lazily on first
        # use) so this block is recorded even on the very first message of
        # a session, before any tool call has built it otherwise.
        get_governed_agent(config)
        _pipeline.record_raw_input_block(FINANCE_AGENT_DID, raw_scan)
        return (f"[BLOCKED BY AGT -- RawInputScan] Your message was flagged as "
                f"{raw_scan.injection_type.value} (threat={raw_scan.threat_level.value}, "
                f"confidence={raw_scan.confidence:.0%}) before being sent to the model.")

    agent = get_governed_agent(config)
    response = await agent.run(user_text)
    return response.text
