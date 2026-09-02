# Product

## Register

product

## Users

Buildathon judges, security reviewers, and engineers evaluating whether an AI-agent payment was authorized honestly. They need to replay a real negotiation, understand why Warden decided PASS, STEPUP, or REJECT, and verify that policy changes do not require rerunning the LLM workflow.

## Product Purpose

Warden is a defense-only trust layer and approval surface for agent-to-agent payments. It sits between negotiation and payment execution, makes its evidence legible through real transcripts and signals, and offers one narrow MCP authorization tool for integration. Success means a reviewer can understand and exercise the decision path in one scrollable session without trusting invented demo data.

## Brand Personality

Warm, nostalgic, exacting. The interface should feel like a memorable illustrated place carrying a serious security instrument: human enough to invite attention, precise enough to withstand technical scrutiny.

## Anti-references

Avoid generic SaaS dashboards, fabricated metrics or dialogue, glass panels outside the hero, dense control-room layouts, decorative gradients, and motion that obscures evidence. The live demo must stay bounded and request/response based; it is an evidence surface, not a persistent websocket dashboard.

## Demo Modes

- **Replay cases** provide deterministic Clean, Legit, Injection, and Drift walkthroughs from the `sabziwala_vs_mom` fixture set. The server returns immutable per-exchange frames; autoplay updates transcript, offered cart, buyer-agreement provenance, trust, detectors, policy, and verdict together.
- **Live demo** starts one bounded sabziwala session. A presenter can run a prepared conversation or speak naturally: local transaction rules ground aliases, quantities, substitutions, cart edits, bargaining, consent, and common market/payment questions, while the provider chain handles broader dialogue without authority to mutate the active offer. A deterministic outage fallback stays useful and is labeled, never disguised as a model call. Pre-agreement exchanges remain provisional `ANALYSIS`; questions are not inferred as consent; every turn updates the same backend evidence surface.
- **Human review** appears only for STEPUP and resolves once. The held-out evaluation report remains separate from live-session data.
- **MCP authorization** evaluates an externally supplied signed cart and transcript through the shared detector service. It returns evidence and a verdict but cannot execute payment or resolve review.
- **Tamper proof** modifies a signed cart and visibly demonstrates that Ed25519 rejection happens before semantic detectors or payment.

## Product Boundaries

- The stored/full negotiation graph can create a Razorpay test order after PASS. The live session route authorizes and demonstrates review state but does not create an order.
- Razorpay integration currently proves server-side Orders API creation, not checkout completion or capture.
- Warden verifies the merchant CartMandate signature. Buyer IntentMandate signing and open key registration are not claimed.
- The MCP adapter is real stdio transport, not full A2A relay, Agent Card, or protocol conformance.
- Headline evaluation is the bounded `eval-v2` corpus: 80 deterministic cases,
  78 in scope, with a 22-row grouped holdout that excludes the 16-row blind
  challenge. It is useful detector capability evidence, not a
  production-prevalence benchmark or production-readiness claim.
- Current eval-v2 semantic recall is 71.4% overall and 100% on the grouped
  holdout; blind-challenge recall is only 25% (2/8). Operational metrics now
  separate PASS/STEPUP/REJECT outcomes, unscored dependency failures, and
  cost-weighted false positives. Known misses remain in the report rather
  than being hidden; these figures do not establish production readiness.
- At the documented operating weights, the all-data report records 4 false
  passes, 5 false STEPUPs, 0 false rejects, and weighted cost of 714.29 per
  1,000 scored transactions. The blind tranche costs 2,625 per 1,000 because
  its unseen attacks are intentionally difficult; this is the key limitation
  to discuss with judges.
- Multilingual injection is explicitly out of scope for the current product
  claim and remains only as a tracked future probe.
- Self-play hardening is offline and bounded to one graph invocation at a time;
  candidate patterns are gated artifacts, not online learning or an automatic
  holdout-tuning loop.

## Design Principles

1. Show the evidence before the claim.
2. Keep the scene stable while the case changes.
3. Make risk state legible through one consistent verdict signal.
4. Separate detection evidence from policy choice.
5. Treat human approval and failure states as first-class outcomes.

## Accessibility & Inclusion

Target WCAG 2.2 AA. Preserve keyboard access for case navigation and all controls, provide visible focus states and live status updates, keep text readable over the illustrated scene, support reduced motion, and never rely on color alone to communicate a verdict.
