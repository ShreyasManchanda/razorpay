from warden.policy.policy_config import PolicyConfig


class PolicyDecisionInput:
    def __init__(self, signals: dict, policy_config: PolicyConfig):
        self.signals = signals
        self.policy_config = policy_config


def _explain(*parts) -> str:
    return " ".join(str(p) for p in parts)


def warden_verdict(signals: dict, policy_config: PolicyConfig) -> tuple[str, str]:
    violations = signals.get("violations", [])
    if violations:
        return "REJECT", _explain("Constraint violations:", violations)

    injection_flags = signals.get("injection_flags", [])
    if injection_flags:
        if policy_config.injection_action == "reject":
            return "REJECT", _explain("Merchant message contained agent-directed imperative:", injection_flags)
        if policy_config.injection_action == "stepup":
            return "STEPUP", _explain("Possible injection detected, human confirmation required:", injection_flags)

    drift = signals.get("drift", {})
    if drift.get("sudden_drop"):
        return "STEPUP", _explain("Reasoning discontinuity detected.", drift.get("trajectory"))
    if drift.get("coherence_break"):
        return "STEPUP", _explain(
            "Buyer reasoning became internally inconsistent across turns.", drift.get("consecutive_coherence")
        )
    if drift.get("gradual_drift"):
        return "STEPUP", _explain("Cumulative drift from original intent.", drift.get("trajectory"))
    soft_flags = signals.get("suspicious_flags", [])
    if soft_flags and policy_config.injection_action != "ignore":
        return "STEPUP", _explain("Suspicious merchant patterns detected, human review recommended:", soft_flags)

    return "PASS", "Constraints satisfied, no drift or injection signature detected."
