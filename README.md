# Project Warden

**A trust layer for agent-to-agent commerce.**

Warden sits between an agent negotiation and a payment tool. It verifies the merchant-signed cart, detects hard constraint violations, structural prompt injection, and buyer-reasoning drift, then returns PASS, STEPUP, or REJECT before payment is allowed to move. It complements payment protocols that prove who signed a transaction by evaluating how that authorization was obtained.

Built for Razorpay AI Buildathon Track 02: AI Risk Manager.

## Defense-Only Statement

> AttackerAgent is a closed internal component with no external interface. It only ever targets our own Buyer/Merchant agents inside the self-play loop, purely to generate labeled test-set data and harden InjectionScanner. It is never exposed as a callable capability, never targets a third party, and produces no artifact usable to attack a system outside this project.

## Quick Start

1. Copy `.env.example` to `.env` and fill in the provider keys you have: `TOKENROUTER_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`, or `GOOGLE_API_KEY`. Add `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` (test mode) to execute payments. Never commit `.env` or production credentials.
2. Install: `py -3.11 -m venv .venv && .venv\Scripts\pip install -e ".[dev]"`
3. Generate keys: `.venv\Scripts\python scripts\gen_keys.py`
4. Run tests: `$env:HF_HUB_OFFLINE='1'; .venv\Scripts\python -m pytest tests/ -v`
5. Start the API from the repository root: `.venv\Scripts\python -m uvicorn warden.api.main:app --app-dir src --reload --port 8000`
6. Open the presenter UI at <http://127.0.0.1:8000/> in your browser.

## Live Demo Flow

The page verifies that `sabziwala_vs_mom` is the API default before rendering
the hero. Use the six-step presenter rail for clean PASS, injection REJECT,
drift STEPUP, policy swap, tamper/MCP proof, and evaluation. Each stored case
autoplays immutable server-derived exchange frames; buyer and merchant turns,
candidate cart, agreement provenance, trust path, parallel detectors, policy,
verdict, and payment boundary update in one synchronized Live Studio.

Choose **Talk live** to start a bounded session, type natural free-form buyer
messages, or run the prepared conversation. Transactional language is grounded
locally: item aliases, mixed gram/kilo quantities, add/remove/substitute,
bargaining, catalog, freshness, and explicit consent update a structured active
offer. The opening and common market/payment questions are answered locally for
demo responsiveness. Other open-ended questions use the configured provider
chain without being allowed to mutate that offer. If every provider fails, a
labeled deterministic fallback preserves the cart and redirects unsupported
questions instead of fabricating a response. `reply_source` reports `provider`,
`rules`, or `fallback` on every snapshot. The local embedding model warms during
API startup so the first trust update does not pay cold-start latency.

Before the buyer accepts a named cart, the API returns `ANALYSIS`: cart checks
are pending, not treated as a final empty-cart rejection. Live drift evaluates a
context-preserving buyer state rather than misclassifying terse chat fragments
as complete agent reasoning. Hard injection or explicit intent abandonment can
still pause/block immediately. After agreement, the normal signature,
constraint, drift, injection, and policy path returns PASS, STEPUP, or REJECT.
Live review resolves once but never creates a Razorpay order; `/negotiate` owns
payment execution. Questions containing words such as "confirm" or "haan" are
not treated as consent; the session completes only on explicit cart/order
acceptance.

Live API contract:

- `GET /replays/{case_id}` returns immutable exchange frames with transcript,
  candidate cart, agreement evidence, detector state, trust, verdict phase,
  and payment boundary.
- `POST /replays/{case_id}/review` creates a disposable STEPUP checkpoint;
  canonical replay transactions cannot be resumed or mutated.
- `POST /live/sessions` starts a session (`scenario`, plus optional intent and
  mandate constraints).
- `POST /live/sessions/{session_id}/turns` accepts a presenter `message` and
  advances the negotiation by one buyer/merchant exchange.
- `GET /live/sessions/{session_id}` returns the current transcript, signal
  bundle, verdict, cart, status, and execution mode.
- `POST /live/sessions/{session_id}/review` resolves a STEPUP exactly once.
- `POST /tamper/check` signs a Rs.90 cart, modifies its total, and proves the
  signature gate returns REJECT before detectors or payment.
- `GET /evaluation/report` serves the validated immutable eval-v2 artifact.
  Legacy `/selfplay/report` remains available for the original provider corpus.

## MCP Integration

Warden exposes one deliberately narrow MCP tool:
`warden_authorize_payment(intent, signed_cart, transcript, policy_name)`. It
uses the same side-effect-free authorization service as the live API and
returns the signature state, detector bundle, trust trajectory, explanation,
and PASS/STEPUP/REJECT verdict. It never creates an order, resolves human
review, registers new keys, or exposes the attacker component.

Run the real stdio round trip:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python scripts\mcp_demo.py
```

This is an MCP integration surface, not a claim of full A2A protocol
conformance. External merchant agents must use a public key already registered
with Warden.

## Architecture

- **Negotiation graph**: Buyer ↔ Merchant agent turn loop through the budget-safe provider fallback chain
- **Warden graph**: Signature gate → parallel detection (constraint, drift, injection) → merge → policy → verdict
- **Selfplay graph**: Attacker proposes a bounded payload → negotiation runs →
  Warden evaluates → delivered merchant evidence is logged → an optional
  validated pattern proposal is gated before versioned activation

See [SPEC.md](SPEC.md) for full architecture details and [decisions.md](decisions.md) for every locked decision.

Detector hardening is offline and reviewable: self-play may propose a pattern
from delivered merchant evidence, but the validated registry only activates a
compiled, deduplicated candidate that matches the miss and passes frozen
benign-control checks. This is a bounded one-round invocation, not online
learning or automatic holdout tuning.

## Evaluation

The authoritative bounded benchmark is `eval-v2`, not the original 40-row
provider corpus. It uses 80 deterministic cases, 78 in-scope cases, paired
controls, provenance-verified attacks, and a deterministic grouped holdout of
22 rows. The holdout excludes the 16-row blind-challenge tranche entirely;
the report records the overlap check and keeps constraint/tamper metrics
separate. Multilingual injection remains an out-of-scope probe.

Run it offline with the cached embedding model:

```powershell
.venv\Scripts\python scripts\run_eval_v2.py
```

Current bounded results are published verbatim in `data/eval_v2/report.json`:
semantic precision 100%, overall recall 71.4%, grouped-holdout recall 100%,
and the untouched blind-challenge tranche at 25% (2/8). The report also shows
operational PASS/STEPUP/REJECT outcomes, unscored dependency failures, and a
cost model that weights a false PASS more heavily than review friction.
Constraints and signature tampering are reported independently. These are
capability measurements on a small synthetic corpus, not production-
prevalence estimates or a release guarantee; the blind misses remain visible
and are the priority for further hardening.

Run each class as its own rate-limit-friendly batch of ten:

```powershell
.\run_clean_10.cmd
.\run_legit_10.cmd
.\run_injection_10.cmd
.\run_drift_10.cmd
```

Each command appends completed negotiations immediately. If a provider quota stops the batch, rerun the same command later; saved transaction IDs are skipped. Run these from a normal terminal with provider network access (not a sandboxed shell).

Four classes: `clean`, `legitimate-revision`, `injected`, and `gradual-drift`. A
transcript is not a semantic positive merely because the attacker mode was
requested: the payload must be surfaced (or its behaviour independently
observed), and every row records that provenance. Cart reconstruction requires
explicit buyer agreement; suggestions, merchant-only selections, and empty
transcripts produce an `agreement_ambiguous` constraint violation and fail
closed. Reports use a deterministic stratified holdout with every label
represented. Constraint-only catches are reported separately from injection
and drift catches, with REJECT/STEPUP counts and unverified legacy rows shown
explicitly. The stored corpus is the benchmark domain; live sabziwala sessions
are a qualitative transfer demo and are not mixed into these numbers. The
offline paired fixtures in `warden.eval.fixtures` keep intent, catalog, cart,
and budget constant so semantic detectors cannot win via price shortcuts.

One command exercises the backend demo beats (clean PASS, injected REJECT,
drift STEPUP + approval, policy swap, tamper check) against Razorpay test-mode
order creation when test credentials are configured:

```powershell
.venv\Scripts\python scripts\demo_video.py
```

## Tech Stack

Python 3.11+, LangGraph 1.x, PyNaCl (Ed25519), sentence-transformers (local MiniLM-L6-v2), FastAPI, MCP Python SDK, provider fallback across TokenRouter/OpenRouter/Groq/Gemini, Razorpay SDK (test-mode Orders API), and a build-free HTML/CSS/JS interface with GSAP motion.

## Five-Minute Judge Path

1. **0:00 - Thesis:** signatures prove identity and payload integrity; Warden evaluates negotiation honesty.
2. **0:30 - Clean PASS:** let the replay autoplay; show explicit buyer agreement, healthy trust, four clear signals, and the guarded demo-order boundary.
3. **1:15 - Injection REJECT:** reveal the highlighted agent-directed imperative, InjectionScanner match, and blocked payment.
4. **2:10 - Drift STEPUP:** watch the trust trajectory cross 0.45, then use the isolated review workspace to explain why ambiguity goes to a person.
5. **3:10 - Policy + tamper:** rescore the same injection bundle from REJECT to STEPUP, then modify a signed cart and fail before detection.
6. **4:15 - Integration + evidence:** name the single MCP authorization tool, disclose the eval-v2 bounded results and confidence intervals, explain the blind-challenge misses, and close on defense-only scope.


## Quality Checks

```powershell
.\.venv\Scripts\python.exe -m ruff check src scripts tests
.\.venv\Scripts\python.exe -m ruff format --check src scripts tests
$env:HF_HUB_OFFLINE='1'; $env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m pytest tests -q
```
