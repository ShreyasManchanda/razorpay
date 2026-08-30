import datetime
from typing import Literal, NotRequired, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from warden.detection.constraint_checker import check_constraints
from warden.detection.drift_scorer import drift_score
from warden.detection.injection_scanner import scan_for_injection, scan_suspicious
from warden.mandates.schema import CanonicalMandate, PaymentMandate
from warden.mandates.signing import verify_mandate
from warden.policy.policy_config import PolicyConfig
from warden.policy.verdict import warden_verdict
from warden.storage.verdict_store import VerdictStore


class WardenState(TypedDict):
    tx_id: str
    canonical_mandate: CanonicalMandate
    transcript: list[dict]
    signature_valid: bool
    violations: list[str]
    drift: dict
    injection_flags: list[str]
    suspicious_flags: list[str]
    signals: dict | None
    verdict: Literal["PASS", "STEPUP", "REJECT"] | None
    explanation: str | None
    trust_score_trajectory: list[float]
    policy_config: PolicyConfig
    execution_mode: NotRequired[Literal["live", "demo"]]
    precomputed_drift: NotRequired[dict]


def signature_gate(state: WardenState) -> dict:
    mandate = state["canonical_mandate"]
    valid = verify_mandate(mandate.cart)
    return {"signature_valid": valid}


def route_signature(state: WardenState) -> list[str]:
    if not state["signature_valid"]:
        return ["reject_no_sig"]
    return ["constraint_checker", "drift_scorer", "injection_scanner"]


def constraint_checker(state: WardenState) -> dict:
    mandate = state["canonical_mandate"]
    violations = check_constraints(mandate.intent, mandate.cart)
    return {"violations": violations}


def drift_scorer(state: WardenState) -> dict:
    # Offline replay uses the detector result persisted with its source run.
    # Regular negotiations always calculate a fresh trajectory.
    precomputed_drift = state.get("precomputed_drift")
    if precomputed_drift is not None:
        return {
            "drift": precomputed_drift,
            "trust_score_trajectory": precomputed_drift.get("trajectory", []),
        }

    mandate = state["canonical_mandate"]
    buyer_reasonings = [t["reasoning"] for t in state["transcript"] if t.get("speaker") == "buyer_agent"]
    result = drift_score(mandate.intent.raw_goal_text, buyer_reasonings)
    return {
        "drift": result,
        "trust_score_trajectory": result.get("trajectory", []),
    }


def injection_scanner(state: WardenState) -> dict:
    merchant_messages = [t["message"] for t in state["transcript"] if t.get("speaker") == "merchant_agent"]
    all_flags = []
    all_soft = []
    for msg in merchant_messages:
        all_flags.extend(scan_for_injection(msg))
        all_soft.extend(scan_suspicious(msg))
    return {"injection_flags": all_flags, "suspicious_flags": all_soft}


def merge_signals(state: WardenState) -> dict:
    cart_total = state["canonical_mandate"].cart.total
    signals = {
        "violations": state.get("violations", []),
        "drift": state.get("drift", {}),
        "injection_flags": state.get("injection_flags", []),
        "suspicious_flags": state.get("suspicious_flags", []),
        "cart_total": cart_total,
    }
    return {"signals": signals}


def policy_decision(state: WardenState) -> dict:
    config = state["policy_config"]
    signals = state["signals"]
    verdict, explanation = warden_verdict(signals, config)
    return {"verdict": verdict, "explanation": explanation}


def route_verdict(state: WardenState) -> str:
    v = state["verdict"]
    if v == "PASS":
        return "execute_payment"
    if v == "STEPUP":
        return "record_stepup"
    return "write_incident"


def _persist_verdict(
    state: WardenState,
    verdict: str | None = None,
    explanation: str | None = None,
):
    VerdictStore().save(
        state["tx_id"],
        {
            "tx_id": state["tx_id"],
            "verdict": verdict or state["verdict"],
            "explanation": explanation if explanation is not None else state.get("explanation", ""),
            "signals": state.get("signals"),
            "trust_score_trajectory": state.get("trust_score_trajectory"),
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        },
    )


def record_stepup(state: WardenState) -> dict:
    """Persist pending review state before interrupt."""
    _persist_verdict(state)
    return {}


def reject_no_sig(state: WardenState) -> dict:
    explanation = "Cart mandate signature verification failed. Transaction blocked before detection."
    _persist_verdict(state, verdict="REJECT", explanation=explanation)
    return {"verdict": "REJECT", "explanation": explanation}


def execute_payment(state: WardenState) -> dict:
    from warden.execution.razorpay_client import RazorpayClient

    payment = PaymentMandate(cart_ref=state["tx_id"], amount=state["canonical_mandate"].cart.total)
    # The seeded replay uses the same execution node as a live transaction, but
    # must remain runnable without credentials or an external payment request.
    client = RazorpayClient(allow_mock=True) if state.get("execution_mode") == "demo" else RazorpayClient()
    order = client.create_order(amount=round(payment.amount), receipt=state["tx_id"])
    explanation = (state.get("explanation") or "") + f" Order created: {order['id']}."
    _persist_verdict(state, verdict="PASS", explanation=explanation)
    return {"verdict": "PASS", "explanation": explanation}


def stepup_wait(state: WardenState) -> dict:
    approved = interrupt({"tx_id": state["tx_id"], "reason": state["explanation"]})
    if approved:
        return {"verdict": "PASS"}
    explanation = "Human rejected during STEPUP review."
    return {"verdict": "REJECT", "explanation": explanation}


def route_stepup(state: WardenState) -> str:
    if state["verdict"] == "PASS":
        return "execute_payment"
    return "write_incident"


def write_incident(state: WardenState) -> dict:
    _persist_verdict(state)
    return {}


def build_warden_graph(checkpointer=None):
    graph = StateGraph(WardenState)

    graph.add_node("signature_gate", signature_gate)
    graph.add_node("reject_no_sig", reject_no_sig)
    graph.add_node("constraint_checker", constraint_checker)
    graph.add_node("drift_scorer", drift_scorer)
    graph.add_node("injection_scanner", injection_scanner)
    graph.add_node("merge_signals", merge_signals)
    graph.add_node("policy_decision", policy_decision)
    graph.add_node("record_stepup", record_stepup)
    graph.add_node("execute_payment", execute_payment)
    graph.add_node("stepup_wait", stepup_wait)
    graph.add_node("write_incident", write_incident)

    graph.set_entry_point("signature_gate")
    graph.add_conditional_edges(
        "signature_gate",
        route_signature,
        path_map=["reject_no_sig", "constraint_checker", "drift_scorer", "injection_scanner"],
    )
    for node in ["constraint_checker", "drift_scorer", "injection_scanner"]:
        graph.add_edge(node, "merge_signals")
    graph.add_edge("merge_signals", "policy_decision")
    graph.add_conditional_edges("policy_decision", route_verdict)
    graph.add_edge("record_stepup", "stepup_wait")
    graph.add_edge("reject_no_sig", END)
    graph.add_edge("execute_payment", END)
    graph.add_conditional_edges("stepup_wait", route_stepup)
    graph.add_edge("write_incident", END)

    if checkpointer is None:
        checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
