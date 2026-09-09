"""Behavioral Trust Scoring.

Real, installed AGT capability confirmed by direct inspection --
agentmesh.TrustTracker/TrustScore -- that this project did not use at all
until now. Nothing about trust was ever computed in the live pipeline; the
only prior trace of "trust" in this codebase was a stale .pyc cache file
left over from an earlier, deleted identity.py module.

TrustTracker.record_interaction(agent_id, peer_id, action, success) moves a
0.0-1.0 score for `agent_id` (the identity being scored) relative to
`peer_id` (who it interacted with) -- confirmed by direct testing:

    tracker = TrustTracker()  # initial_score=0.5, reward=0.01, penalty=0.05
    tracker.get_score(did)                    -> 0.5
    tracker.record_interaction(did, peer, action, success=True)   -> 0.51
    tracker.record_interaction(did, peer, action, success=False)  -> 0.46

peer_id is set to this project's own AGENT_ID (the fleet owner/grantor, see
capability_grants.py) for every call, regardless of which identity is
actually calling -- there is no third party in this project's scenario for
an identity to build trust WITH other than the fleet itself.

This module only tracks and reports the score -- it does not yet gate
anything on it (e.g. denying calls below a threshold). See
docs/feature-implemented.md for that as a documented next step, not
something this module does today.
"""

from __future__ import annotations

from agentmesh import TrustTracker

from governed_agent.governance.spiffe_setup import FINANCE_AGENT_DID


def build_trust_tracker() -> TrustTracker:
    return TrustTracker()


def record_and_get_score(tracker: TrustTracker, agent_did: str, action: str, success: bool) -> float:
    return tracker.record_interaction(agent_did, peer_id=FINANCE_AGENT_DID, action=action, success=success)
