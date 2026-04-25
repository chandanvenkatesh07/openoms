"""Small scripted demo for the current vertical slice."""

from __future__ import annotations

import json

from openoms.models.domain import ExplainDecisionRequest, Order, OrderLine
from openoms.service import OpenOMSService


def main() -> None:
    service = OpenOMSService()
    order = Order(
        customer_id="cust-001",
        shipping_zip="60601",
        lines=[OrderLine(sku="HAMMER-001", quantity=1, unit_price=19.99)],
    )
    decision = service.source_order(order, idempotency_key="demo-order-001")
    print(json.dumps(decision.model_dump(mode="json"), indent=2))
    explanation = service.explain_decision(
        ExplainDecisionRequest(decision_id=decision.decision_id, audience="customer")
    )
    print(json.dumps(explanation, indent=2))


if __name__ == "__main__":
    main()
