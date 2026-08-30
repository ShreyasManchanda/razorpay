from pathlib import Path

import yaml
from pydantic import BaseModel, Field

SCENARIOS_DIR = Path(__file__).parent / "configs"


class ScenarioCatalogItem(BaseModel):
    name: str
    price: float
    category: str = "vegetables"
    description: str = ""


class ScenarioPolicy(BaseModel):
    name: str = "default"
    injection_action: str = "reject"
    drift_action: str = "stepup"
    stepup_required_above: float = 500.0


class Scenario(BaseModel):
    id: str
    display_name: str
    tagline: str = ""
    language_hint: str = "English"
    buyer_persona: str
    merchant_persona: str
    margin_policy: str
    catalog: list[ScenarioCatalogItem]
    default_intent: dict = Field(
        default_factory=lambda: {
            "intent_text": "buy fresh vegetables",
            "max_price": 300,
            "red_lines": [],
            "allowed_categories": ["vegetables"],
        }
    )
    policy_overrides: ScenarioPolicy = ScenarioPolicy()


def load_scenario(scenario_id: str) -> Scenario:
    path = SCENARIOS_DIR / f"{scenario_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Scenario '{scenario_id}' not found at {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Scenario(**data)


def list_scenarios() -> list[str]:
    if not SCENARIOS_DIR.exists():
        return []
    return [f.stem for f in SCENARIOS_DIR.glob("*.yaml")]
