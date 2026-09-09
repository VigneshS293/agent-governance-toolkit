# AGT runtime features — what to show on a dashboard

This is the corrected, complete list of Agent Governance Toolkit (AGT) runtime
features relevant to a monitoring dashboard, each with its official name,
purpose, why it matters, and a sample of the actual data returned. Sourced
from the official docs at https://microsoft.github.io/agent-governance-toolkit/
and cross-checked against project source where the docs site doesn't spell
out exact field names.

Two data-access paths exist for all of this, and they are not interchangeable:

| | OpenTelemetry (`enable_otel()`) | Native REST / query APIs |
|---|---|---|
| Shape | Aggregated events/metrics (counters, histograms) | Live state snapshots (objects, rows) |
| Answers | "What happened, how often, over time?" | "What is true right now?" |
| Content | Redacted — no raw prompts, tool args, model output, secrets | Richer — audit entries carry real action/resource/outcome data |
| Source | [`tutorials/40-otel-observability/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/40-otel-observability/) | [`packages/agent-hypervisor/`](https://microsoft.github.io/agent-governance-toolkit/packages/agent-hypervisor/), [`packages/agent-sre/`](https://microsoft.github.io/agent-governance-toolkit/packages/agent-sre/), [`tutorials/04-audit-and-compliance/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/04-audit-and-compliance/) |

Neither path is optional or automatic — both must be explicitly wired into
the agent's code. An agent with neither configured is invisible to any
dashboard, the same way an agent absent from Defender's inventory is a real,
reportable gap rather than "clean."

---

## 1. Runtime Status

**Purpose:** Whether the agent is currently running, restricted, stopped, or unhealthy.

**Why needed:** Distinct from Reliability/SLO below — this answers "is it even
active right now," not "how well is it performing." The first thing an
operator needs to know before anything else on this list matters.

**Source:** Hypervisor session state — [`packages/agent-hypervisor/`](https://microsoft.github.io/agent-governance-toolkit/packages/agent-hypervisor/)

**Sample data:**
```
agent_id: "agent-fin-report-07"
session_state: "active"        # active | restricted | terminated | unhealthy
ring: 1
last_heartbeat: "2026-09-07T10:04:12Z"
```

---

## 2. Action / Tool Control

**Purpose:** Defines exactly which tools/actions an agent is allowed to
invoke, and enforces it before the call executes.

**Why needed:** Having a valid connection to a system (API key, OAuth scope)
is not the same as being allowed to do anything with it. This is the layer
that separates "can reach the database" from "can run `DROP TABLE`."

**Source:** Policy engine, `pre_tool_call` / `post_tool_call` intervention points.

**Sample data:**
```
tool: "send_email"        -> allowed
tool: "drop_table"        -> denied   (rule: block-destructive)
tool: "query_database"    -> allowed, arguments redacted in log
```

---

## 3. Policy Decisions

**Purpose:** The graded verdict of every policy check — not just blocked or
not, but one of `allow / deny / warn / escalate / transform`.

**Why needed:** Not every risky action deserves an outright block. Some need
a warning logged, some need human sign-off, some need the sensitive content
redacted while the call still proceeds.

**Source:** ACS core verdict model — [`tutorials/55-agent-control-specification/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/55-agent-control-specification/)

**Sample data:**
```
decision: "warn"       -> logged, action proceeds
decision: "escalate"   -> routed to human approver
decision: "transform"  -> sensitive value redacted, call proceeds with clean data
decision: "deny"       -> blocked outright
```

---

## 4. Trust & Identity

**Purpose:** Gives each agent a real, cryptographic identity (not a shared
API key) and a continuously computed trust score.

**Why needed:** "An agent did it" is not an incident report. You need to know
*which* agent, and whether it currently behaves well enough to be trusted
with sensitive actions.

**Source:** [`tutorials/02-trust-and-identity/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/02-trust-and-identity/)

**Sample data:**
```
identity: "did:mesh:agent-fin-report-07"
trust_score: 812 / 1000
components: { identity: 240/250, behavior: 180/200, network: 132/150, compliance: 260/300 }
execution_ring: 1
```

> **Caveat:** the live trust-score query endpoint is documented in source as
> a placeholder pending a later implementation epoch — treat this feature as
> "designed for" rather than "fully working today" until independently
> re-verified.

---

## 5. Agent-to-Agent Trust (Delegation)

**Purpose:** Tracks which agents delegate work to which other agents, and
enforces that permissions only ever shrink at each hop, never grow.

**Why needed:** If Agent A spins up Agent B for a subtask, B must never end
up with more access than A had. If A is later compromised or revoked, B's
inherited access must die with it automatically.

**Source:** [`tutorials/23-delegation-chains/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/23-delegation-chains/)

**Sample data:**
```
parent: "agent-A" -> child: "agent-B"
delegated_scope: ["read_invoices"]      # narrowed subset of A's scope
revoked_at: "2026-09-07T10:03:00Z"      # cascades to agent-B automatically
```

---

## 6. Execution Limits

**Purpose:** Caps on time, concurrency, resource use, and the privilege
tier ("ring") an agent is allowed to operate within.

**Why needed:** Even a fully trusted agent should not run unbounded. Limits
contain the blast radius of a bug or an attack regardless of intent.

**Source:** [`tutorials/06-execution-sandboxing/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/06-execution-sandboxing/)

**Sample data:**
```
ring: 2                              # 0 (most trusted) - 3 (fully sandboxed)
concurrent_sessions: 3 / max 5
session_timeout: "00:04:12 / 00:10:00"
rate_limit: "18 calls/min / max 20"
```

---

## 7. Human Approval

**Purpose:** Routes specifically high-risk actions to a human for sign-off
instead of an automatic allow/deny.

**Why needed:** Some actions are too consequential to leave to policy alone —
a wire transfer, a production deploy. This is the escape hatch that keeps a
person in the loop for exactly those cases.

**Source:** [`tutorials/38-approval-workflows/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/38-approval-workflows/)

**Sample data:**
```
request_id: "appr-88291"
action: "transfer_funds", amount: "$12,000"
status: "pending"
approver_channel: "Teams webhook"
timeout_behavior: "deny if no response in 15 min"   # fail-closed
```

> **Known gap:** the approval store exposes a getter for a specific
> `approval_request_id` you already know, but no documented "list all
> pending approvals" queue method — building a live approval-queue tile
> would need a thin wrapper you write yourself.

---

## 8. Kill Switch / Rate Limiting

**Purpose:** Immediate, hard termination of a misbehaving agent, plus caps
on call frequency to stop runaway loops.

**Why needed:** Detection is useless without a way to actually stop the
agent. This is the "pull the plug" mechanism, with rollback so a
half-finished multi-step action doesn't leave things in a broken state.

**Source:** [`tutorials/14-kill-switch-and-rate-limiting/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/14-kill-switch-and-rate-limiting/)

**Sample data:**
```
event: "kill_triggered"
reason: "anomalous_tool_call_rate"
rollback: "saga rollback completed, 2 steps undone"
rate_limit_hits: 4 in last 60s (limit: 3)
```

---

## 9. Reliability / SLO

**Purpose:** Tracks whether the agent is operationally healthy — meeting
uptime/latency/error-rate targets — separate from whether it is behaving
securely.

**Why needed:** A "secure" agent that constantly times out or errors is
still failing its users. This is the ops-health lens, distinct from the
governance lens above.

**Source:** [`tutorials/05-agent-reliability/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/05-agent-reliability/), [`packages/agent-sre/`](https://microsoft.github.io/agent-governance-toolkit/packages/agent-sre/)

**Sample data:**
```
slo: "success_rate"
target: 99.5%, current: 98.1%     # error budget burning fast
circuit_breaker: "OPEN"            # auto-tripped after repeated failures
anomaly_score: 3.2 sigma           # rogue-agent detector flag
```

---

## 10. Cost / Resource Governance

**Purpose:** Tracks how much money/tokens an agent is spending and stops it
before it runs away.

**Why needed:** An agent stuck in a retry loop, or repeatedly calling an
expensive model, can burn budget silently. This catches it in real time
instead of on next month's invoice.

**Source:** [`tutorials/51-cost-governance/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/51-cost-governance/), [`tutorials/24-cost-and-token-budgets/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/24-cost-and-token-budgets/)

**Sample data:**
```
agent_id: "agent-fin-report-07"
budget_usd: 50.00
spent_usd: 42.75
threshold_hit: "85%"     -> auto-throttle triggered
threshold_hit: "95%"     -> kill-switch triggered
```

---

## 11. Runtime Audit Trail

**Purpose:** A tamper-evident, permanent record of exactly what happened,
what policy evaluated it, and why it was allowed or denied.

**Why needed:** This is what gets handed to an auditor or regulator — not a
log line that could have been edited after the fact, but a hash-chained
record that can be cryptographically proven unaltered.

**Source:** [`tutorials/04-audit-and-compliance/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/04-audit-and-compliance/)

**Sample data:**
```
entry_id: "audit-45231"
agent_did: "did:mesh:agent-fin-report-07"
action: "query_database", outcome: "denied"
policy_rule: "block-destructive"
entry_hash: "sha256:9af...", previous_hash: "sha256:31e..."
```

---

## 12. Violations

**Purpose:** A rollup of which governance rules were actually broken, across
an agent or a fleet.

**Why needed:** "What happened" (Audit Trail) and "which rules were broken"
(Violations) are different questions — this is a filtered lens over the
audit trail plus circuit-breaker trip events, not a separate data source of
its own.

**Source:** Filtered view over [`tutorials/04-audit-and-compliance/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/04-audit-and-compliance/) (`event_type = policy_violation`) and [`packages/agent-sre/`](https://microsoft.github.io/agent-governance-toolkit/packages/agent-sre/) circuit-breaker state.

**Sample data:**
```
agent_id: "agent-fin-report-07"
violation_type: "policy_violation"
rule: "block-destructive"
count_last_24h: 3
circuit_breaker_trips: 1
```

---

## 13. MCP Governance (Live Gateway)

**Purpose:** Intercepts Model Context Protocol tool calls in real time and
scans responses for leaked credentials/PII before they reach the agent.

**Why needed:** Action/Tool Control (#2) governs generic tool calls; this is
specific to the MCP protocol layer — tool descriptions, server identity, and
response content, which carry their own attack surface (poisoned tool
descriptions, hidden instructions, typosquatted servers).

**Source:** [`tutorials/07-mcp-security-gateway/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/07-mcp-security-gateway/)

**Sample data:**
```
mcp_server: "finance-tools-server"
tool_call: "get_account_balance"
decision: "allowed"
response_scan: "clean"          # or: "credential_leak_detected -> redacted"
```

---

## 14. Prompt Injection / Adversarial Defense

**Purpose:** Detects attack patterns in the content an agent receives —
direct override attempts, role-play jailbreaks, encoding tricks, multi-turn
escalation — before that content can influence the agent's behaviour.

**Why needed:** Policy Decisions (#3) governs what the agent is allowed to
*do*; this governs what the agent is allowed to be *told*. A model can be
fully policy-compliant on paper and still get manipulated by adversarial
input if nothing inspects the input itself.

**Source:** [`tutorials/09-prompt-injection-detection/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/09-prompt-injection-detection/), [`tutorials/41-advisory-defense-in-depth/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/41-advisory-defense-in-depth/)

**Sample data:**
```
input_id: "msg-33021"
attack_pattern: "delimiter_attack"
confidence: 0.87
conversation_guardian_action: "PAUSE"   # WARN | PAUSE | BREAK | QUARANTINE
```

---

## 15. E2E Encrypted Agent Messaging

**Purpose:** Encrypts messages between agents using Signal-protocol-grade
key exchange, so message content stays confidential in transit.

**Why needed:** Distinct from Agent-to-Agent Trust (#5), which governs
*whether* one agent may act on another's behalf. This governs whether a
third party can read the conversation between two agents that are already
trusted to talk to each other.

**Source:** [`tutorials/32-e2e-encrypted-messaging/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/32-e2e-encrypted-messaging/)

**Sample data:**
```
channel_id: "sec-chan-4471"
participants: ["agent-A", "agent-B"]
encryption: "X3DH + Double Ratchet"
status: "established"
```

*(Purely cryptographic — no report or dashboard artifact by design; either
the channel is secure or the handshake fails.)*

---

## 16. A2A Conversation Policy

**Purpose:** Governs agent-to-agent dialogue itself — which skills one agent
may invoke on another, content pattern blocking, and automatic circuit-
breaking of a runaway back-and-forth exchange.

**Why needed:** Delegation (#5) governs permission scope; this governs the
*conversation* between two already-trusted agents, catching things like two
agents escalating each other into a feedback loop.

**Source:** [`tutorials/44-a2a-conversation-policy/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/44-a2a-conversation-policy/)

**Sample data:**
```
from: "agent-A", to: "agent-B"
skill_requested: "approve_transaction"
decision: "denied"           # trust score below threshold for this skill
guardian_status: "loop_detected -> conversation broken"
```

---

## 17. Intent-Based Authorization

**Purpose:** Checks whether what an agent actually did matches what it
declared it would do beforehand, and flags drift between plan and action.

**Why needed:** Policy Decisions (#3) evaluates one action in isolation;
this catches an agent that behaves fine action-by-action but is quietly
executing something different from its stated plan across a sequence of
steps.

**Source:** [`tutorials/48-intent-based-authorization/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/48-intent-based-authorization/)

**Sample data:**
```
intent_id: "intent-7734"
declared_plan: ["read_invoices", "generate_report"]
actual_actions: ["read_invoices", "generate_report", "email_external"]
drift_detected: true
response: "hard_block"        # soft_block | hard_block | re_declare
```

---

## 18. DLP Attribute Ratchets

**Purpose:** Session sensitivity can only escalate, never relax — reading
one confidential document permanently raises the session's data-sensitivity
level for everything after it.

**Why needed:** Closes the "read now, exfiltrate later" gap: an agent that
reads a confidential file in step 2 and tries to email something external in
step 9 gets blocked, even though steps 2 and 9 look unrelated in isolation.

**Source:** [`tutorials/39-dlp-attribute-ratchets/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/39-dlp-attribute-ratchets/)

**Sample data:**
```
session_id: "sess-9012"
sensitivity_ratchet: "restricted"   # public -> internal -> restricted (one-way)
triggering_action: "read_document: financials_q3.xlsx"
blocked_later: "send_email(external=true)"
```

---

## 19. Fleet-Wide Aggregate Policy

**Purpose:** Enforces limits across an entire fleet of agents at once, not
just per individual agent.

**Why needed:** Execution Limits (#6) caps one agent's concurrency/rate; this
catches the case where 10 different agents each stay within their own limit
but collectively do something dangerous — e.g. more than 3 fund transfers
across the whole fleet within 60 seconds.

**Source:** [`tutorials/49-multi-agent-policies/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/49-multi-agent-policies/)

**Sample data:**
```
constraint: "fleet_transfer_rate"
window: "60s"
aggregate_count: 4 / max 3          # breach
mode: "alert"                        # alert (non-blocking) | enforce
```

---

## 20. Compliance Attestation & Decision BOM

**Purpose:** Produces a graded compliance report (A–F) against frameworks
like OWASP ASI 2026, and can reconstruct "why was this specific action
allowed" on demand from existing audit/trust/policy data.

**Why needed:** Runtime Audit Trail (#11) proves what happened; this layer
synthesizes that history into something an auditor or regulator can
actually consume — a signed grade instead of a raw log to read line by line.

**Source:** [`tutorials/18-compliance-verification/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/18-compliance-verification/), [`tutorials/50-decision-bom/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/50-decision-bom/)

**Sample data:**
```
attestation_grade: "B+"
framework: "OWASP ASI 2026"
controls_passed: 8 / 10
decision_bom: { action: "query_database", allowed_by: "policy v2.3",
                trust_score_at_time: 812, completeness: 0.94 }
```

> **Note:** this is report/attestation-shaped, not a live-updating tile —
> it's generated on request rather than streamed continuously.

---

## Not dashboard features — build-time / CI-only (flagged, not included above)

These exist in AGT but run in your build pipeline, not on a live agent —
they produce files and CI gate results, never a runtime dashboard signal:

- **SBOM & signing** — [`tutorials/26-sbom-and-signing/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/26-sbom-and-signing/)
- **Security hardening** (Gitleaks/Dependabot/CodeQL/fuzzing) — [`tutorials/25-security-hardening/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/25-security-hardening/)
- **Shift-left CI/CD gates** — [`tutorials/45-shift-left-governance/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/45-shift-left-governance/)
- **`mcp-scan` CLI** (static MCP manifest scanning) — [`tutorials/27-mcp-scan-cli/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/27-mcp-scan-cli/)
- **`agt red-team scan`** (pre-deployment adversarial testing) — [`tutorials/47-red-team-testing/`](https://microsoft.github.io/agent-governance-toolkit/tutorials/47-red-team-testing/)

Two packages are named on the site but have no live monitoring surface either
— **Agent Marketplace** ([`packages/agent-marketplace/`](https://microsoft.github.io/agent-governance-toolkit/packages/agent-marketplace/), plugin trust scoring, a CLI tool) and **Agent Lightning** ([`packages/agent-lightning/`](https://microsoft.github.io/agent-governance-toolkit/packages/agent-lightning/), RL-training-time governance, relevant only if training models, not monitoring deployed agents).

---

## Data access: OTel vs. native APIs vs. the coming Studio API

Confirmed directly from the official docs — there are, concretely, **three**
categories of data access, not two:

1. **OpenTelemetry** (`enable_otel()`) — aggregated, redacted events/metrics
   exported to an external backend (Prometheus/Azure Monitor/Datadog). See
   the table at the top of this document.
2. **Native REST/query APIs** — Hypervisor and SRE ship real FastAPI servers;
   the audit log is a queryable in-process object. Live state, richer
   content, but per-process/in-memory — no central store across a fleet.
3. **AGT Studio Engine API** — [`studio/engine-api-contract/`](https://microsoft.github.io/agent-governance-toolkit/studio/engine-api-contract/), an
   **approved-for-implementation, not-yet-shipped** read-only API contract
   intended to be the proper dashboard interface, fronting the existing
   policy/audit/trust stores rather than adding a new data source. 11 of its
   12 endpoints are read-only (`/health`, `/policies`, `/audit/log`,
   `/trust/scores`, `/trust/graph`, `/agents`, `/decisions`, `/versions`,
   etc.); the only mutating one is `POST /policy/save`, gated to require a
   direct user action. A `WebSocket /api/v1/events` route is reserved for
   live push updates but **not implemented in v1** — so even this intended
   design currently requires polling, not subscribing.

**Practical takeaway:** nothing shipped today gives you one unified live API
across a fleet. You either export summarized signals via OTel, or query
individual agents' native APIs directly, or wait for AGT Studio's read-only
API to ship a reference implementation.

---

## Corrections from earlier drafts

- **"Deny / warn / approval / accept"** is not part of Execution Limits — it
  is the **Policy Decisions** verdict type (#3), a separate concept from the
  time/concurrency/resource caps that Execution Limits (#6) actually covers.
- **Runtime Status** (#1) and **Violations** (#12) were missing from the
  original list and are added above.
- The exact OTel identifiers `OtelMetricsTelemetrySink`, meter
  `agent_control_specification`, counters `acs_intervention_*_total`, and
  histogram `acs_intervention_duration_ms` do **not** appear on the official
  docs site (checked against `tutorials/40-otel-observability/` and
  `packages/agent-control-specification/`) — they were sourced from raw
  project code in an earlier research pass, not confirmed documentation.
  What the official OTel tutorial actually documents is `enable_otel()`
  emitting spans `agt.policy.evaluate` / `agt.approval.request` /
  `agt.trust.verify` and counters `agt.policy.evaluations` /
  `agt.policy.denials` / `agt.approval.requests` plus histogram
  `agt.policy.latency_ms`. Treat the `acs_intervention_*` names as
  unverified until confirmed independently.
