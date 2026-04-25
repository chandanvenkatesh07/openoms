from openoms.models.domain import ExplainDecisionRequest, InventoryQuery, Order, OrderLine
from openoms.service import OpenOMSService


def test_get_inventory_returns_sorted_candidates() -> None:
    service = OpenOMSService()
    items = service.get_inventory(InventoryQuery(sku="HAMMER-001", near_zip="60601", radius_miles=5000))
    assert items[0].node_id == "store-chi"
    assert items[0].available >= 1


def test_source_order_creates_single_shipment_and_decision() -> None:
    service = OpenOMSService()
    order = Order(customer_id="cust-1", shipping_zip="60601", lines=[OrderLine(sku="HAMMER-001", quantity=1, unit_price=19.99)])
    decision = service.source_order(order, idempotency_key="test-key-1")
    assert decision.split_count == 1
    assert decision.shipments[0].node_id == "store-chi"
    assert decision.reasoning_trace["selected_node"] == "store-chi"


def test_explain_decision_returns_trace() -> None:
    service = OpenOMSService()
    order = Order(customer_id="cust-1", shipping_zip="60601", lines=[OrderLine(sku="HAMMER-001", quantity=1, unit_price=19.99)])
    decision = service.source_order(order, idempotency_key="test-key-2")
    explained = service.explain_decision(ExplainDecisionRequest(decision_id=decision.decision_id, audience="ops"))
    assert "decision_trace" in explained
    assert explained["decision_trace"]["selected_node"] == "store-chi"
