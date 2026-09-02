# Project Warden

Project Warden is a defense layer for agent-to-agent commerce. It evaluates
whether a proposed payment was reached safely before an order is created.

Warden verifies merchant-signed cart integrity, checks hard purchase
constraints, detects prompt injection and buyer-reasoning drift, and combines
those signals into one of three outcomes:

- **PASS** — authorization is safe to continue.
- **STEPUP** — a human review is required.
- **REJECT** — the payment must be blocked.

The project includes a FastAPI service, an MCP authorization tool, a local
HTML interface, deterministic evaluation fixtures, and an optional Razorpay
test-mode execution boundary.

## Getting started

Requirements: Python 3.11+.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
Copy-Item .env.example .env
.venv\Scripts\python scripts/gen_keys.py
```

Run the test suite:

```powershell
$env:HF_HUB_OFFLINE='1'
$env:PYTHONPATH='src'
.venv\Scripts\python -m pytest tests -q
```

Start the API:

```powershell
.venv\Scripts\python -m uvicorn warden.api.main:app --app-dir src --reload --port 8000
```

Then open <http://127.0.0.1:8000/>.

## How it works

1. A signed cart and negotiation transcript are submitted for authorization.
2. The signature gate verifies the cart before any detector or payment action.
3. Constraint, drift, and injection detectors run in parallel.
4. Policy combines their signals into PASS, STEPUP, or REJECT.
5. Only an authorized request may proceed to the payment integration.

The same side-effect-free authorization service powers both the HTTP API and
the narrow MCP tool, `warden_authorize_payment`.

## Evaluation

The bounded `eval-v2` benchmark is deterministic and runs against local
fixtures:

```powershell
.venv\Scripts\python scripts/run_eval_v2.py
```

The resulting report is stored at
[`data/eval_v2/report.json`](data/eval_v2/report.json). It is a capability
measurement on a synthetic corpus, not a production safety or performance
guarantee.

## Project layout

```text
src/warden/       Core agents, detectors, policy, API, MCP, and storage
scripts/          Key generation, evaluation, and development utilities
tests/            Unit, integration, and resilience tests
data/             Versioned fixtures and evaluation artifacts
ui/               Build-free browser interface
```

See [`SPEC.md`](SPEC.md) for the architecture and contracts,
[`PRODUCT.md`](PRODUCT.md) for product scope, and
[`WARDEN_FRONTEND_PRD.md`](WARDEN_FRONTEND_PRD.md) for the UI requirements.

## Security and scope

Never commit `.env`, private keys, or production credentials. The included
attacker component is an internal, defense-only test fixture used to generate
labeled data for detector hardening; it has no external attack interface.

Payment execution is intentionally isolated behind the authorization boundary
and should be configured only with Razorpay test credentials during local
development.

## License

No license has been declared yet.
