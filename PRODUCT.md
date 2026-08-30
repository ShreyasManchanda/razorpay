# Product

## Register

product

## Users

Buildathon judges, security reviewers, and engineers evaluating whether an AI-agent payment was authorized honestly. They need to replay a real negotiation, understand why Warden decided PASS, STEPUP, or REJECT, and verify that policy changes do not require rerunning the LLM workflow.

## Product Purpose

Warden is a defense-only observability and approval surface for agent-to-agent payments. It makes the detector legible through real transcripts, trust-score trajectories, mandate/signature state, policy comparison, human STEPUP review, and held-out evaluation metrics. Success means a reviewer can understand the evidence and decision path in one scrollable session without trusting invented demo data.

## Brand Personality

Warm, nostalgic, exacting. The interface should feel like a memorable illustrated place carrying a serious security instrument: human enough to invite attention, precise enough to withstand technical scrutiny.

## Anti-references

Avoid generic SaaS dashboards, fabricated metrics or dialogue, glass panels outside the hero, dense control-room layouts, decorative gradients, and motion that obscures evidence. Do not turn the replay into a live websocket dashboard or add features outside the frontend PRD.

## Design Principles

1. Show the evidence before the claim.
2. Keep the scene stable while the case changes.
3. Make risk state legible through one consistent verdict signal.
4. Separate detection evidence from policy choice.
5. Treat human approval and failure states as first-class outcomes.

## Accessibility & Inclusion

Target WCAG 2.2 AA. Preserve keyboard access for case navigation and all controls, provide visible focus states and live status updates, keep text readable over the illustrated scene, support reduced motion, and never rely on color alone to communicate a verdict.
