# Real Rego policy for the ACS "tools_policy" policy id (see ../manifest.yaml).
# Evaluated by the real agent_control_specification SDK's bundled OPA
# dispatcher -- genuine Rego, not AGT's "builtin" mock interpreter used
# earlier in this project's history (see docs/implementation-notes.md).
#
# input.policy_target.value is the tool call's args dict, per the manifest's:
#   policy_target: "$.tool_call.args"
#   policy_target_kind: tool_args
# The tool name is NOT at input.tool_call.name -- confirmed by inspecting a
# real InterventionPointResult.policy_input directly (an earlier version of
# this file got this wrong, and every rule below silently fell through to
# the default allow because of it -- see docs/implementation-notes.md for
# the full diagnosis). The real path is input.snapshot.tool_call.name.
package agt.finance.tools

default decision := {"decision": "allow"}

decision := {"decision": "deny", "reason": "destructive_action_blocked"} if {
    input.snapshot.tool_call.name == "drop_table"
}

decision := {"decision": "deny", "reason": "dlp_ratchet_blocks_external_send"} if {
    input.snapshot.tool_call.name == "send_email"
    input.policy_target.value.dlp_ratchet == "restricted"
    input.policy_target.value.recipient_is_external == true
}

decision := {"decision": "escalate", "reason": "large_email_requires_approval"} if {
    input.snapshot.tool_call.name == "send_email"
    input.policy_target.value.body_length > 2000
}
