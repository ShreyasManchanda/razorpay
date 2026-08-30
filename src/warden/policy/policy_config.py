from pydantic import BaseModel


class PolicyConfig(BaseModel):
    name: str = "default"
    injection_action: str = "reject"  # "reject" | "stepup" | "ignore"
    drift_action: str = "stepup"  # "reject" | "stepup" | "ignore"
    stepup_required_above: float = 5000.0
    max_trust_threshold: float = 0.3


QUICK_COMMERCE_POLICY = PolicyConfig(
    name="quick_commerce",
    injection_action="reject",
    drift_action="stepup",
    stepup_required_above=2000.0,
)

B2B_RECEIVABLES_POLICY = PolicyConfig(
    name="b2b_receivables",
    injection_action="stepup",
    drift_action="stepup",
    stepup_required_above=10000.0,
)
