import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from warden.agents.attacker_agent import AttackerAgent


async def main():
    attacker = AttackerAgent()
    print("Generating injection payload...")
    injection = await attacker.generate("injection")
    print(f"Payload: {injection.payload}")
    print(f"Rationale: {injection.rationale}")

    print("\nGenerating drift strategy...")
    drift = await attacker.generate("gradual_drift")
    print(f"Payload: {drift.payload}")
    print(f"Rationale: {drift.rationale}")


if __name__ == "__main__":
    asyncio.run(main())
