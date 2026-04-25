"""Small synthetic dataset used by the in-memory development flow."""

from __future__ import annotations

import json

from openoms.store.memory import build_seed_store


def main() -> None:
    store = build_seed_store()
    payload = {
        "nodes": [node.model_dump(mode="json") for node in store.nodes.values()],
        "inventory": [record.model_dump(mode="json") for record in store.inventory.values()],
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
