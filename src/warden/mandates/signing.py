from nacl.signing import SigningKey, VerifyKey

from warden.keys import get_public_key


def _canonical_bytes(model) -> bytes:
    return model.model_dump_json(exclude={"signature"}).encode("utf-8")


def sign_mandate(model, private_hex: str):
    sk = SigningKey(bytes.fromhex(private_hex))
    signed = sk.sign(_canonical_bytes(model))
    model.signature = signed.signature.hex()
    return model


def verify_mandate(model) -> bool:
    if model.signature is None:
        return False
    public_hex = get_public_key(model.agent_id)
    vk = VerifyKey(bytes.fromhex(public_hex))
    try:
        vk.verify(_canonical_bytes(model), bytes.fromhex(model.signature))
        return True
    except Exception:
        return False
