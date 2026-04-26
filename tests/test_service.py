from openoms.models.domain import ExplainDecisionRequest, InventoryQuery, Order, OrderLine


def test_order_schema_serializes_with_sterling_field_names() -> None:
    order = Order(
        OrderNo="A10000000",
        BuyerUserId="cust-sterling",
        ShipToZipCode="60601",
        OrderLines=[OrderLine(ItemID="HAMMER-001", OrderedQty=2, UnitPrice=19.99)],
    )
    payload = order.model_dump(mode="json", by_alias=True)
    assert payload["OrderNo"] == "A10000000"
    assert payload["BuyerUserId"] == "cust-sterling"
    assert payload["OrderLines"][0]["ItemID"] == "HAMMER-001"

from openoms.service import OpenOMSService


def test_get_inventory_returns_sorted_candidates() -> None:
    service = OpenOMSService()
    items = service.get_inventory(InventoryQuery(sku="HAMMER-001", near_zip="60601", radius_miles=5000))
    assert items[0].node_id == "store-chi"
    assert items[0].available >= 1


def test_source_order_creates_single_shipment_and_decision() -> None:
    service = OpenOMSService()
    order = Order(
        OrderNo="A10000001",
        BuyerUserId="cust-1",
        ShipToZipCode="60601",
        OrderLines=[OrderLine(ItemID="HAMMER-001", OrderedQty=1, UnitPrice=19.99)],
    )
    decision = service.source_order(order, idempotency_key="test-key-1")
    assert decision.split_count == 1
    assert decision.shipments[0].node_id == "store-chi"
    assert decision.reasoning_trace["selected_node"] == "store-chi"


def test_explain_decision_returns_trace() -> None:
    service = OpenOMSService()
    order = Order(
        OrderNo="A10000002",
        BuyerUserId="cust-1",
        ShipToZipCode="60601",
        OrderLines=[OrderLine(ItemID="HAMMER-001", OrderedQty=1, UnitPrice=19.99)],
    )
    decision = service.source_order(order, idempotency_key="test-key-2")
    explained = service.explain_decision(ExplainDecisionRequest(decision_id=decision.decision_id, audience="ops"))
    assert "decision_trace" in explained
    assert explained["decision_trace"]["selected_node"] == "store-chi"
