import json
import os
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "src"))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pydantic import BaseModel, Field

from warden.scenarios.replay_cases import DEFAULT_SCENARIO_ID, load_hero_replay_cases, seed_hero_replay_cases

warden_checkpointer = MemorySaver()
DEMO_STEPUP_TX_ID = "demo_stepup_drift_v1"
DEMO_STEPUP_SOURCE_TX_ID = "eval_gradual-drift_5_e4da3b"
DEMO_STEPUP_SOURCE_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "transcripts" / f"{DEMO_STEPUP_SOURCE_TX_ID}.json"
)
DEMO_STEPUP_SOURCE_VERDICT_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "verdicts" / f"{DEMO_STEPUP_SOURCE_TX_ID}.json"
)
DEMO_INJECTION_TX_ID = "demo_injection_reject_v1"
DEMO_INJECTION_SOURCE_PATH = Path(__file__).resolve().parents[3] / "data" / "fixtures" / f"{DEMO_INJECTION_TX_ID}.json"
HERO_REPLAY_IDS = {case["label"]: case["id"] for case in load_hero_replay_cases()}


async def ensure_hero_replays() -> None:
    await seed_hero_replay_cases(warden_checkpointer)


async def ensure_demo_stepup() -> None:
    """Create a resumable, deterministic review case for the replay UI.

    This deliberately runs the ordinary Warden graph instead of writing a
    fixture verdict. It copies the stored gradual-drift transcript unchanged,
    reuses that run's persisted detector output, and applies the production
    graph and default policy to a corrected safe cart before storing the
    interrupt checkpoint under the stable demo transaction id.
    """
    from warden.graph.warden_graph import build_warden_graph
    from warden.keys import get_private_key
    from warden.mandates.schema import CanonicalMandate, CartMandate, IntentMandate
    from warden.mandates.signing import sign_mandate
    from warden.policy.policy_config import PolicyConfig
    from warden.storage.transcript_store import TranscriptStore
    from warden.storage.verdict_store import VerdictStore

    _ensure_keys()
    if not DEMO_STEPUP_SOURCE_PATH.is_file() or not DEMO_STEPUP_SOURCE_VERDICT_PATH.is_file():
        raise RuntimeError("Demo source transcript or verdict is missing")
    transcript = json.loads(DEMO_STEPUP_SOURCE_PATH.read_text(encoding="utf-8"))
    source_verdict = json.loads(DEMO_STEPUP_SOURCE_VERDICT_PATH.read_text(encoding="utf-8"))
    source_drift = source_verdict.get("signals", {}).get("drift")
    if not source_drift or not source_drift.get("sudden_drop"):
        raise RuntimeError("Demo source does not contain the required sudden-drift signal")
    intent = IntentMandate(
        agent_id="buyer_agent_v1",
        raw_goal_text="buy wireless earbuds under 3000 rupees",
        max_price=3000,
        allowed_categories=["electronics"],
        red_lines=["no subscriptions"],
    )
    cart = CartMandate(
        agent_id="merchant_agent_v1",
        items=[{"name": "Wireless Earbuds Pro", "price": 2499}],
        total=2499,
        category="electronics",
    )
    canonical = CanonicalMandate(intent=intent, cart=sign_mandate(cart, get_private_key("merchant_agent_v1")))

    transcript_store = TranscriptStore()
    transcript_store.reset(DEMO_STEPUP_TX_ID)
    for turn in transcript:
        transcript_store.append_turn(DEMO_STEPUP_TX_ID, turn)

    graph = build_warden_graph(checkpointer=warden_checkpointer)
    result = await graph.ainvoke(
        {
            "tx_id": DEMO_STEPUP_TX_ID,
            "canonical_mandate": canonical,
            "transcript": transcript,
            "policy_config": PolicyConfig(),
            "execution_mode": "demo",
            "precomputed_drift": source_drift,
        },
        config={"configurable": {"thread_id": DEMO_STEPUP_TX_ID}},
    )
    pending = VerdictStore().load(DEMO_STEPUP_TX_ID)
    if not result.get("__interrupt__") or pending is None or pending.get("verdict") != "STEPUP":
        raise RuntimeError("Demo STEPUP case did not reach a persisted review interrupt")


async def ensure_demo_injection_reject() -> None:
    """Create a deterministic InjectionScanner replay case for the hero."""
    from warden.graph.warden_graph import build_warden_graph
    from warden.keys import get_private_key
    from warden.mandates.schema import CanonicalMandate, CartMandate, IntentMandate
    from warden.mandates.signing import sign_mandate
    from warden.policy.policy_config import PolicyConfig
    from warden.storage.transcript_store import TranscriptStore
    from warden.storage.verdict_store import VerdictStore

    _ensure_keys()
    if not DEMO_INJECTION_SOURCE_PATH.is_file():
        raise RuntimeError(f"Injection demo source transcript is missing: {DEMO_INJECTION_SOURCE_PATH}")
    transcript = json.loads(DEMO_INJECTION_SOURCE_PATH.read_text(encoding="utf-8"))
    intent = IntentMandate(
        agent_id="buyer_agent_v1",
        raw_goal_text="buy wireless earbuds under 3000 rupees",
        max_price=3000,
        allowed_categories=["electronics"],
        red_lines=["no subscriptions"],
    )
    cart = CartMandate(
        agent_id="merchant_agent_v1",
        items=[{"name": "Wireless Earbuds Pro", "price": 2499}],
        total=2499,
        category="electronics",
    )
    canonical = CanonicalMandate(intent=intent, cart=sign_mandate(cart, get_private_key("merchant_agent_v1")))

    transcript_store = TranscriptStore()
    transcript_store.reset(DEMO_INJECTION_TX_ID)
    for turn in transcript:
        transcript_store.append_turn(DEMO_INJECTION_TX_ID, turn)

    graph = build_warden_graph(checkpointer=warden_checkpointer)
    result = await graph.ainvoke(
        {
            "tx_id": DEMO_INJECTION_TX_ID,
            "canonical_mandate": canonical,
            "transcript": transcript,
            "policy_config": PolicyConfig(),
        },
        config={"configurable": {"thread_id": DEMO_INJECTION_TX_ID}},
    )
    stored = VerdictStore().load(DEMO_INJECTION_TX_ID)
    if result.get("verdict") != "REJECT" or stored is None or not stored.get("signals", {}).get("injection_flags"):
        raise RuntimeError("Injection demo case did not produce a persisted scanner rejection")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await ensure_hero_replays()
    yield


app = FastAPI(title="Project Warden", version="0.1.0", lifespan=lifespan)

UI_DIR = Path(__file__).resolve().parents[3] / "ui"
SCENE_PATH = Path(__file__).resolve().parents[3] / "scene.png"
app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")


# --- Request models ---


class NegotiateRequest(BaseModel):
    intent_text: str
    max_price: float
    red_lines: list[str] = Field(default_factory=list)
    allowed_categories: list[str] = Field(default_factory=lambda: ["electronics"])
    attack_type: Literal["injection", "gradual_drift"] | None = None
    scenario: str = DEFAULT_SCENARIO_ID


class PolicySwapRequest(BaseModel):
    policy_name: str  # "quick_commerce" | "b2b_receivables"


class StepupResumeRequest(BaseModel):
    approved: bool


# --- Helpers ---


def _ensure_keys():
    from warden.keys import ensure_keys_loaded

    ensure_keys_loaded()


# --- Routes ---


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/scene.png", include_in_schema=False)
def scene_image():
    """Serve the replay scene asset without exposing arbitrary filesystem paths."""
    if not SCENE_PATH.is_file():
        raise HTTPException(404, "Scene image is not available")
    return FileResponse(SCENE_PATH, media_type="image/png")


@app.get("/scenarios")
def list_available_scenarios():
    from warden.scenarios.loader import list_scenarios, load_scenario

    result = []
    for sid in list_scenarios():
        s = load_scenario(sid)
        result.append(
            {
                "id": s.id,
                "display_name": s.display_name,
                "tagline": s.tagline,
                "is_default": s.id == DEFAULT_SCENARIO_ID,
            }
        )
    return result


@app.post("/negotiate")
async def negotiate(req: NegotiateRequest):
    """Full pipeline: negotiation → warden detection → verdict."""
    from warden.graph.negotiation_graph import build_negotiation_graph
    from warden.graph.warden_graph import build_warden_graph
    from warden.keys import get_private_key
    from warden.mandates.schema import CanonicalMandate, IntentMandate
    from warden.mandates.signing import sign_mandate
    from warden.policy.policy_config import PolicyConfig
    from warden.scenarios.loader import load_scenario
    from warden.storage.transcript_store import TranscriptStore
    from warden.storage.verdict_store import VerdictStore

    _ensure_keys()
    scenario = load_scenario(req.scenario)
    tx_id = uuid.uuid4().hex[:16]

    intent = IntentMandate(
        agent_id="buyer_agent_v1",
        raw_goal_text=req.intent_text,
        max_price=req.max_price,
        allowed_categories=req.allowed_categories,
        red_lines=req.red_lines,
    )

    # Phase A: negotiation
    neg_graph = build_negotiation_graph()
    neg_state = {
        "tx_id": tx_id,
        "intent_mandate": intent,
        "turns": [],
        "cart_mandate": None,
        "turn_count": 0,
        "max_turns": 6,
        "attacker_payload": None,
        "attack_type": req.attack_type,
        "scenario": scenario,
    }
    neg_result = await neg_graph.ainvoke(neg_state)
    cart = neg_result.get("cart_mandate")
    if cart is None:
        raise HTTPException(500, "Negotiation failed to produce a cart")

    # Sign the cart with the merchant key
    signed_cart = sign_mandate(cart, get_private_key("merchant_agent_v1"))

    # Phase B: warden detection
    transcript = TranscriptStore().load(tx_id)
    canonical = CanonicalMandate(intent=intent, cart=signed_cart)
    config = PolicyConfig(**scenario.policy_overrides.model_dump())
    ward_graph = build_warden_graph(checkpointer=warden_checkpointer)
    ward_result = await ward_graph.ainvoke(
        {
            "tx_id": tx_id,
            "canonical_mandate": canonical,
            "transcript": transcript,
            "policy_config": config,
        },
        config={"configurable": {"thread_id": tx_id}},
    )

    verdict = ward_result.get("verdict")
    explanation = ward_result.get("explanation", "")
    if not verdict:
        # An interrupted graph returns the interrupt payload rather than the node's pending state.
        pending = VerdictStore().load(tx_id)
        verdict = pending.get("verdict", "UNKNOWN") if pending else "UNKNOWN"
        explanation = pending.get("explanation", "") if pending else ""
    response = {
        "tx_id": tx_id,
        "verdict": verdict,
        "explanation": explanation,
        "trust_score_trajectory": ward_result.get("trust_score_trajectory"),
    }
    if verdict == "STEPUP":
        response["status"] = "awaiting_approval"
    return response


@app.get("/transcripts/{tx_id}")
def get_transcript(tx_id: str):
    from warden.storage.transcript_store import TranscriptStore

    store = TranscriptStore()
    if not store.exists(tx_id):
        raise HTTPException(404, f"No transcript for {tx_id}")
    return store.load(tx_id)


@app.get("/verdicts/{tx_id}")
def get_verdict(tx_id: str):
    from warden.storage.verdict_store import VerdictStore

    store = VerdictStore()
    result = store.load(tx_id)
    if result is None:
        raise HTTPException(404, f"No verdict for {tx_id}")
    return result


@app.post("/policy/swap")
async def policy_swap(req: PolicySwapRequest):
    """Re-run policy_decision on an existing tx_id's stored signals against a different policy."""
    from warden.policy.policy_config import (
        B2B_RECEIVABLES_POLICY,
        QUICK_COMMERCE_POLICY,
    )
    from warden.policy.verdict import warden_verdict
    from warden.storage.verdict_store import VerdictStore

    policies = {"quick_commerce": QUICK_COMMERCE_POLICY, "b2b_receivables": B2B_RECEIVABLES_POLICY}
    config = policies.get(req.policy_name)
    if config is None:
        raise HTTPException(400, f"Unknown policy: {req.policy_name}. Available: {list(policies.keys())}")

    store = VerdictStore()
    all_verdicts = []
    if os.path.exists(store.base_dir):
        for fname in os.listdir(store.base_dir):
            if not fname.endswith(".json"):
                continue
            data = store.load(fname.replace(".json", ""))
            if data and data.get("signals"):
                new_verdict, _new_explanation = warden_verdict(data["signals"], config)
                all_verdicts.append({"tx_id": data["tx_id"], "old": data.get("verdict"), "new": new_verdict})
    return {"policy": req.policy_name, "results": all_verdicts}


@app.post("/stepup/{tx_id}/resume")
async def stepup_resume(tx_id: str, req: StepupResumeRequest):
    """Resume the interrupted Warden thread with the reviewer's decision."""
    from warden.graph.warden_graph import build_warden_graph
    from warden.storage.verdict_store import VerdictStore

    store = VerdictStore()
    existing = store.load(tx_id)
    if existing is None:
        raise HTTPException(404, f"No paused transaction {tx_id}")
    if existing.get("verdict") != "STEPUP":
        raise HTTPException(409, f"Transaction {tx_id} is not awaiting review")

    graph = build_warden_graph(checkpointer=warden_checkpointer)
    try:
        result = await graph.ainvoke(
            Command(resume=req.approved),
            config={"configurable": {"thread_id": tx_id}},
        )
    except Exception as exc:
        raise HTTPException(409, "Paused thread is unavailable; restart review from a new negotiation") from exc

    return {
        "tx_id": tx_id,
        "verdict": result.get("verdict", existing["verdict"]),
        "explanation": result.get("explanation", existing.get("explanation", "")),
    }


@app.get("/selfplay/report")
def selfplay_report():
    from warden.eval.metrics import compute_precision_recall_f1
    from warden.eval.testset_builder import TestSetBuilder

    builder = TestSetBuilder()
    entries = builder.load_all()
    y_true = [1 if e.get("label") in ("injected", "gradual-drift") else 0 for e in entries]
    y_pred = [1 if e.get("verdict") in ("REJECT", "STEPUP") else 0 for e in entries]
    metrics = compute_precision_recall_f1(y_true, y_pred)
    by_round = {}
    by_class = {}
    for e in entries:
        r = e.get("round", "?")
        by_round[r] = by_round.get(r, {"total": 0, "caught": 0})
        by_round[r]["total"] += 1
        caught = e.get("verdict") in ("REJECT", "STEPUP")
        if caught:
            by_round[r]["caught"] += 1
        label = e.get("label", "unknown")
        stats = by_class.setdefault(label, {"total": 0, "caught": 0})
        stats["total"] += 1
        if caught:
            stats["caught"] += 1
    for stats in by_class.values():
        stats["rate"] = stats["caught"] / stats["total"] if stats["total"] else 0.0
    return {
        "metrics": metrics,
        "metric_scope": "transaction_outcome",
        "by_round": by_round,
        "by_class": by_class,
        "n_entries": len(entries),
    }
