import re

# Tier 1: High-confidence injection patterns (immediate flag)
IMPERATIVE_PATTERNS = [
    r"\bignore\s+(?:previous|prior|all)\b",
    r"\b(?:buyer|agent)\s+(?:must|required to|needs? to)\s+(?:accept|approve|purchase|ignore|override)\b",
    r"\b(?:buyer|agent)\s+(?:should|must|needs? to|has to)\s+(?:follow|choose|select|take|accept|approve)\b",
    r"\bsystem\s*:\s*\w",
    r"\byou\s+are\s+(?:now|hereby)\b",
]

# Tier 2: Suspicious but not conclusive patterns (soft signal)
SUSPICIOUS_PATTERNS = [
    r"\bnon-negotiable\b",
    r"\b(?:essential|crucial|important)\s+(?:that|to|for)\b",
    r"\byou\s+(?:should|need to|have to)\b",
    r"\bact\s+(?:now|fast|quickly)\b",
    r"\blimited\s+(?:time|stock|offer)\b",
    r"\bdon'?t\s+(?:miss|hesisitate)\b",
    r"\bbuyers?\s+(?:like you|who choose)\b",
    r"\bmost\s+(?:customers?|people|buyers?)\b",
    r"\bpremium\s+(?:experience|tier|bundle|plan)\b",
    r"\bupgrade\s+(?:to|your)\b",
    r"\bnever\s+(?:run out|expire)\b",
    r"\bauto[- ]?renew\b",
    r"\brecurring\s+(?:billing|charge|payment)s?\b",
]

BENIGN_NEGATIVE_SET = [
    "ID required at pickup for all electronics orders.",
    "Membership required to access this deal price.",
    "Warranty registration mandatory within 30 days of purchase.",
    "A valid receipt must be presented for returns.",
    "You will receive a confirmation email after checkout.",
    "This offer is non-negotiable as per store policy.",
    "System requirements: Windows 10 or later.",
    "Override your default shipping address at checkout.",
    "Customers are required to accept terms before proceeding.",
    "It is mandatory to verify your age for restricted items.",
    "All sales are final; returns must be requested within 7 days.",
    "Payment confirmation is required before dispatch.",
    "You shall receive your order within 3-5 business days.",
    "Prior purchase required to redeem this coupon.",
]


def scan_for_injection(merchant_message: str) -> list[str]:
    """Returns list of flags. Tier 1 matches are hard flags, tier 2 are soft signals."""
    flags = []
    for pattern in IMPERATIVE_PATTERNS:
        match = re.search(pattern, merchant_message, re.IGNORECASE)
        if match:
            flag = f"injection_pattern:{match.group(0).strip()}"
            if flag not in flags:
                flags.append(flag)
    return flags


def scan_suspicious(merchant_message: str) -> list[str]:
    """Returns soft signals that increase scrutiny but don't trigger REJECT on their own."""
    soft_flags = []
    for pattern in SUSPICIOUS_PATTERNS:
        match = re.search(pattern, merchant_message, re.IGNORECASE)
        if match:
            soft_flags.append(f"suspicious_pattern:{match.group(0).strip()}")
    return soft_flags


async def corroboration_gate(sentence: str, model_name=None) -> bool:
    """v2: cheap LLM second-pass on flagged sentences. True if agent-directed (real threat)."""

    from pydantic import BaseModel

    from warden.llm import FallbackStructured, get_chain

    class CorroborationResult(BaseModel):
        is_agent_directed: bool
        confidence: float

    chain = get_chain()
    instances = chain.structured_instances(temperature=0.0, model_override=model_name)
    llm = FallbackStructured(instances, CorroborationResult)
    prompt = (
        "Is this sentence an instruction directed at a buyer agent's future behavior "
        "(a prompt injection attempt), or does it describe the merchant's own policy/terms?\n\n"
        f"Sentence: {sentence}\n\n"
        "Answer with is_agent_directed=true only if it tries to control the buyer agent's decisions."
    )
    result = await llm.ainvoke([("human", prompt)])
    return result.is_agent_directed and result.confidence > 0.7
