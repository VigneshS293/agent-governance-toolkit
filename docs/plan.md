# Plan — Governed Custom Engine Agent (local test build)

Status: **implemented** (2026-09-08). See `docs/implementation-notes.md` for
what was actually built, the real (installed-and-inspected, not guessed) AGT
and Microsoft Agent Framework APIs used, and how to run/test it locally.

## Architecture

```
Teams channel
   |
M365 Agents SDK (existing: app.py, agent.py) -- transport/channel layer, unchanged
   | (on_message handler calls into the governed agent)
Microsoft Agent Framework (MAF) -- Agent + OpenAIChatClient(Azure) + tools
   | (Function middleware intercepts every tool call)
AGT -- AgentControl / HostSession (ACS) -- pre_tool_call/post_tool_call verdicts,
       audit log, trust/identity, execution limits, kill switch, cost tracking
   |
Local console + file logs (JSON lines) -- OTel spans/metrics AND native audit records
```

MAF is the officially-documented AGT integration point (listed in AGT's framework
support table as "Native Middleware"). The M365 Agents SDK is kept exactly as-is
for Teams channel/transport duties; MAF runs *inside* its turn handler as the
governed "brain" that actually answers the user. **AGT + M365 Agents SDK as a
combination has not been independently verified against AGT's own docs in this
conversation — treat as an assumed-safe pairing (AGT's enforcement is in-process
middleware around function calls, not tied to a specific host), not a confirmed
one.**

## New project structure (under `src/`)

```
src/
  agent.py              # unchanged entry: M365 SDK turn handler, now calls governed_agent.handle()
  app.py                # unchanged (aiohttp host)
  config.py             # extended with AGT policy manifest path, log paths
  governed_agent/
    __init__.py
    maf_agent.py         # MAF Agent definition, tools, OpenAIChatClient wiring
    tools.py             # mock tools: read_invoice, query_database, send_email, drop_table (deliberately blocked)
    agt_middleware.py     # MAF FunctionInvocationContext middleware -> AGT pre/post_tool_call
    identity.py           # AGT trust/identity + execution ring setup for this agent
    telemetry.py          # OTel exporters (console/local file) + native audit log sink
  policies/
    manifest.yaml         # AGT policy rules: block-destructive, warn-on-sensitive, escalate-on-transfer, DLP ratchet
  logs/                    # gitignored -- local run output lands here
    audit.jsonl
    otel.log
requirements.txt           # + agent-framework(-core, -openai), agent-governance-toolkit[full]
```

## Scenario

A "finance assistant" in Teams with four mock tools:

- `read_invoice(id)` -- allowed, triggers a DLP sensitivity ratchet after read
- `query_database(query)` -- allowed but arguments redacted in audit log
- `send_email(to, body)` -- **denied** if attempted after a sensitivity ratchet
  with an external recipient (shows DLP + policy interplay)
- `drop_table(name)` -- **always denied** (block-destructive rule) -- demonstrates
  tool control + violations

One user turn such as "show me invoice INV-1004 and email a summary to
someone@gmail.com" naturally triggers: tool control, a policy decision
(allow/deny), a DLP ratchet, a violation record, an audit entry, and (if
repeated rapidly) rate-limit/kill-switch behaviour.

## AGT features covered (representative subset)

1. Runtime Status -- session state via `HostSession`
2. Action/Tool Control -- `pre_tool_call` gate on all four tools
3. Policy Decisions -- allow/deny/warn/transform verdicts from `manifest.yaml`
4. Trust & Identity -- static identity + trust score for this agent
6. Execution Limits -- rate limit + timeout on the session
7. Human Approval -- escalate path stubbed for `send_email` above a threshold
8. Kill Switch / Rate Limiting -- triggered by repeated denied calls
10. Cost Governance -- token/cost counter on each OpenAI call, threshold log
11. Runtime Audit Trail -- hash-chained JSONL audit log
12. Violations -- filtered view over the audit log for `policy_violation` events
18. DLP Attribute Ratchets -- invoice read -> ratchet -> later blocks external email

Skipped for this pass (need a second agent or infra this simple scenario
doesn't have): delegation chains, E2E encrypted messaging, A2A conversation
policy, fleet-wide policy, MCP live gateway, prompt injection detection,
intent-based auth, compliance attestation. Candidates to add once the basic
build is verified.

## Telemetry output

- `logs/otel.log` -- OTel spans/metrics, console/file exporter, no external
  backend needed locally.
- `logs/audit.jsonl` -- native hash-chained audit records from the ACS
  session, one line per tool-call evaluation, directly queryable/greppable --
  likely the richer source a future dashboard export would prefer.

## Open flags carried into implementation

- **OTel entry point is contradicted between sources and needs a direct
  check before it's written into code.** `docs/agt-runtime-features.md` (this
  project's own doc) states `enable_otel(service_name=...)` is real, sourced
  from `tutorials/40-otel-observability/`, emitting spans
  `agt.policy.evaluate` / `agt.approval.request` / `agt.trust.verify` and
  counters `agt.policy.evaluations` / `agt.policy.denials` /
  `agt.approval.requests` / histogram `agt.policy.latency_ms`. A background
  research pass in this conversation searched the live repo and did not find
  a literal `enable_otel(` function, and instead found OTel wired through
  submodules (`agent_sre/integrations/otel/traces.py`, `metrics.py`, etc.).
  These two claims have not been reconciled — resolve by direct repo
  inspection before writing the `telemetry.py` import, rather than assuming
  either source.
- **Package naming/install path for the Hypervisor capability is unresolved.**
  One research pass called standalone `agent-hypervisor` (PyPI v3.7.0)
  deprecated in favour of installing the full `agent-governance-toolkit[full]`
  umbrella package. A later message asserted instead that it is a
  redirect/compatibility stub pointing to a consolidated
  `agent-governance-toolkit-runtime` package. Neither claim has been directly
  confirmed by inspecting the actual PyPI page/classifiers or the package's
  own README in this conversation. Practical effect either way is the same
  (install the `[full]` umbrella package rather than the standalone one), but
  the exact reason should be verified and stated correctly in a code comment
  rather than asserted.
- `AgentControl.from_path(...)` and `HostSession(runtime, agent_id=..., session_id=...)`
  are both confirmed from the same quickstart snippet retrieved from the
  repo's `docs/quickstart.md` in this conversation -- these are the ACS entry
  points to use, not an unverified guess.
- MAF's release/GA status is ambiguous in what's been checked so far (a Beta
  trove classifier and a `--pre` install convention on one hand, a "stable"
  version number reported from a direct PyPI fetch on the other). Pin
  whatever version resolves at implementation time and flag it in
  `requirements.txt` with a comment to revisit.
- AGT's support for the Microsoft 365 Agents SDK specifically (as opposed to
  Microsoft Agent Framework) has not been verified against AGT's own docs in
  this conversation -- the pairing chosen here (MAF embedded inside the M365
  SDK's turn handler) is an architectural inference, not a documented,
  Microsoft-confirmed combination. Comment this clearly in code.

## Not in scope now

Exporting to the unified dashboard (Purview/Defender/Agent 365/Entra) -- that
dashboard already exists (see `docs/data-sources.md`, a separate project) and
is a later task once this agent's local logs are verified. This plan builds
the runtime agent and its local log output only.
