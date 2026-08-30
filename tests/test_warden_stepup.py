import uuid
from unittest.mock import MagicMock

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from warden.graph import warden_graph as graph_module
from warden.graph.warden_graph import build_warden_graph
from warden.keys import ensure_keys_loaded, get_private_key
from warden.mandates.schema import CanonicalMandate, CartMandate, IntentMandate
from warden.mandates.signing import sign_mandate
from warden.policy.policy_config import PolicyConfig
from warden.storage.transcript_store import TranscriptStore
from warden.storage.verdict_store import VerdictStore


async def test_stepup_persists_pending_state_and_resume_executes(tmp_path, monkeypatch):
    ensure_keys_loaded()
    tx_id = f"stepup_{uuid.uuid4().hex[:12]}"
    verdict_dir = tmp_path / "verdicts"
    transcript_dir = tmp_path / "transcripts"
    store = VerdictStore(base_dir=str(verdict_dir))
    monkeypatch.setattr(graph_module, "VerdictStore", lambda: store)

    intent = IntentMandate(
        agent_id="buyer_agent_v1",
        raw_goal_text="buy wireless earbuds under 3000 rupees",
        max_price=3000,
        allowed_categories=["electronics"],
        red_lines=[],
    )
    cart = CartMandate(
        agent_id="merchant_agent_v1",
        items=[{"name": "Wireless Earbuds Pro", "price": 2499}],
        total=2499,
        category="electronics",
    )
    signed_cart = sign_mandate(cart, get_private_key("merchant_agent_v1"))
    canonical = CanonicalMandate(intent=intent, cart=signed_cart)
    transcript_store = TranscriptStore(base_dir=str(transcript_dir))
    transcript_store.reset(tx_id)

    monkeypatch.setattr(
        graph_module,
        "drift_score",
        lambda intent_text, reasonings: {
            "sudden_drop": True,
            "gradual_drift": False,
            "coherence_break": False,
            "trajectory": [0.8],
            "consecutive_coherence": [],
        },
    )

    mock_client = MagicMock()
    mock_client.create_order.return_value = {"id": "order_test_123"}
    monkeypatch.setattr("warden.execution.razorpay_client.RazorpayClient", lambda: mock_client)

    graph = build_warden_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": tx_id}}
    state = {
        "tx_id": tx_id,
        "canonical_mandate": canonical,
        "transcript": transcript_store.load(tx_id),
        "policy_config": PolicyConfig(),
    }

    interrupted = await graph.ainvoke(state, config=config)
    assert interrupted.get("__interrupt__")
    pending = store.load(tx_id)
    assert pending["verdict"] == "STEPUP"

    resumed = await graph.ainvoke(Command(resume=True), config=config)
    assert resumed["verdict"] == "PASS"
    mock_client.create_order.assert_called_once_with(amount=2499, receipt=tx_id)
    final = store.load(tx_id)
    assert final["verdict"] == "PASS"
    assert "order_test_123" in final["explanation"]
