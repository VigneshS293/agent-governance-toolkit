# Data sources — where every number on the dashboard comes from

This is the map from "what you see on screen" back to "the exact Graph call
that produced it." Everything here is derived from the actual fetchers in
[`src/hooks/useAgent365Graph.js`](../src/hooks/useAgent365Graph.js), the
capability/scope table in [`src/msalConfig.js`](../src/msalConfig.js), and the
derivation logic in [`src/domain/`](../src/domain/). If a number on the
dashboard looks wrong, this document tells you which of those three files to
open first.

## How to read this document

Every fetch is one of eleven **capabilities**. Each capability is:

- fetched **independently** of the other ten — one missing consent or one
  failing endpoint degrades exactly one capability, never the whole dashboard
- gated by its own **scope**, requested **incrementally** (not at sign-in),
  so declining one consent prompt costs one capability, not the app
- reported in the **"Partial coverage"** banner at the top of every view when
  it fails, with the reason (missing consent vs. a real error) spelled out

Four scopes are requested at sign-in and are **not optional** — declining
them means no dashboard at all:

```
User.Read
AgentIdentity.Read.All
Application.Read.All
Directory.Read.All
```

(`Application.Read.All` and `Directory.Read.All` are required up front because
the core agent registry call and the delegated-grants call both need them
immediately; the *capability* wrapper around them still exists so a later
failure reports cleanly rather than crashing the refresh.)

---

## 1. Core registry — the one non-optional fetch

| | |
|---|---|
| **Endpoint** | `GET /v1.0/servicePrincipals/microsoft.graph.agentIdentity?$top=100` |
| **Scope** | `AgentIdentity.Read.All` (required at sign-in) |
| **Fetcher** | `fetchAgentIdentities` |
| **Fallback** | none — if this fails, the dashboard shows nothing |

This is the list of agents. Every other capability below either enriches one
of these identities or fails silently for it. Paged via `callGraphPaged`
(follows `@odata.nextLink`, capped at 10 pages, reports `truncated` if more
remain).

**Exact fields consumed:** `id`, `displayName`, `tags`, `agentIdentityBlueprintId`,
`accountEnabled`, `createdDateTime`.

---

## 2. Capability table

Each row below is one entry in `CAPABILITIES` (`msalConfig.js`) and one
fetcher in `useAgent365Graph.js`. "Pillars" is which status column(s) on the
Agents view this feeds — empty means it feeds detail/drill-down views only,
not a pillar's red/amber/green.

| Capability | Endpoint | Scope | Pillars | Preview? |
|---|---|---|---|---|
| `agentAttributes` | `GET .../agentIdentity?$select=id,tags,customSecurityAttributes&$top=100` | `CustomSecAttributeAssignment.Read.All` | — | No |
| `agentsInfo` | `POST /security/runHuntingQuery` (KQL, see §3) | `ThreatHunting.Read.All` | observe, govern, dlp | No |
| `mcpActivity` | `POST /security/runHuntingQuery` (KQL, see §4) | `ThreatHunting.Read.All` | — | **Yes** |
| `agentAccess` | `GET .../agentIdentity?$select=id,displayName&$expand=appRoleAssignments` + a second call `&$expand=owners` | `Application.Read.All` | govern | No |
| `oauthGrants` | `GET /oauth2PermissionGrants?$top=999` | `Directory.Read.All` | govern | No |
| `blueprints` | `GET /applications/microsoft.graph.agentIdentityBlueprint?$select=...&$top=100` | `AgentIdentityBlueprint.Read.All` | — | No |
| `incidents` | `GET /security/incidents?$filter=...&$expand=alerts&$top=50` | `SecurityIncident.Read.All` | secure | No |
| `roleAssignments` | `GET /roleManagement/directory/roleAssignments` | `RoleManagement.Read.Directory` | govern | No |
| `sensitivityLabels` | `GET /security/dataSecurityAndGovernance/sensitivityLabels` | `SensitivityLabel.Read` | dlp | No (fallback is) |
| `conditionalAccess` | `GET /identity/conditionalAccess/policies` | `Policy.Read.All` | govern | No |
| `riskyAgents` | `GET /beta/identityProtection/riskyAgents` | `IdentityRiskyAgent.Read.All` | secure | **Yes** |

Two more Graph calls exist purely to **resolve a GUID to a name** for display
— they don't feed a pillar or a capability of their own, they piggyback on an
existing capability's scope:

| Purpose | Endpoint | Reuses scope of |
|---|---|---|
| Directory role name (was a raw GUID) | `GET /roleManagement/directory/roleDefinitions?$select=id,displayName` | `roleAssignments` |
| App role name (was a raw GUID) | `GET /servicePrincipals/{resourceId}?$select=id,appRoles`, one call per distinct resource SP referenced | `agentAccess` |

### Fallback paths

Only one capability has an actual fallback (a different endpoint, not just a
retry):

**`sensitivityLabels`** — the tenant-wide GA endpoint
(`/v1.0/security/dataSecurityAndGovernance/sensitivityLabels`) internally does
an on-behalf-of exchange to the Office sync service. In some tenants Entra
rejects that (`AADSTS500301`) and Graph returns a 500 — a service-side
failure. The fallback is a **per-user, beta-only** endpoint:

```
GET /beta/me/security/informationProtection/sensitivityLabels
```

requiring a *different* scope (`InformationProtectionPolicy.Read`, its own
consent step) and returning the labels visible to the signed-in user rather
than every label in the tenant — narrower, but real. When this path is used,
the dashboard shows a blue "served from a fallback endpoint" banner.

Every other capability has no fallback: if it fails, that pillar/section
reports "unavailable" with a reason, and everything else keeps working.

---

## 3. The Defender agent inventory — `agentsInfo`

This is the single richest source on the dashboard: nearly everything in an
agent's Composition, Ownership, Tools, Models and DLP data comes from here.

**How it's fetched:** the table name and its columns are *discovered*, not
assumed — this tenant's `AgentsInfo` differs from Microsoft's published
schema (renamed columns, inconsistent `Id`/`ID` casing), and a hard-coded
`project` clause fails the whole query on one missing column.

1. Try `AgentsInfo | getschema`, then `AIAgentsInfo | getschema` if the first
   resolves to nothing (the old table name; documented as accessible until
   1 Jul 2026, but rollout is per-tenant).
2. Resolve each wanted field against whatever columns actually exist,
   case-insensitively, with known aliases (e.g. `Name` → `AgentName`,
   `Description` → `AgentDescription`).
3. Run the actual KQL query, deduplicated with `summarize arg_max(Timestamp, *)`
   when a join key and a timestamp both exist.

**Exact fields projected (canonical name ← accepted aliases):**

```
AgentId, AgentName (← Name), AgentDescription (← Description), Platform,
SourceAgentId, EntraAgentId, EntraBlueprintId, LifecycleStatus,
PublishedStatus, Availability, Owners, SharedWith, InstanceCount, Model,
DeclaredTools, DeclaredDataSources, McpServers, Guardrails, Permissions,
ObservabilityId, LastUpdatedDateTime, Version, Instructions, Capabilities,
Channels, Skills, ConnectedAgents, Memory, Triggers, Endpoints,
ToolsAuthenticationType, CreatedDateTime, LastPublishedDateTime
```

**Join to the Entra identity:** by `EntraAgentId` (primary) or `AgentId`
(secondary), case-insensitively. An agent identity with no matching row here
is "registered in Entra, not discovered by Defender" — a real, reportable gap
(the Overview's coverage number), not a bug.

**Where each field surfaces:**

| Field(s) | Shown in |
|---|---|
| `Platform`, `Model`, `Version`, `LifecycleStatus`, `PublishedStatus`, `Instructions`, `ToolsAuthenticationType`, `InstanceCount` | Agent profile → Composition tab |
| `DeclaredTools`, `McpServers`, `Endpoints`, `ConnectedAgents`, `DeclaredDataSources` | Tools & data view; Agent profile → Composition |
| `Guardrails` | Agent profile → Composition; DLP status (see §5) |
| `Owners`, `SharedWith` | Ownership view; Agent profile → Ownership tab; Govern status |
| `Availability` | DLP status (broad-availability check, see §5) |
| `Capabilities`, `Channels`, `Skills`, `Triggers`, `Memory` | Agent profile → Composition |
| `CreatedDateTime`, `LastPublishedDateTime`, `LastUpdatedDateTime` | Agent profile metadata |

All of `DeclaredTools`/`McpServers`/`Endpoints`/`ConnectedAgents`/`DeclaredDataSources`
pass through `toList()` (parses a JSON-string column into an array if needed)
and each item's display name through `summaryOf()` (extracts `type`/`name`/
`description`, including the nested OpenAI-style `{ type: 'function', function:
{ name } }` shape some platforms use) — see
[`domain/agentMapping.js`](../src/domain/agentMapping.js).

---

## 4. BYO MCP server activity — `mcpActivity` (preview)

**This is the only *observed* data source on the dashboard** — everything
else is either identity/config (Entra, Defender inventory) or declared intent.
This one is telemetry: the Agent 365 Tooling Gateway's own record of who
invoked what, on which server, and whether it succeeded.

**Table:** `CloudAppEvents` (Defender for Cloud Apps), via two `runHuntingQuery`
calls over the same `ThreatHunting.Read.All` scope as `agentsInfo` — no extra
consent needed, but reported as its own capability because a tenant can have
the agent inventory without also having this table populated.

1. **Discovery query** — every `ActionType` that contains "gateway" and
   ("tool" or "mcp"), aggregated to counts/first-seen/last-seen. This is
   deliberately *wider* than what's queried next, so a Microsoft rename during
   preview shows up as a new discovered action type instead of silently
   emptying the view.
2. **Detail query** — the documented action type (`ExecuteToolByGateway`) plus
   anything discovered that matches, capped at **2,000 rows**, ordered by
   `Timestamp desc`. If the aggregate count exceeds the sampled 2,000, that
   gap is reported as `truncated` — never hidden.

**The catch, stated plainly:** the server name, tool name and calling agent
are *not* documented columns — they live inside `RawEventData`, an
undocumented `dynamic` JSON blob. This module (`domain/mcpActivity.js`)
**searches** that payload for plausible field names rather than addressing a
fixed path, and reports which key it matched (`resolvedPaths`) so a schema
change during preview is visible on screen instead of reading as "no data."

**What this can prove vs. what it can't:** only traffic that passes *through*
the gateway appears here. An agent talking to an MCP server directly,
out-of-band, leaves nothing in this table — so an empty result here is never
evidence that MCP isn't being used, only that the gateway didn't broker it.

---

## 5. How pillar status is derived (no API call — pure logic)

The four pillar colours (Observe / Govern / Secure / DLP) on every agent row
are computed by [`domain/agentStatusRules.js`](../src/domain/agentStatusRules.js)
from the capabilities above. No additional API calls — this is business logic
over data already fetched. Thresholds here are **judgment, not verified
Microsoft guidance** — flagged in the source as needing review before this
goes in front of stakeholders.

**Observe** (`deriveObserve`) — reads Entra `accountEnabled` + Defender
`LifecycleStatus`/`PublishedStatus`:
- `risk`: identity disabled in Entra, or `LifecycleStatus` is `Blocked`/`Deleted`
- `warn`: registered in Entra but absent from Defender's inventory; `LifecycleStatus`
  is `Uninstalled`; or `PublishedStatus` is `Draft`
- `unknown`: `agentsInfo` capability unavailable

**Govern** (`deriveGovern`) — reads `roleAssignments` + `AgentsInfo.Owners` +
`conditionalAccess`:
- `risk`: holds **any** directory role assignment (treated as privileged, no threshold)
- `warn`: no named owner in `AgentsInfo.Owners`; or tenant has no *enabled*
  Conditional Access policy at all (v1.0 Conditional Access has no
  per-agent-scoping property exposed, so this can only report "does any
  policy exist," never "is this specific agent covered")
- `unknown`: none of the three sources available

**Secure** (`deriveSecure`) — reads `incidents` + `riskyAgents`:
- Incident correlation is a **heuristic**: no incident object carries a direct
  agent-principal reference, so this stringifies each incident's expanded
  `alerts` and substring-searches for the agent's id/displayName. Explicitly
  flagged in source as needing validation against real tenant incidents.
- `risk`: an open incident (`active`/`inProgress`) at `high`/`medium` severity,
  or a matching `riskyAgents` entry at `riskState: 'atRisk'` with `riskLevel`
  `high`/`medium`
- `warn`: open incident at `low`/`informational` severity, or risky-agent match at `riskLevel: 'low'`
- `unknown`: neither `incidents` nor `riskyAgents` available

**DLP** (`deriveDlp`) — reads `AgentsInfo.Guardrails`/`DeclaredDataSources`/
`Availability`/`SharedWith` + `sensitivityLabels`:
- **Important limitation, stated in source:** `Guardrails` reports **Microsoft
  Foundry guardrails only** — Copilot Studio, SharePoint and Agent Builder
  agents are protected instead by tenant-level Purview policy, which **no API
  this dashboard calls can read**. An empty `Guardrails` on a non-Foundry
  agent is expected, not a finding.
- `enforced`: has agent-level guardrails
- `ok`: no declared data sources at all
- `risk`: has declared data sources, no guardrails, and either broadly
  available (`Availability` matches `/every|all|organi[sz]ation|tenant|public/i`)
  or shared with anyone
- `partial`: has declared data sources, no guardrails, narrow audience — this
  dashboard cannot see whether Purview policy actually covers it
- `unknown`: `agentsInfo` unavailable, or no matching inventory row for this agent

---

## 6. Per-view map: what's on screen, where it comes from

| View | Primary source(s) | What it shows |
|---|---|---|
| **Overview** | all capabilities (via `available`/`diagnostics`) | Coverage (`agents.length` vs. `agentsInfo` row count — two different denominators, stated explicitly), platform breakdown, pillar tone counts. Everything renders as a skeleton, never a false "0 = clean", while a capability hasn't landed yet. |
| **Agents** (registry) | agent identities + all pillar derivations | Filter/sort/drill-down table. Every filter (platform, model, lifecycle, owner, `uses`, tone, flags, date range) is defined once in `agentFilters.js` and reused by every stat-card link, so a card's count and the list it links to can never disagree. |
| **Microsoft Entra / Defender / Purview (Source views)** | one capability's raw response, verbatim | "Show your working" — the raw material behind a pillar, so a status can be traced back to the exact Graph call. |
| **Tools & data** | `AgentsInfo.DeclaredTools`/`McpServers`/`Endpoints`/`ConnectedAgents`/`DeclaredDataSources`, cross-referenced against `mcpActivity` gateway telemetry where available | Declared surface area, ranked by how many agents declare each item. Two heuristics live here: external-reach (URL doesn't match `.microsoft.com`/`.azure.com`/localhost) and inline-credential detection (field name matches `secret`/`apikey`/`password`/`token`/`credential`) — both stated as heuristics to review, not verdicts. |
| **MCP servers** | `mcpActivity` only | Observed gateway traffic — the one telemetry (not declared-config) view. Deliberately separate from Tools & data: declared vs. observed disagreeing is the useful signal, and merging them would hide it. |
| **Permissions / Access** | `agentAccess` (app roles) + `oauthGrants` (delegated) + `roleAssignments` (directory roles) | The union of three distinct reach mechanisms — most dashboards check directory roles alone, which is the narrowest of the three. App role assignments (application permissions) matter most: they apply with no signed-in user in the loop. |
| **Blast radius** (blueprints) | `blueprints` + agent identities' `agentIdentityBlueprintId` | Which agents inherit from which security boundary, and the worst pillar status among them — a blueprint with one bad agent inside four healthy ones is not the same finding as four healthy agents, and a boundary-with-count table can't distinguish them. Explicitly does **not** claim to know how many credentials (secrets/certs) exist on the blueprint's application object — not read by this dashboard. |
| **Models & prompts** | `AgentsInfo.Model`, `Instructions` | Model spread (supply-chain question) and system prompts (behaviour question), read together in the agent profile rather than in isolation. |
| **Ownership** | `AgentsInfo.Owners` + `agentAccess`'s directory-owners expand + blueprints | Accountability. Two owner sources are kept distinct and never merged: Entra directory owners (`agentAccess`'s `$expand=owners`) vs. platform-reported owners (`AgentsInfo.Owners`) — either counts as "has an owner," but they can disagree, and that disagreement is itself a finding. |

---

## 7. Things this dashboard cannot see (explicitly, by design)

Documented in source so a gap is never mistaken for a clean bill of health:

- **Conditional Access agent-scoping** — v1.0 `conditionalAccessPolicy` exposes
  no property for per-agent targeting (that's a preview-only Graph capability).
  This dashboard can report "does any enabled CA policy exist," never "is this
  specific agent in scope of one."
- **Purview policy coverage** for non-Foundry agents — DLP/DSPM/sensitivity
  label enforcement on Copilot Studio, SharePoint and Agent Builder agents is
  not exposed through any Graph endpoint this dashboard calls. `Guardrails`
  only covers Microsoft Foundry-hosted agents.
- **MCP traffic outside the Agent 365 Tooling Gateway** — direct, out-of-band
  MCP connections leave no `CloudAppEvents` row.
- **Blueprint credentials** — client secrets/certificates on a blueprint's
  application object are not read; the "blast radius" framing describes the
  boundary's *structural* property, never a count of exposed secrets.
- **Incident-to-agent correlation** is a substring heuristic over stringified
  alert evidence, not a documented Graph relationship — flagged in source as
  needing validation against real tenant incidents before it's relied on.

---

*Generated from the source in `src/hooks/useAgent365Graph.js`,
`src/msalConfig.js`, `src/domain/agentMapping.js`, `src/domain/agentStatusRules.js`
and `src/domain/mcpActivity.js`. If any of those files change, this document
is the thing that goes stale — check it against the fetchers, not the other
way around.*
