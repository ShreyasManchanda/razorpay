import json
import os

from nacl.signing import SigningKey

KEYS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "keys")
KEYS_FILE = os.path.join(KEYS_DIR, "keys.json")

AGENT_REGISTRY: dict[str, str] = {}
_PRIVATE_KEYS: dict[str, str] = {}
_loaded = False


def _load_keys_from_disk():
    global _loaded
    if _loaded:
        return
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE) as f:
            data = json.load(f)
        for agent_id, pair in data.items():
            AGENT_REGISTRY[agent_id] = pair["public"]
            _PRIVATE_KEYS[agent_id] = pair["private"]
    _loaded = True


def generate_keypair(agent_id: str) -> tuple[str, str]:
    sk = SigningKey.generate()
    private_hex = sk.encode().hex()
    public_hex = sk.verify_key.encode().hex()
    AGENT_REGISTRY[agent_id] = public_hex
    _PRIVATE_KEYS[agent_id] = private_hex
    return private_hex, public_hex


def save_keys_to_disk():
    os.makedirs(KEYS_DIR, exist_ok=True)
    data = {}
    for agent_id, public_key in AGENT_REGISTRY.items():
        data[agent_id] = {
            "private": _PRIVATE_KEYS.get(agent_id, ""),
            "public": public_key,
        }
    with open(KEYS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def ensure_keys_loaded():
    """Call this at startup to load keys from disk or generate fresh ones."""
    _load_keys_from_disk()
    if not AGENT_REGISTRY:
        for agent_id in ["buyer_agent_v1", "merchant_agent_v1"]:
            generate_keypair(agent_id)
        save_keys_to_disk()


def get_public_key(agent_id: str) -> str:
    _load_keys_from_disk()
    if agent_id not in AGENT_REGISTRY:
        raise KeyError(f"Agent '{agent_id}' not found in registry")
    return AGENT_REGISTRY[agent_id]


def get_private_key(agent_id: str) -> str:
    _load_keys_from_disk()
    if agent_id not in _PRIVATE_KEYS:
        raise KeyError(f"Private key for '{agent_id}' not found")
    return _PRIVATE_KEYS[agent_id]
