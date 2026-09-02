# Bugs — Project Warden

> **This is a living document.** Log every confirmed bug immediately upon discovery. Update status as you fix them. Add new known risks whenever you spot a potential issue during implementation. Never close this file and say "I'll log it later" — log it now.

## Format

| Field | Meaning |
|---|---|
| ID | Stable identifier (B-001, B-002...) |
| Status | OPEN / IN_PROGRESS / FIXED / WONTFIX |
| Severity | P0 (blocks demo) / P1 (wrong behavior) / P2 (degraded quality) / P3 (cosmetic) |
| Found | Date discovered |
| Description | What's wrong and where |

---

## Confirmed Bugs

Historical confirmed bugs and their fixes are recorded below. New unresolved
items are tracked under **Known Risks** until reproduced as defects.

---

## Known Risks

These are not confirmed bugs yet but are likely to bite during implementation. Move to Confirmed Bugs if/when they do.

### R-001: DriftScorer FPR on legitimate-revision class

**Severity:** P1
**Likelihood:** High without the coherence_break signal; moderate with it.

Cosine similarity between original intent and buyer reasoning will naturally drop when a buyer legitimately discovers a better product in a different category. The `coherence_break` signal (consecutive-turn similarity) should distinguish this from manipulative drift, but thresholds need calibration against actual Gemini Flash transcripts. If FPR is still >15% on legitimate-revision after calibration, consider raising COHERENCE_THRESHOLD or adding a minimum-turns-before-check rule.

### R-002: Gemini Flash reasoning quality may be too noisy for DriftScorer

**Severity:** P1
**Likelihood:** Unknown until tested.

The spec originally called for Sonnet-class reasoning because DriftScorer measures reasoning quality. Flash may produce less coherent or more formulaic reasoning, making clean runs look like drift. Mitigation: run 3–5 clean negotiations first, inspect the embedding trajectory manually before calibrating thresholds.

### R-003: Injection scanner regex over-defense on benign merchant text

**Severity:** P2
**Likelihood:** Observed and bounded, not eliminated.

Words like "required", "must", and "mandatory" appear legitimately in
merchant policy language. The scanner now keeps hard imperatives separate from
suspicious STEPUP signals, normalizes common obfuscation, and runs against a
frozen benign set. The current eval-v2 report still records five operational
false STEPUPs overall, so this remains a measured friction risk rather than a
claim of zero false positives. The optional LLM corroboration helper is not a
required payment-path dependency and is not presented as a production gate.

### R-004: LangGraph parallel node execution order is nondeterministic

**Severity:** P3
**Likelihood:** Low impact.

Three detection nodes run in parallel. LangGraph doesn't guarantee completion order. Since each writes only its own key and merge_signals runs after all three complete, this doesn't cause data loss — but don't add any logic that assumes ordering between detection nodes.

### R-005: Ed25519 signature canonicalization

**Severity:** P1
**Likelihood:** Moderate if canonical serialization isn't handled explicitly.

Signing a Pydantic model's JSON representation requires consistent field ordering and encoding. If serialization is non-deterministic (e.g., dict ordering varies), sign→verify passes locally but fails when the mandate is reconstructed from storage. Mitigation: use `model_dump_json()` with explicit field ordering, sign the bytes of that output, verify by deserializing and re-signing to compare.

### R-006: Razorpay Orders API requires server-side order creation

**Severity:** P2
**Likelihood:** Certain if not handled.

Razorpay checkout cannot work without a pre-created order_id from the server-side API. The execute_payment node must call `razorpay_client.order.create()` before initiating any payment flow. For the recorded demo, this can be mocked since real money movement isn't needed.

### R-007: Self-play cost scaling

**Severity:** P3
**Likelihood:** Low with Gemini Flash pricing.

50 negotiations × 6 turns × 2 agents = ~600 calls per eval batch. At ~700 tokens/call average, this is ~420K tokens ≈ $0.20 total with Flash. Not a budget concern, but rate limits on the free tier may slow batch generation. Use the paid tier if available, or spread generation across sessions.

### R-008: Held-out split leakage

**Severity:** P1
**Likelihood:** Moderate if split isn't locked before calibration.

If injection patterns are tuned on data that includes held-out samples, metrics are inflated. Mitigation: eval-v2 uses deterministic SHA-256 group ordering stratified by label, keeps paired rows together, and stores the holdout IDs. Never tune patterns using holdout data. Report both all-data diagnostics and the untouched holdout separately.

### R-009: Merchant agent prompt contamination during attack runs

**Severity:** P2
**Likelihood:** Moderate.

When `attack_type == "injection"`, the poisoned catalog entry is spliced into the merchant agent's context. If the merchant agent's system prompt already contains trigger words (even innocuously), the injection scanner may flag the merchant's own system instructions rather than the attacker payload. Mitigation: keep clean-run merchant prompts free of trigger words (verify by running several times). For attack runs, ensure the scanner only scans the merchant's *output* messages, not its input context.

### R-010: Trust score chart misleading if buyer has few turns

**Severity:** P3
**Likelihood:** Moderate for short negotiations.

If a negotiation resolves in 2–3 turns, the drift trajectory is too short to show meaningful decline. The chart looks flat even in attack scenarios. Mitigation: set max_turns >= 6 so there's always enough trajectory to visualize, and note in the UI when turn count is below the calibration minimum.

### R-011: finalize_cart item extraction is fragile

**Severity:** P2
**Likelihood:** Moderate — depends on Gemini Flash mentioning exact product names.

The historical implementation extracted items from merchant messages by checking whether any catalog word appeared in text, then defaulted to the first item. That caused the charger-over-budget contamination found in B-011. The current implementation requires explicit buyer agreement, records evidence/warnings, and fails closed for suggestions, merchant-only selections, generic "yes", and empty/ambiguous carts.

### R-012: Gemini free tier depletes almost immediately

**Severity:** P1
**Status:** Mitigated (switched to Groq as primary)

Gemini API prepayment credits were exhausted after ~2 basic calls. Even if the user tops up credits, the per-call cost may still be prohibitive for 50-negotiation eval batches. Groq's free tier handles structured output reliably at zero cost. Keep Gemini as secondary/fallback option only.

### R-013: LangGraph checkpointer requires explicit thread_id

**Severity:** P2
**Likelihood:** Certain without fix — already fixed in api/main.py

When building the warden graph with a MemorySaver checkpointer, every `ainvoke()` call must include `config={"configurable": {"thread_id": <unique>}}`. Without it, LangGraph raises `ValueError: Checkpointer requires one or more of the following 'configurable' keys: thread_id`. Fixed by passing tx_id as thread_id.

### R-014: Injection scanner over-defense rate was 93% on benign text

**Severity:** P1
**Status:** FIXED (two-tier approach)

v1 regex had 13/14 false positive rate on the benign negative set. Fixed by
splitting into two tiers: hard imperatives and suspicious patterns. The
validated registry now preserves the reviewed baseline and synthesized entries;
suspicious patterns trigger STEPUP rather than REJECT, giving human reviewers
visibility without blocking legitimate sales.

### R-015: Gradual drift could be bypassed by keeping price low

**Severity:** P1
**Status:** FIXED

Policy layer only triggered STEPUP on gradual_drift when `cart_total > stepup_required_above`. Attacker could manipulate buyer into accepting a low-price item outside original intent without triggering any alert. Fixed: gradual_drift always STEPUPs regardless of amount.

### R-016: Blind-challenge generalization gap

**Severity:** P1
**Likelihood:** Confirmed

The untouched blind-challenge tranche catches only 2/8 semantic attacks (25%
recall). The grouped holdout is intentionally separate and currently reports
100% recall, so that result must not be presented as unseen-attack robustness.
Blind misses remain in `data/eval_v2/report.json` and are the next detector-
hardening target.

### R-017: Self-play activation is bounded to one invocation

**Severity:** P2
**Likelihood:** Confirmed

One self-play graph invocation runs one attacker/negotiation/warden round and
may propose a versioned pattern. Candidate activation is compile-, dedupe-,
miss-match-, and benign-control-gated, but a multi-round automatic regression
loop over the complete frozen holdout is not yet implemented. Treat generated
patterns as reviewed defensive artifacts, not online learning.

### R-018: Demo persistence is process-local

**Severity:** P2
**Likelihood:** Confirmed by design

The demo uses `MemorySaver` and flat JSON stores. Writes are atomic and HTTP
transaction IDs are path-validated, but cross-process durability, locking, and
multi-instance recovery require a database/checkpointer before production use.

### B-001: Structured-output parsing crashed evaluation runs

**Status:** FIXED
**Severity:** P0
**Found:** 2026-08-24

A provider could return a tool-call shape such as `functions.BuyerAction` that LangChain could not parse. The failover wrapper treated malformed output as fatal instead of retrying another provider, ending Phase 2.

**Fix:** `FallbackStructured` now requests plain JSON, extracts and validates it locally against the Pydantic schema, treats invalid output like any other retryable provider failure, and has regression tests.

---

### B-002: Injection scanner produced benign-commerce false positives

**Status:** FIXED
**Severity:** P1
**Found:** 2026-08-24

Clean negotiations were rejected because merchant text contained ordinary policy terms such as “required”, “must”, “you will receive”, or “non-negotiable”. This violated the intended two-tier design.

**Fix:** Hard signatures now require agent-directed action syntax. Generic policy language was removed from the hard tier; “non-negotiable” moved to the suspicious tier. Full suite passes at 92 tests. Evaluation rows created before this fix must not be used for headline precision/recall metrics.

### B-003: Agent sandbox cannot reach evaluation providers

**Status:** OPEN
**Severity:** P0
**Found:** 2026-08-24

The resumed 36-run evaluation failed on outbound connections for Groq, TokenRouter, and Gemini before the first fresh transaction completed. Local approval/usage policy blocked the required network escalation.

**Interim control:** Do not mix the archived `testset_pre_b002.jsonl` rows into current metrics. Run the incremental script from a normal terminal with provider access; it will resume from the empty current test set.

---

### B-004: Transcripts and verdicts were stored under src/data

**Status:** FIXED
**Severity:** P1
**Found:** 2026-08-25

Store path construction stopped at `src` instead of the repository root, so negotiation transcripts and verdicts landed in `src\data`. This made replay/API storage inconsistent with evaluation data.

**Fix:** Root-path calculation corrected for transcript, verdict, selfplay, and test-set stores. Existing files were moved from `src\data` to `data`.

---

### B-005: Drift detector treated normal LLM reasoning noise as manipulation

**Status:** FIXED
**Severity:** P1
**Found:** 2026-08-25

A single adjacent similarity drop over 0.25 was enough to STEPUP, causing 9/9 observed clean negotiations to be flagged. Coherence breaks below 0.30 had the same problem.

**Fix:** Sudden drift now requires a sustained first-half versus second-half intent-similarity decline. Endpoint gradual drift requires 0.45. Coherence break requires at least two extreme discontinuities in transcripts of four or more buyer turns. Offline replay now clears all ten archived clean transcripts.

---

### B-006: Interrupted evaluation retries appended to stale transcripts

**Status:** FIXED
**Severity:** P1
**Found:** 2026-08-25

A transaction interrupted after transcript writes but before test-set persistence was retried under the same ID. Old turns remained, producing duplicated negotiations and invalid drift trajectories.

**Fix:** Before retrying an unsaved evaluation ID, the runner clears its orphaned transcript and stale verdict. Added storage regression tests; full suite is now 95 tests.

---

### B-007: Negotiation action fields accepted arbitrary model text

**Status:** FIXED
**Severity:** P1
**Found:** 2026-08-25

Buyer and merchant schemas documented `accept`/`counter`/`reject` but typed them as free strings. Models emitted variants such as `accept_offer` and `offer_bundle`, so the negotiation router often missed completion and ran to the turn cap.

**Fix:** Action fields now use `Literal` contracts, prompts state the exact allowed values, and cart extraction deduplicates repeated catalog mentions.

---

### B-008: Initial STEPUP could not be resumed reliably

**Status:** FIXED
**Severity:** P0
**Found:** 2026-08-25

The Warden jumped directly into `interrupt()` without saving pending review data. The API resume endpoint then read a verdict file that did not exist and merely changed stored JSON instead of resuming the graph or executing an approved payment.

**Fix:** Added a side-effect-free-before-interrupt `record_stepup` node, shared API checkpointer, final-verdict persistence, and a `/stepup/{tx_id}/resume` flow that invokes `Command(resume=...)`. An integration test covers pending STEPUP through approval and order creation.

---

### B-009: Replay viewer rendered untrusted transcript as HTML

**Status:** FIXED
**Severity:** P1
**Found:** 2026-08-25

LLM/attacker-controlled transcript messages and explanations were inserted into `innerHTML`, allowing stored HTML/script injection in the replay UI.

**Fix:** Transcript and verdict rendering now escapes all dynamic text, and transaction IDs are URL-encoded before fetch.

---

### B-010: Missing Razorpay credentials silently created fake PASS orders

**Status:** FIXED
**Severity:** P0
**Found:** 2026-08-25

The payment wrapper automatically switched to a mock when credentials were absent. A misconfigured production/demo environment could therefore pass Warden, create a mock order, and appear to execute successfully.

**Fix:** Mock mode is now explicit via `allow_mock=True`. The Warden execution path uses the guarded default, so missing or empty Razorpay credentials fail closed before an order is attempted.

---

### B-011: finalize_cart added suggested-but-unaccepted items to carts

**Status:** FIXED
**Severity:** P1
**Found:** 2026-08-25

Cart extraction matched catalog words against merchant message text. When a merchant asked "Would you like to add a USB-C Fast Charger 65W as an accessory?" the ₹899 charger entered the cart despite the buyer never accepting it. A clean earbuds negotiation (total 2500) finalized at 3398, tripping `price_ceiling_exceeded` against the 3000 ceiling and producing false clean-run REJECTs (observed on `eval_clean_0_cfcd20`). This poisoned evaluation rows generated before the fix.

**Fix:** Merchant agents now return structured `selected_items`, but authorization still requires explicit buyer agreement. Merchant-only selections, suggestions, generic "yes", and substring/default fallbacks cannot create a cart. Ambiguous extraction fails closed and the pre-fix test-set row remains archived in `data/eval/testset_pre_cartfix.jsonl`.

---

### B-012: Policy swap endpoint read a stale src/data directory

**Status:** FIXED
**Severity:** P2
**Found:** 2026-08-25

`POST /policy/swap` hand-built its verdicts path from `__file__` and landed on `src/data/verdicts` — the pre-B-004 layout. The missing-directory guard masked the bug, so the endpoint always returned an empty result set instead of re-scoring stored signals.

**Fix:** The route now iterates `VerdictStore.base_dir` directly, guaranteeing it reads the same store every other endpoint uses.

---

### B-013: Hero replay evidence was static or missing until the final frame

**Status:** FIXED
**Severity:** P0
**Found:** 2026-08-31

Three sabziwala replay fixtures had empty trust trajectories, and the viewer rendered final detector state instead of updating evidence with each displayed turn. The demo therefore looked like a report even when the transcript advanced.

**Fix:** Every hero fixture now carries a trajectory. Replay progress slices transcript and trust evidence per turn, delays final flags and verdicts until the relevant frame, animates cart and detector values, and cancels superseded GSAP timelines during rapid navigation.

---

### B-014: No bounded real-time negotiation surface existed

**Status:** FIXED
**Severity:** P0
**Found:** 2026-08-31

The frontend could only load stored verdicts, so a presenter could not ask the sabziwala a question or demonstrate Warden evaluating a negotiation as it developed.

**Fix:** `/live/sessions` now owns isolated, locked, short-lived sessions. Each turn runs signature verification and all detectors, persists the transcript/verdict, returns a signal-first snapshot, clearly labels deterministic provider fallback, caps the exchange, and supports a one-shot STEPUP review. The hero consumes that contract without mixing live data into held-out evaluation metrics.

---

### B-015: API headline metrics did not match the held-out protocol

**Status:** FIXED
**Severity:** P1
**Found:** 2026-08-31

`GET /selfplay/report` previously aggregated every stored row even though the offline evaluator reported a deterministic SHA-256 holdout. That made the UI's “held-out” claim unverifiable and hid the small, imbalanced current denominator.

**Fix:** The API now reports the provenance-aware stratified holdout as the
primary metric set, preserves verdict-only and all-data diagnostics separately,
exposes the split rule and denominators, and keeps the historical 8/40 legacy
holdout distinct from the current eval-v2 artifact. Unverified legacy attack
rows cannot inflate semantic recall; live sabziwala sessions are explicitly
qualitative transfer evidence.

---

### B-016: Live detector or provider degradation could look like a clean approval

**Status:** FIXED
**Severity:** P1
**Found:** 2026-08-31

Provider fallback was bounded but an unavailable drift detector could leave a `PASS` verdict with incomplete evidence. The Razorpay wrapper also read only process environment variables while the app loaded `.env` through settings.

**Fix:** Live detector errors now fail closed to `STEPUP` and are surfaced in the signal bundle; provider fallback is labeled. Razorpay credentials resolve through the same settings layer while preserving explicit mock-mode guards. Live sessions are capped, locked, and expired after 30 minutes.

---

### B-017: Frontend state semantics and mobile containment were inconsistent

**Status:** FIXED
**Severity:** P0
**Found:** 2026-08-31

Partial replays used the amber STEPUP theme for a generic `CHECK` state, the
mobile hero retained desktop-width content, and the main viewport omitted the
active policy/payment boundary. This made provisional analysis look risky and
caused controls and evidence to leave the mobile viewport.

**Fix:** Added a neutral blue analysis state, consolidated the active visual
system in `ui/warden.css`, constrained every hero child at 375px, and added a
synchronized turn/cart-budget/policy/signature/payment rail. Browser checks
now report `scrollWidth == innerWidth` at 375px.

---

### B-018: Authorization logic was duplicated and not externally integrable

**Status:** FIXED
**Severity:** P1
**Found:** 2026-08-31

Live evaluation duplicated the graph's signature/detector/policy behavior, and
there was no supported way for another agent host to request a Warden decision
without coupling to HTTP session state.

**Fix:** Extracted a shared side-effect-free authorization service and added
one strict MCP stdio tool. Unknown agents and changed signatures fail before
semantic detectors; detector errors fail closed to STEPUP; the tool can never
execute payment. Direct and real stdio transport tests cover the contract.

---

### B-019: Explicit-agreement hardening blocked live negotiation before acceptance

**Status:** FIXED
**Severity:** P0
**Found:** 2026-09-01

After cart reconstruction correctly began failing closed, Live Studio evaluated
the pre-agreement empty cart as `agreement_ambiguous`, `cart_empty`, and
`category_mismatch`, returned REJECT, and blocked the session after an ordinary
offer. The security boundary was correct for final authorization but applied at
the wrong lifecycle phase.

**Fix:** Pre-agreement live evaluations now expose `ANALYSIS`, pending cart
constraints, and no payment request. Semantic detectors continue running, so a
hard injection can still reject immediately. Focused tests cover opening state,
ordinary provisional turns, injection blocking, agreement, and detector failure.

---

### B-020: Canonical Drift replay could be mutated by human-review controls

**Status:** FIXED
**Severity:** P1
**Found:** 2026-09-01

The old review controls resumed `sabziwala_drift_stepup_v1` directly. After one
approval or rejection, later presenters could load a changed verdict and lose
the deterministic STEPUP beat.

**Fix:** Canonical replay IDs are immutable at the resume endpoint. The UI calls
`POST /replays/{case_id}/review` to create a fresh checkpoint, then applies the
human decision to that disposable transaction only.

---

### B-021: Live questions could be misclassified as payment consent

**Status:** FIXED
**Severity:** P0
**Found:** 2026-09-01

The live action classifier treated any occurrence of "haan", "confirm", or
"final" as buyer acceptance. A presenter asking "freshness confirm karo" could
therefore complete a session even though cart reconstruction correctly found
no explicit agreement.

**Fix:** Consent now requires explicit acceptance, order/cart/deal confirmation,
or equivalent finalization language. Regression tests distinguish ordinary
questions from authorization, and the prepared three-turn demo remains
provisional until its final explicit accept.

---

### B-022: Provider fallback could cross the payment boundary

**Status:** FIXED
**Severity:** P0
**Found:** 2026-09-01

When negotiation degraded, the request path could still reach the ordinary
Warden graph and potentially execute payment before the response was rewritten
to STEPUP.

**Fix:** Degraded negotiation now uses the side-effect-free authorization
service, persists a fail-closed STEPUP diagnosis, and never invokes the
Razorpay order path. Its review endpoint resolves authorization only and keeps
payment execution disabled. A regression test asserts that no order call is
made on this path.
