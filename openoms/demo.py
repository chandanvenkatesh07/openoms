"""End-to-end demo: single-line and multi-line orders through the CP-SAT solver."""

from __future__ import annotations

import json

from openoms.models.domain import ExplainDecisionRequest, Order, OrderLine
from openoms.service import OpenOMSService
from openoms.store.memory import build_seed_store


def _dump(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main() -> None:
    service = OpenOMSService(store=build_seed_store())

    print("=" * 60)
    print("SCENARIO 1 — single-line order (Chicago, HAMMER-001)")
    print("=" * 60)
    order1 = Order(
        BuyerUserId="cust-001",
        ShipToZipCode="60601",
        OrderLines=[OrderLine(ItemID="HAMMER-001", OrderedQty=1, UnitPrice=19.99)],
    )
    d1 = service.source_order(order1, idempotency_key="demo-s1")
    _dump(d1.model_dump(mode="json", by_alias=True))
    _dump(service.explain_decision(ExplainDecisionRequest(decision_id=d1.decision_id)))

    print()
    print("=" * 60)
    print("SCENARIO 2 — multi-line order (Chicago, HAMMER-001 + PAINT-RED-1G)")
    print("  HAMMER-001 is available at store-chi; PAINT-RED-1G is only at")
    print("  dc-south and dc-west. Solver must split across 2 nodes.")
    print("=" * 60)
    order2 = Order(
        BuyerUserId="cust-002",
        ShipToZipCode="60601",
        OrderLines=[
            OrderLine(ItemID="HAMMER-001", OrderedQty=1, UnitPrice=19.99),
            OrderLine(ItemID="PAINT-RED-1G", OrderedQty=2, UnitPrice=32.50),
        ],
    )
    d2 = service.source_order(order2, idempotency_key="demo-s2")
    _dump(d2.model_dump(mode="json", by_alias=True))
    _dump(service.explain_decision(ExplainDecisionRequest(decision_id=d2.decision_id, audience="ops")))

    print()
    print(f"Events captured in log: {len(service.store.events)}")
    print("Event sequence:", [e.event_type for e in service.store.events])


if __name__ == "__main__":
    main()
