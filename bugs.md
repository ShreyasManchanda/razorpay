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

(none yet)

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
**Likelihood:** Certain without v2 corroboration gate.

Words like "required", "must", "mandatory" appear legitimately in merchant policy language ("ID required", "membership required"). The over-defense negative test set (§8.3) must include these cases from day one. v2 corroboration via Gemini Flash structured output is cheap enough to run on every flagged sentence.

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

If injection patterns are tuned on data that includes held-out samples, metrics are inflated. Mitigation: deterministic hash-based split (`hash(tx_id) % 5 == 0 → holdout`) computed once and stored. Never tune patterns using holdout data. Report both train-slice and holdout-slice metrics separately.

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

The current implementation extracts items from merchant messages by checking if any word from the catalog item name appears in the message text. This can match on generic words like "wireless" or "speaker" and produce false positives. Mitigation for now: fallback to first catalog item if no matches found. Future improvement: have merchant agent return structured cart items alongside the free-text message.

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

v1 regex had 13/14 false positive rate on the benign negative set. Fixed by splitting into two tiers: hard imperatives (still high FP, mitigated by v2 corroboration gate) and suspicious patterns (0/14 FP). Suspicious tier triggers STEPUP not REJECT, giving human reviewers visibility without blocking legitimate sales.

### R-015: Gradual drift could be bypassed by keeping price low

**Severity:** P1
**Status:** FIXED

Policy layer only triggered STEPUP on gradual_drift when `cart_total > stepup_required_above`. Attacker could manipulate buyer into accepting a low-price item outside original intent without triggering any alert. Fixed: gradual_drift always STEPUPs regardless of amount.

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

**Fix:** Merchant agents now return structured `selected_items` (exact catalog names actually agreed to); `finalize_cart` uses them first and keeps substring matching only as legacy fallback. Shared extraction helper reused by self-play. Pre-fix test-set row archived to `data/eval/testset_pre_cartfix.jsonl`.

---

### B-012: Policy swap endpoint read a stale src/data directory

**Status:** FIXED
**Severity:** P2
**Found:** 2026-08-25

`POST /policy/swap` hand-built its verdicts path from `__file__` and landed on `src/data/verdicts` — the pre-B-004 layout. The missing-directory guard masked the bug, so the endpoint always returned an empty result set instead of re-scoring stored signals.

**Fix:** The route now iterates `VerdictStore.base_dir` directly, guaranteeing it reads the same store every other endpoint uses.
