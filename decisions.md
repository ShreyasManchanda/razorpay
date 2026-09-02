# Decisions — Project Warden

> **This is a living document.** Append new decisions as they are made. If a decision is revised, mark the old entry REVISED and add a new entry. Never delete entries — they are the audit trail of why we chose what we chose. Every agent working on this project must read this file before writing code and update it after making any non-trivial choice.

## Format

| Field | Meaning |
|---|---|
| ID | Stable identifier, never reused |
| Status | LOCKED (final) / REVISED (superseded by a later entry) |
| Date | When the decision was made |
| Rationale | Why, not just what |

---

## D-001: Track choice

**Status:** LOCKED
**Date:** 2026-08-22

**Decision:** Track 02 — AI Risk Manager.

**Rationale:** The track description is a near-verbatim match for what Warden does: "a working detector, verifier or auto-responder for one class of loss, with measured precision and recall on a held-out test set." Warden detects dishonest agent-to-agent authorization as its single class of loss. Defense-only constraint is satisfied by the closed internal self-play design.

---

## D-002: LLM model

**Status:** LOCKED
**Date:** 2026-08-23

**Decision:** Google Gemini 2.0 Flash (`gemini-2.0-flash`) for every agent — buyer, merchant, attacker, pattern synthesizer.

**Rationale:** Budget constraint. No Claude/Anthropic budget available. Gemini Flash at $0.10/M input + $0.40/M output tokens is affordable even for 50 negotiations × ~6 turns × 2 agents = ~600 calls per eval batch (~$0.20 total). Supports native structured output via `langchain_google_genai.ChatGoogleGenerativeAI.with_structured_output(PydanticModel)`. Quality is adequate for coherent reasoning that DriftScorer can measure.

**Trade-off accepted:** Reasoning quality may be lower than Sonnet-class models. DriftScorer's signal depends on coherent reasoning; if Flash produces noisy reasoning, the false-positive rate on clean runs may be higher. Mitigation: calibrate thresholds against actual Flash-generated transcripts, not idealized ones.

---

## D-003: Embedding model

**Status:** LOCKED
**Date:** 2026-08-23

**Decision:** Local `sentence-transformers/all-MiniLM-L6-v2` (384-dim).

**Rationale:** No external API dependency during demo recording. 2.56B downloads on HuggingFace, extremely well-established. Fast enough for real-time scoring of short reasoning strings. Cosine similarity over a handful of short texts doesn't need FAISS/Qdrant.

---

## D-004: Mandate signing

**Status:** LOCKED
**Date:** 2026-08-23

**Decision:** PyNaCl (`nacl.signing`), Ed25519.

**Rationale:** Simpler sign/verify API than `cryptography` library. Ed25519 produces compact signatures (64 bytes). PyNaCl 1.6.2 confirmed on PyPI.

---

## D-005: Storage

**Status:** LOCKED
**Date:** 2026-08-23

**Decision:** Flat append-only JSON files. No database.

**Rationale:** Buildathon project, not production system. No migration overhead, no ORM complexity, trivially inspectable for debugging. Files map directly to what the replay UI reads.

---

## D-006: Agent orchestration

**Status:** LOCKED
**Date:** 2026-08-23

**Decision:** LangGraph for all three graphs (negotiation, warden, selfplay).

**Rationale:** Cyclic turn-loop needs graph structure. Parallel detection fan-out/fan-in maps naturally to LangGraph parallel nodes. STEPUP pause/resume uses native `interrupt()` + `Command(resume=...)`. Self-play wraps the other two as compiled subgraphs. LangGraph 1.2.11 confirmed stable on PyPI.

---

## D-007: Parallel detection state keys

**Status:** LOCKED
**Date:** 2026-08-23

**Decision:** Each detection node writes only to its own top-level state key (`violations`, `drift`, `injection_flags`). A dedicated `merge_signals` node assembles them into `SignalBundle`.

**Rationale:** Under LangGraph's default state merge, if all three nodes wrote to a shared `signals` dict, the last one to finish would overwrite the others. Separate keys eliminate this collision structurally.

---

## D-008: Policy layer isolation

**Status:** LOCKED
**Date:** 2026-08-23

**Decision:** `policy_decision` function is typed against `PolicyDecisionInput` (signals + policy_config only), not full WardenState. Transcript is not in scope.

**Rationale:** "Policy never touches transcript" enforced structurally, not by convention. If someone adds `transcript` to the function signature later, the type checker rejects it because it's not in `PolicyDecisionInput`.

---

## D-009: STEPUP interrupt safety

**Status:** LOCKED
**Date:** 2026-08-23

**Decision:** `stepup_wait` node contains nothing except `interrupt(...)` and returns the resume value. No side effects before or inside the interrupt call.

**Rationale:** LangGraph re-runs a node from its start when resuming from an interrupt. Any side effect placed before `interrupt()` would fire twice. Confirmed in official docs: "Side effects called before interrupt must be idempotent."

---

## D-010: Evaluation protocol

**Status:** LOCKED
**Date:** 2026-08-23

**Decision:** Four classes (`clean`, `injected`, `gradual-drift`, `legitimate-revision`) built via three separate generation paths. 30–50 total negotiations, roughly even. Hold out ~20% by deterministic hash split before any pattern tuning.

**Rationale:** Clean and legitimate-revision are not attacks — they don't come from the AttackerAgent loop. Conflating generation paths would contaminate labels. Held-out split must be locked before calibration begins to prevent leakage.

---

## D-011: DriftScorer signals

**Status:** LOCKED
**Date:** 2026-08-23

**Decision:** Three drift signals from one embedding trajectory:
1. `sudden_drop`: large single-turn decrease in intent similarity
2. `gradual_drift`: cumulative decline from first to last turn
3. `coherence_break`: large drop in consecutive-turn similarity between buyer reasonings

**Rationale:** Signal 3 distinguishes legitimate revision (topic shifts but reasoning stays coherent) from manipulative drift (reasoning becomes contradictory/incoherent). Without it, DriftScorer has high FPR on legitimate-revision class. Trust score chart uses raw intent similarity per turn.

---

## D-012: Injection scanner strategy

**Status:** LOCKED
**Date:** 2026-08-23

**Decision:** v1 structural regex as primary detector. v2 corroboration gate (Gemini Flash structured output) applied only to flagged sentences.

**Rationale:** Regex catches obvious imperative injection cheaply. Over-defense is a known failure mode (NotInject benchmark). v2 corroboration asks "is this directive aimed at the buyer agent or describing merchant terms?" — cuts FPs without abandoning structural-first approach.

---

## D-013: Defense-only boundary

**Status:** LOCKED
**Date:** 2026-08-23

**Decision:** AttackerAgent is a closed internal component. It targets only our own agents inside the self-play loop. Never exposed as callable capability. Produces no artifact usable to attack systems outside this project. Statement included verbatim in README.

**Rationale:** Track 02 explicitly disqualifies anything offense-capable. This boundary makes compliance unambiguous.

---

## D-014: Frontend approach

**Status:** SUPERSEDED IN PART BY D-030
**Date:** 2026-08-23

**Decision:** Start with a static replay viewer (plain HTML + Chart.js), without an unbounded live websocket dashboard. D-030 later adds a bounded request/response live session while retaining deterministic replay.

**Rationale:** Deterministic replay remains the reliable recording path. The later buildathon correction requires a judge-typed, per-turn demonstration, but still does not justify persistent websocket infrastructure.

---

## D-015: LLM model tiering

**Status:** LOCKED
**Date:** 2026-08-23

**Decision:** Gemini 2.5 Flash (`gemini-2.5-flash`) for buyer and merchant agents (visible negotiations, quality matters). Gemini 2.5 Flash Lite (`gemini-2.5-flash-lite`) for attacker agent, pattern synthesizer, and injection scanner v2 corroboration gate (bulk generation, quality matters less).

**Rationale:** Budget constraint from user. Flash Lite is significantly cheaper than Flash while still supporting structured output. Buyer/merchant reasoning quality directly affects DriftScorer signal quality, so those use the higher-tier model.

---

## D-016: LLM provider fallback chain

**Status:** LOCKED
**Date:** 2026-08-23

**Decision:** Shared `create_llm()` factory in `src/warden/llm.py`. Provider selection order:
1. Groq (`openai/gpt-oss-20b`) if `GROQ_API_KEY` present
2. Gemini (`gemini-3.5-flash`) if only `GOOGLE_API_KEY` present  
3. RuntimeError if neither

**Rationale:** User's Gemini credits depleted immediately on first test. Groq free tier is reliable and supports structured output. Factory pattern means swapping providers only requires changing .env keys, not code.

---

## D-017: Two-tier injection detection

**Status:** LOCKED
**Date:** 2026-08-23

**Decision:** Injection scanner uses two tiers:
1. `IMPERATIVE_PATTERNS` (hard): explicit agent-directed commands → REJECT/STEPUP per policy
2. `SUSPICIOUS_PATTERNS` (soft): manipulation tactics (urgency, social pressure, subscription language) → always STEPUP

Hard tier has known high FPR on benign text; mitigated by v2 corroboration gate (Gemini/Groq Flash Lite second-pass). Soft tier has 0/14 FPR on benign negative set.

---

## D-018: Provider-neutral structured negotiation output

**Status:** LOCKED
**Date:** 2026-08-24

**Decision:** Buyer, merchant, and attacker agents use one provider-neutral JSON contract plus local Pydantic validation. Provider order is Groq (`openai/gpt-oss-20b`) → TokenRouter (`qwen/qwen3.8-max-free`) → Gemini (`gemini-3.5-flash`). Rate limits, connection failures, malformed JSON, and failed validation advance to the next provider.

**Rationale:** Provider-specific tool-calling parsers caused a fatal `functions.BuyerAction` mismatch during evaluation. Normalizing at the application layer makes fallback behavior consistent across free providers and keeps the project within budget.

---

## D-019: Injection hard-tier directionality

**Status:** LOCKED
**Date:** 2026-08-24

**Decision:** A REJECT-level signature must be explicitly directed at an agent’s decision process. Ordinary commercial obligations (“receipt required”, “returns must be requested”) and fulfillment statements (“you will receive”) are not hard injection evidence. Ambiguous pressure language stays in the STEPUP-level suspicious tier pending corroboration.

**Rationale:** The original broad regexes contradicted the built-in benign negative set and caused clean-run rejections.

---

## D-020: Rate-limit-safe phase scripts

**Status:** LOCKED
**Date:** 2026-08-25

**Decision:** Evaluation supports `--phase clean|legitimate-revision|injected|gradual-drift --count N`, with four project-root commands defaulting to ten runs per class. Each completed negotiation is appended immediately. A provider failure stops the current batch but does not lose prior results; rerunning skips saved transaction IDs.

**Rationale:** The user has free-tier quota constraints and needs isolated batches rather than one 40-run pipeline.

---

## D-021: Drift decisions use sustained evidence

**Status:** LOCKED
**Date:** 2026-08-25

**Decision:** Do not classify drift from one noisy adjacent embedding change. Require a sustained early/late intent-similarity decline, or endpoint drift above 0.45, or repeated extreme coherence breaks on sufficiently long transcripts.

**Rationale:** Nine real clean Groq transcripts showed large turn-to-turn cosine swings without sustained goal abandonment. Single-threshold logic produced a 100% clean false-positive rate.

---

## D-022: Resume semantics for deterministic evaluation IDs

**Status:** LOCKED
**Date:** 2026-08-25

**Decision:** A saved transaction ID is skipped. An unsaved transaction ID is treated as an orphaned attempt: clear its transcript and verdict, then regenerate from turn zero.

**Rationale:** Append-only storage is safe only when a run has a single owner. Without orphan cleanup, provider failures could contaminate future embeddings with turns from multiple attempts.

---

## D-023: Machine-readable negotiation actions are closed enums

**Status:** LOCKED
**Date:** 2026-08-25

**Decision:** Buyer actions are exactly `accept`, `counter`, or `reject`; merchant actions are exactly `offer`, `accept`, or `reject`. Natural-language detail belongs in `message`; control flow reads only the enum field.

**Rationale:** Free-form action strings made graph routing nondeterministic and caused avoidable max-turn runs.

---

## D-024: STEPUP must persist before interrupt

**Status:** LOCKED
**Date:** 2026-08-25

**Decision:** A dedicated node persists pending review state before the LangGraph interrupt. Resume uses the same stable thread ID and `Command(resume=...)`; approved STEPUP continues into payment execution and persists its final verdict.

**Rationale:** Human review is a boundary across requests. Without durable pending state, resume endpoints either lose the transaction or fake approval without executing the guarded workflow. The current demo checkpointer is process-local; production requires a durable implementation.

---

## D-025: Payment execution fails closed without credentials

**Status:** LOCKED
**Date:** 2026-08-25

**Decision:** Razorpay mocking is opt-in for tests/demos through `allow_mock=True`. The Warden execution node does not enable it; missing credentials raise before order creation.

**Rationale:** A payment guard must never turn a configuration failure into a successful-looking mock execution.

---

## D-026: Replay viewer is API-served

**Status:** LOCKED
**Date:** 2026-08-25

**Decision:** FastAPI serves `ui/replay.html` at `/ui/replay.html` so browser fetches use the API origin. Do not rely on opening the HTML file directly with `file://`.

**Rationale:** The viewer calls same-origin transcript, verdict, and report endpoints; file-open mode creates an opaque origin and breaks fetch.

---

## D-027: YAML scenario system for negotiators

**Status:** LOCKED
**Date:** 2026-08-25

**Decision:** Buyer/merchant personas, catalogs, margin policies, and default intents are loaded from YAML files in `src/warden/scenarios/configs/` via a pydantic-validated loader. `/negotiate` accepts an optional `scenario` id; `/scenarios` lists them. First scenario: `sabziwala_vs_mom` (Hinglish vegetable-mandi negotiation).

**Rationale:** The demo needs a memorable, culturally specific negotiation that shows DriftScorer working over natural Hinglish reasoning — not just English electronics catalogs. Scenarios keep personas out of code so new demos are config-only.

---

## D-028: Provider order revised — TokenRouter first, OpenRouter backup

**Status:** LOCKED (revises D-018's ordering; D-018's provider-neutral contract unchanged)
**Date:** 2026-08-25

**Decision:** Fallback chain order is now TokenRouter (`qwen/qwen3.8-max-free`) → OpenRouter (`minimax/minimax-m3:free`, env-overridable) → Groq (`openai/gpt-oss-20b`) → Gemini (`gemini-3.5-flash`). Missing keys skip a provider silently.

**Rationale:** Quota reality: TokenRouter free tier is effectively unlimited; Groq burns out mid-batch when used first; Gemini credits are exhausted. The old Groq-first order made every call pay Groq rate-limit tax before reaching TokenRouter. OpenRouter adds a second high-capacity tier between them.

---

## D-029: Cart contents come from a structured selected_items contract

**Status:** LOCKED
**Date:** 2026-08-25

**Decision:** `MerchantAction` gains `selected_items: list[str]` — exact catalog names the buyer actually agreed to buy. `finalize_cart` builds carts from this field first; substring matching on merchant messages survives only as fallback for pre-contract transcripts.

**Rationale:** Substring extraction put suggested-but-unaccepted accessories in the cart ("would you like to add a charger?" → ₹899 added → false `price_ceiling_exceeded` REJECTs on clean runs), contaminating eval data (B-011). Structured selection makes cart contents deterministic and auditable.

---

## D-030: Live demo sessions are bounded and signal-first

**Status:** LOCKED
**Date:** 2026-08-31

**Decision:** The replay page may start a bounded `/live/sessions` transaction for the default `sabziwala_vs_mom` scenario. Each `/turns` response appends at most the next buyer/merchant exchange, evaluates the current transcript, and returns transcript, cart, signal bundle, verdict, phase, and execution mode. Presenter messages are accepted as buyer turns. If no provider is configured, a deterministic offline merchant response is used and labeled `fallback`.

**Rationale:** A buildathon judge needs to see the detector react to a message, not only inspect pre-recorded JSON. Bounding the session keeps the live beat deterministic and defense-only while preserving the stored 40-run evaluation set as an independent measurement artifact. Signals—not raw transcript text—remain the policy input.

---

## D-031: One shared authorization service and one MCP tool

**Status:** LOCKED
**Date:** 2026-08-31

**Decision:** Extract mandate-level signature, detector, and policy evaluation
into `services.authorization.evaluate_authorization`. Live Studio and the MCP
adapter call this shared side-effect-free service. MCP exposes exactly one
stdio tool, `warden_authorize_payment`, with strict bounded inputs and fixed
policy names. It cannot execute Razorpay, resolve STEPUP, register keys, or
access in-memory live sessions.

**Rationale:** A single tool provides a genuine integration story without
building a second A2A relay project. Payload-based MCP works across process
boundaries; session-id coupling would not. Keeping execution out of the tool
preserves the payment and human-approval privilege boundaries.

---

## D-032: Presenter progress stays inside the existing one-page product

**Status:** LOCKED
**Date:** 2026-08-31

**Decision:** Add a compact six-beat rail and synchronized evidence strip to
the existing hero. Do not add routes or a second presenter application. The
rail targets existing replay cases and sections; the only new evidence
interaction is the deterministic tamper gate.

**Rationale:** Judges need a reliable five-minute sequence and visible proof
of backend capabilities. Reusing the existing page and controls adds narrative
clarity without creating another navigation system or demo failure surface.

---

## D-033: Bounded eval-v2 is the honest capability boundary

**Status:** LOCKED
**Date:** 2026-09-01

**Decision:** Treat `data/eval_v2` as the current offline capability benchmark:
80 deterministic cases, 78 in scope, paired controls, provenance-verified
attacks, and a deterministic grouped 22-row holdout that excludes the blind
challenge tranche. Semantic, operational, constraint, and tamper metrics stay
separate. Multilingual injection is retained as an explicitly out-of-scope
probe. Do not describe these figures as production accuracy or production
readiness.

**Rationale:** The original verdict-only corpus produced a misleading perfect
score because constraint rejection masked semantic detection. Eval-v2 exposes
blind-challenge misses and confidence intervals, preserving useful engineering
evidence without overstating what a small synthetic corpus proves.

---

## D-034: Replay evidence is immutable and server-framed

**Status:** LOCKED
**Date:** 2026-09-01

**Decision:** Hero fixtures must end in explicit buyer agreement and reconstruct
their declared cart from the transcript. `GET /replays/{case_id}` returns one
server-derived evidence frame per complete exchange. Provisional frames use
`ANALYSIS`; final policy decisions appear only after agreement. Human review
uses a new disposable clone and cannot resume a canonical replay transaction.

**Rationale:** Client-side signal slicing looked live but could drift from
backend semantics, while resuming the stored Drift transaction mutated demo
evidence for later runs. Server frames keep animation truthful and disposable
checkpoints make every presentation repeatable.

---

## D-035: Live cart checks remain pending until buyer agreement

**Status:** LOCKED
**Date:** 2026-09-01

**Decision:** A live session with no buyer-agreed cart returns provisional
`ANALYSIS`, clears cart-derived constraint violations from policy input, and
marks the constraint detector pending. Injection, suspicious-pattern, drift,
and detector-degradation signals may still produce REJECT or STEPUP before
agreement.

**Rationale:** An empty candidate cart before acceptance is normal negotiation
state, not a failed authorization. Treating it as final REJECT stopped the live
conversation after its first offer and confused absence of consent with a bad
signed mandate.

---

## D-036: Live consent requires explicit finalization language

**Status:** LOCKED
**Date:** 2026-09-01

**Decision:** Treat generic affirmations and questions containing words such as
"haan", "final", or "confirm" as negotiation turns unless they explicitly
accept a cart, order, or deal. The signed cart extractor remains the authority
for item-level agreement evidence.

**Rationale:** A freshness or final-price question is not payment consent.
Completing a live session from a keyword alone would reproduce the exact
difference between identity and honest authorization that Warden exists to
enforce.
## D-037: Versioned detector registry and authorization-only degraded fallback

**Status:** LOCKED
**Date:** 2026-09-01

**Decision:** InjectionScanner loads a validated, versioned pattern registry with
safe built-in fallback; self-play candidates are activated only after compile,
deduplication, and clean-fixture gates. If negotiation or a required detector
dependency fails, `/negotiate` uses the side-effect-free authorization service,
forces STEPUP when necessary, persists the degraded diagnosis, and never calls
the Razorpay order path. Approval of that degraded review resolves
authorization only; payment execution remains disabled.

**Rationale:** A detector update must be auditable and reversible, while an
outage must not silently cross the payment boundary or turn an UNKNOWN result
into PASS. The fallback is deliberately honest and reviewable rather than
pretending to have completed a live payment.

---

## D-038: Separate semantic and operational evaluation contracts

**Status:** LOCKED
**Date:** 2026-09-01

**Decision:** The immutable eval-v2 report keeps semantic detector metrics,
constraint/tamper strata, and operational verdict outcomes separate. The
22-row deterministic grouped holdout excludes the 16-row blind challenge;
ERROR/UNKNOWN rows are tracked as unscored, not counted as catches or clean
true negatives. Reports include explicit false-pass/false-stepup/false-reject
counts and cost per 1,000 transactions.

**Rationale:** A high semantic score can hide payment-friction or dependency
failures. Publishing both contracts gives judges the honest capability and
the action-level risk picture without mixing distinct loss classes.

---
