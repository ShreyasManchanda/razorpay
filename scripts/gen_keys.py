import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from warden.keys import KEYS_DIR, generate_keypair, save_keys_to_disk


def main():
    os.makedirs(KEYS_DIR, exist_ok=True)
    for agent_id in ["buyer_agent_v1", "merchant_agent_v1"]:
        generate_keypair(agent_id)
        print(f"Generated keypair for {agent_id}")
    save_keys_to_disk()
    print(f"Keys saved to {KEYS_DIR}/keys.json")


if __name__ == "__main__":
    main()
