"""
Video-prep script: runs every beat of the 5-minute pitch in one command.

Beats:
  1. Clean sabziwala negotiation (Hinglish scenario)
  2. Clean electronics PASS -> real Razorpay TEST-MODE order created
  3. Injected attack -> REJECT with plain-English explanation
  4. Gradual-drift attack -> STEPUP -> resume approved -> payment executes
  5. Policy swap: same signals, different policy, verdict flips
  6. Tampered cart -> signature gate REJECT before detection runs

Usage:
    .venv\\Scripts\\python.exe scripts\\demo_video.py [beat ...]

Run with no arguments for all beats. Each beat prints a clear section header
for screen recording.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from dotenv import load_dotenv

load_dotenv()

from httpx import ASGITransport, AsyncClient  # noqa: E402

LINE = "=" * 64


async def request_json(client, method: str, path: str, **kwargs):
    """Fail loudly on API errors so a recording never shows null verdicts."""

    resp = await client.request(method, path, **kwargs)
    if resp.status_code >= 400:
        detail = resp.text[:300]
        raise RuntimeError(f"{method} {path} returned HTTP {resp.status_code}: {detail}")
    try:
        return resp.json()
    except ValueError as exc:
        raise RuntimeError(f"{method} {path} returned non-JSON content") from exc


def header(title):
    print(f"\n{LINE}\n{title}\n{LINE}")


def print_turns(turns, max_msg=160):
    for t in turns:
        speaker = "BUYER " if "buyer" in t.get("speaker", "") else "MERCHANT"
        print(f"  {speaker} [{t.get('action', '')}] {t.get('message', '')[:max_msg]}")
        items = t.get("selected_items")
        if items:
            print(f"         selected_items: {items}")


def print_verdict(data):
    print(f"  verdict   : {data.get('verdict')}")
    print(f"  status    : {data.get('status', 'final')}")
    traj = data.get("trust_score_trajectory") or []
    if traj:
        print(f"  trust     : {[round(x, 3) for x in traj]}")
    explanation = data.get("explanation", "")
    if explanation:
        print(f"  why       : {explanation[:220]}")


async def beat_clean_sabziwala(client):
    header("BEAT 1 — CLEAN RUN (Sabziwala vs Indian Mom, Hinglish)")
    data = await request_json(
        client,
        "POST",
        "/negotiate",
        json={
            "intent_text": "Buy tamatar aur pyaz under 150 rupees total, fresh quality only",
            "max_price": 150,
            "allowed_categories": ["vegetables"],
            "red_lines": ["no stale items"],
            "scenario": "sabziwala_vs_mom",
        },
    )
    tx_id = data.get("tx_id")
    print_verdict(data)
    transcript = await request_json(client, "GET", f"/transcripts/{tx_id}")
    print("\n  transcript:")
    print_turns(transcript)
    return tx_id


async def beat_clean_pass_payment(client):
    header("BEAT 2 — CLEAN ELECTRONICS PASS -> RAZORPAY TEST ORDER")
    data = await request_json(
        client,
        "POST",
        "/negotiate",
        json={
            "intent_text": "buy wireless earbuds under 3000 rupees",
            "max_price": 3000,
            "allowed_categories": ["electronics"],
            "red_lines": ["no subscriptions"],
            "scenario": "electronics_store",
        },
    )
    print_verdict(data)
    tx_id = data.get("tx_id")
    if data.get("verdict") == "PASS":
        vd = await request_json(client, "GET", f"/verdicts/{tx_id}")
        print(f"  order line: {vd.get('explanation', '')[-120:]}")
    return tx_id


async def beat_injected(client):
    header("BEAT 3 — INJECTED CATALOG ATTACK -> REJECT")
    data = await request_json(
        client,
        "POST",
        "/negotiate",
        json={
            "intent_text": "buy wireless earbuds under 3000 rupees",
            "max_price": 3000,
            "allowed_categories": ["electronics"],
            "red_lines": [],
            "attack_type": "injection",
            "scenario": "electronics_store",
        },
    )
    print_verdict(data)
    return data.get("tx_id")


async def beat_drift_stepup_resume(client):
    header("BEAT 4 — GRADUAL DRIFT -> STEPUP -> HUMAN APPROVES -> PAYMENT")
    data = await request_json(
        client,
        "POST",
        "/negotiate",
        json={
            "intent_text": "buy wireless earbuds under 3000 rupees",
            "max_price": 3000,
            "allowed_categories": ["electronics"],
            "red_lines": [],
            "attack_type": "gradual_drift",
            "scenario": "electronics_store",
        },
    )
    tx_id = data.get("tx_id")
    print_verdict(data)

    if data.get("status") != "awaiting_approval":
        print("  (run did not pause for review — nothing to resume)")
        return tx_id

    print(f"\n  resuming {tx_id} with approval=TRUE ...")
    resume = await request_json(client, "POST", f"/stepup/{tx_id}/resume", json={"approved": True})
    print(f"  post-resume verdict: {resume.get('verdict')}")
    v = await request_json(client, "GET", f"/verdicts/{tx_id}")
    print(f"  final order line: {v.get('explanation', '')[-140:]}")
    return tx_id


async def beat_policy_swap(client):
    header("BEAT 5 — POLICY SWAP (same signals, different risk appetite)")
    quick = await request_json(client, "POST", "/policy/swap", json={"policy_name": "quick_commerce"})
    b2b = await request_json(client, "POST", "/policy/swap", json={"policy_name": "b2b_receivables"})
    q = quick.get("results", [])
    b = b2b.get("results", [])
    flips = [
        {"tx_id": row["tx_id"], "quick_commerce": row["new"], "b2b": brow["new"]}
        for row, brow in zip(q, b, strict=False)
        if row["tx_id"] == brow["tx_id"] and row["new"] != brow["new"]
    ]
    print(f"  transactions re-scored : {len(q)}")
    print(f"  verdict flips          : {len(flips)}")
    for f in flips[:5]:
        print(f"    {f['tx_id']}: quick_commerce={f['quick_commerce']} vs b2b={f['b2b']}")


async def beat_tamper_check(client):
    header("BEAT 6 — MANDATE TAMPER CHECK (signature gate fires first)")
    from warden.graph.warden_graph import build_warden_graph
    from warden.keys import ensure_keys_loaded
    from warden.mandates.schema import CanonicalMandate, IntentMandate
    from warden.policy.policy_config import PolicyConfig

    ensure_keys_loaded()
    intent = IntentMandate(
        agent_id="buyer_agent_v1",
        raw_goal_text="buy wireless earbuds under 3000 rupees",
        max_price=3000,
        allowed_categories=["electronics"],
        red_lines=[],
    )
    # A cart that was never signed by anyone — attacker-modified payload.
    canonical = CanonicalMandate(
        intent=intent,
        cart={
            "agent_id": "merchant_agent_v1",
            "items": [{"name": "Wireless Earbuds Pro", "price": 1}],
            "total": 1,
            "category": "electronics",
            "signature": None,
        },
    )
    graph = build_warden_graph()
    result = await graph.ainvoke(
        {
            "tx_id": "tamper_demo",
            "canonical_mandate": canonical,
            "transcript": [],
            "policy_config": PolicyConfig(),
        },
        config={"configurable": {"thread_id": "tamper_demo"}},
    )
    print(f"  signature_valid: {result.get('signature_valid')}")
    print(f"  verdict        : {result.get('verdict')}")
    print(f"  why            : {result.get('explanation')}")


BEATS = {
    "clean-sabziwala": beat_clean_sabziwala,
    "clean-pass": beat_clean_pass_payment,
    "injected": beat_injected,
    "drift-stepup": beat_drift_stepup_resume,
    "policy-swap": beat_policy_swap,
    "tamper": beat_tamper_check,
}


async def main():
    requested = sys.argv[1:] or list(BEATS)
    unknown = [r for r in requested if r not in BEATS]
    if unknown:
        raise SystemExit(f"Unknown beats: {unknown}. Available: {list(BEATS)}")

    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://test", timeout=300) as client:
        print(LINE)
        print("PROJECT WARDEN — VIDEO PREP")
        print(f"beats: {requested}")
        print(LINE)
        for name in requested:
            try:
                await BEATS[name](client)
            except Exception as exc:
                print(f"  !! beat '{name}' failed: {type(exc).__name__}: {exc}")

    header("DONE — replay any tx at http://localhost:8000/ui/replay.html")


def _build_app():
    from warden.api.main import app

    return app


if __name__ == "__main__":
    asyncio.run(main())
