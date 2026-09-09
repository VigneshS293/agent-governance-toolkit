# CEA-Agt-unified -- Governed Finance Assistant (Custom Engine Agent)

A Microsoft Teams finance assistant built as a **Custom Engine Agent** on the
Microsoft 365 Agents SDK, with its reasoning handled by the **Microsoft Agent
Framework (MAF)** and every tool call routed through a real, 9-layer
governance pipeline built from the **Agent Governance Toolkit (AGT)**.

This is a sample/demo project for Quadrasystems.net India Private Limited,
used to demonstrate what AGT-based governance looks like end-to-end against a
live agent, not a mocked one.

## What this project actually does

The agent answers finance questions (invoice lookups, database search, email
summaries) for a small fictional set of customers. What makes it a
*governed* agent is that no tool call reaches its real implementation
directly -- every call passes through `GovernancePipeline.process_tool_call()`
first, which enforces, in order:

1. **Identity** -- SPIFFE-based agent identity (SPIFFE Verifiable Identity Document)
2. **Capability** -- least-privilege grants per agent identity
3. **Rate limiting** -- sliding-window call limits
4. **Kill switch** -- circuit breaker
5. **Prompt injection detection** -- scans tool arguments (and, separately, the
   raw user message before it ever reaches the model)
6. **Policy evaluation** -- YAML-defined allow/warn/deny/require-approval rules
7. **Approval / escalation** -- human-approval-style gating for risky actions
8. **Compliance** -- rule-based compliance checks (e.g. consent-on-file)
9. **Tamper-evident audit logging, cost governance, reliability (SLO), and
   trust scoring**

The project also demonstrates **multi-agent identity**: a main agent
(`finance-assistant-sample`, full tool access) and a narrower sub-agent
(`invoice-lookup-subagent`, read-only invoice access only) sharing one SPIFFE
registry, so `logs/audit.jsonl` shows exactly which identity performed each
action.

A full, source-verified feature-by-feature breakdown (including what is
real vs. still a local stand-in) lives in
[docs/feature-implemented.md](docs/feature-implemented.md).

## Project structure

```
src/
  app.py                        Teams channel entry point (aiohttp server, M365 Agents SDK)
  agent.py                      M365 Agents SDK transport/channel layer for Teams
  config.py                     Reads Azure OpenAI settings from environment
  governed_agent/
    maf_agent.py                MAF "brain": Azure OpenAI agent + governed tool wrappers
    governance_pipeline.py      The real 9-layer GovernancePipeline
    tools.py                    Underlying (ungoverned) tool implementations
    verify_audit.py             CLI to verify the audit log's hash chain
    governance/
      spiffe_setup.py           Agent identities (main + sub-agent)
      capability_grants.py      Least-privilege capability grants
      trust_scoring.py          Trust score tracking
      decision_bom.py           Decision "Bill of Materials" summary
      injection_detection.py    Raw-message prompt injection scan
policies/
  manifest.yaml                 Policy rules (allow/warn/deny/require_approval)
  acs/                          Optional Rego/ACS alternative policy engine (not wired live)
dashboard/
  server.py                     Local dashboard backend (reads logs/audit.jsonl)
  index.html                    Single-page AGT Activity Dashboard (frontend)
logs/
  audit.jsonl                   Tamper-evident, hash-chained governance audit log
docs/
  feature-implemented.md        Full feature audit against AGT's tutorial catalog
  implementation-notes.md       Log of real bugs found and fixed during development
```

## Prerequisites

- Python 3.11+ (a `.venv` is already present in this folder)
- An Azure OpenAI resource with a Chat Completions-capable deployment
- Microsoft 365 Agents Toolkit (VS Code extension) if you want to run/debug
  the agent inside Teams via F5; not required to test the governance pipeline
  or dashboard on their own

## One-time setup

```powershell
# From the project root
.venv\Scripts\Activate.ps1
pip install -r src\requirements.txt
```

Set your Azure OpenAI credentials via the Agents Toolkit's env files, which
are gitignored and never committed. Copy the provided examples and fill in
real values:

```powershell
Copy-Item env\.env.local.user.example env\.env.local.user
Copy-Item env\.env.dev.user.example env\.env.dev.user
```

Then edit `env\.env.local.user` (used for local/Playground runs) and set:

```
SECRET_AZURE_OPENAI_API_KEY=<your key>
AZURE_OPENAI_ENDPOINT='<your endpoint>'
AZURE_OPENAI_DEPLOYMENT_NAME='<your chat completions deployment name>'
```

## Running the backend (the Teams agent)

**Option A -- Microsoft 365 Agents Toolkit (recommended for testing in Teams):**
Open this folder in VS Code with the Agents Toolkit extension installed, and
press **F5** (or use the "Debug in Microsoft 365 Agents Playground" /
"Debug in Teams" launch configuration). This starts `src/app.py` and opens
the Agents Playground or Teams for you to chat with the agent directly.

**Option B -- run the aiohttp server directly:**

```powershell
.venv\Scripts\Activate.ps1
cd src
python app.py
```

This starts the agent's messaging endpoint at `http://localhost:3978/api/messages`.
On its own (without the Agents Toolkit/Playground driving it) this endpoint
expects properly authenticated Bot Framework requests, so for local
chat-only testing Option A is simpler.

Every tool call made during a conversation is written to `logs/audit.jsonl`.
You can verify the audit log's tamper-evident hash chain at any time with:

```powershell
python src\governed_agent\verify_audit.py
```

## Running the frontend (AGT Activity Dashboard)

The dashboard is a separate, local, read-only viewer for `logs/audit.jsonl`.
It does not need the Teams agent to be running at the same moment it starts,
but it has nothing to show until the agent has processed at least one
message.

```powershell
.venv\Scripts\Activate.ps1
python dashboard\server.py
```

Then open your browser to:

**http://localhost:8787**

The page auto-refreshes every 4 seconds, reading fresh from
`logs/audit.jsonl` on every request (it is not a live stream/websocket) and
re-verifying the hash chain each time. It shows one card per governed tool
call: which identity acted, which policy decision was made (allow / warn /
deny / escalate), compliance and prompt-injection details when present,
estimated cost, SLO status, and trust score.

If you ever see stale or missing data on the dashboard, confirm only one
`dashboard/server.py` process is running -- starting a second one on the
same port is the most common cause of confusing results, and the server
will now fail loudly with an `OSError` instead of silently coexisting.

To use a different port: set `DASHBOARD_PORT` before starting the server,
e.g. `$env:DASHBOARD_PORT="8888"; python dashboard\server.py`.

## Further reading

- [docs/feature-implemented.md](docs/feature-implemented.md) -- full feature
  audit, cross-checked against AGT's own tutorial catalogue, including what
  is and is not implemented, and how to test each feature
- [docs/implementation-notes.md](docs/implementation-notes.md) -- running log
  of real issues found and fixed during development
