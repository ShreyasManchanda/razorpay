# Project Warden

**A detector for dishonest agent-to-agent authorization.**

Warden observes agent-to-agent payment negotiations and detects when the authorization was obtained dishonestly — via structural prompt injection in merchant free-text, or manipulative reasoning drift in the buyer agent. It produces measured precision, recall, and false-positive cost on a held-out test set.

Built for Razorpay AI Buildathon Track 02: AI Risk Manager.

## Defense-Only Statement

> AttackerAgent is a closed internal component with no external interface. It only ever targets our own Buyer/Merchant agents inside the self-play loop, purely to generate labeled test-set data and harden InjectionScanner. It is never exposed as a callable capability, never targets a third party, and produces no artifact usable to attack a system outside this project.

## Quick Start

1. Copy `.env.example` to `.env` and fill in the provider keys you have: `TOKENROUTER_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`, or `GOOGLE_API_KEY`. Add `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` (test mode) to execute payments.
2. Install: `py -3.11 -m venv .venv && .venv\Scripts\pip install -e ".[dev]"`
3. Generate keys: `.venv\Scripts\python scripts\gen_keys.py`
4. Run tests: `$env:HF_HUB_OFFLINE='1'; .venv\Scripts\python -m pytest tests/ -v`
5. Start the API from the repository root: `.venv\Scripts\python -m uvicorn warden.api.main:app --app-dir src --reload --port 8000`
6. Open the replay UI at <http://127.0.0.1:8000/ui/replay.html> in your browser.

## Architecture

- **Negotiation graph**: Buyer ↔ Merchant agent turn loop through the budget-safe provider fallback chain
- **Warden graph**: Signature gate → parallel detection (constraint, drift, injection) → merge → policy → verdict
- **Selfplay graph**: Attacker proposes payload → negotiation runs → warden evaluates → results logged

See [SPEC.md](SPEC.md) for full architecture details and [decisions.md](decisions.md) for every locked decision.

## Evaluation

Run each class as its own rate-limit-friendly batch of ten:

```powershell
.\run_clean_10.cmd
.\run_legit_10.cmd
.\run_injection_10.cmd
.\run_drift_10.cmd
```

Each command appends completed negotiations immediately. If a provider quota stops the batch, rerun the same command later; saved transaction IDs are skipped. Run these from a normal terminal with provider network access (not a sandboxed shell).

Four classes: `clean`, `legitimate-revision`, `injected`, and `gradual-drift`. Metrics reported: precision, recall, F1 for REJECT/STEPUP decisions, false-positive rate on clean + legitimate-revision, and cost-weighted score.

One command records every demo beat (clean PASS, injected REJECT, drift STEPUP + approval, policy swap, tamper check) against real Razorpay test-mode orders:

```powershell
.venv\Scripts\python scripts\demo_video.py
```

## Tech Stack

Python 3.11+, LangGraph 1.x, PyNaCl (Ed25519), sentence-transformers (local MiniLM-L6-v2), FastAPI, provider fallback across TokenRouter/OpenRouter/Groq/Gemini, Razorpay SDK (test mode).


## Quality Checks

```powershell
.\.venv\Scripts\python.exe -m ruff check src scripts tests
.\.venv\Scripts\python.exe -m ruff format --check src scripts tests
$env:HF_HUB_OFFLINE='1'; $env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m pytest tests -q
```
