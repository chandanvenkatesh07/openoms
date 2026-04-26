"""Small scripted demo for the current vertical slice."""

from __future__ import annotations

import json

from openoms.models.domain import ExplainDecisionRequest, Order, OrderLine
from openoms.service import OpenOMSService


def main() -> None:
    service = OpenOMSService()
    order = Order(
        BuyerUserId="cust-001",
        ShipToZipCode="60601",
        OrderLines=[OrderLine(ItemID="HAMMER-001", OrderedQty=1, UnitPrice=19.99)],
    )
    decision = service.source_order(order, idempotency_key="demo-order-001")
    print(json.dumps(decision.model_dump(mode="json", by_alias=True), indent=2))
    explanation = service.explain_decision(
        ExplainDecisionRequest(decision_id=decision.decision_id, audience="customer")
    )
    print(json.dumps(explanation, indent=2))


if __name__ == "__main__":
    main()
