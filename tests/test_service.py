from openoms.models.domain import ExplainDecisionRequest, InventoryQuery, Order, OrderLine
from openoms.service import OpenOMSService
from openoms.store.memory import build_seed_store


def test_order_schema_serializes_with_enterprise_field_names() -> None:
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


def test_get_inventory_returns_sorted_candidates() -> None:
    service = OpenOMSService(store=build_seed_store())
    items = service.get_inventory(InventoryQuery(sku="HAMMER-001", near_zip="60601", radius_miles=5000))
    assert items[0].node_id == "store-chi"
    assert items[0].available >= 1


def test_source_single_line_order() -> None:
    service = OpenOMSService(store=build_seed_store())
    order = Order(
        OrderNo="A10000001",
        BuyerUserId="cust-1",
        ShipToZipCode="60601",
        OrderLines=[OrderLine(ItemID="HAMMER-001", OrderedQty=1, UnitPrice=19.99)],
    )
    decision = service.source_order(order, idempotency_key="test-key-1")
    assert decision.split_count == 1
    assert decision.shipments[0].node_id == "store-chi"
    assert decision.reasoning_trace["assignments"][0]["node_id"] == "store-chi"


def test_source_multi_line_order_splits_across_nodes() -> None:
    # HAMMER-001 lives at dc-east/store-chi/store-dal.
    # PAINT-RED-1G lives at dc-south/dc-west.
    # No single node carries both — solver must split.
    service = OpenOMSService(store=build_seed_store())
    order = Order(
        BuyerUserId="cust-ml",
        ShipToZipCode="60601",
        OrderLines=[
            OrderLine(ItemID="HAMMER-001", OrderedQty=1, UnitPrice=19.99),
            OrderLine(ItemID="PAINT-RED-1G", OrderedQty=1, UnitPrice=32.50),
        ],
    )
    decision = service.source_order(order, idempotency_key="test-multi-1")
    assert len(decision.shipments) == 2
    assert decision.split_count == 2
    assert len(decision.reasoning_trace["assignments"]) == 2


def test_explain_decision_returns_trace() -> None:
    service = OpenOMSService(store=build_seed_store())
    order = Order(
        OrderNo="A10000002",
        BuyerUserId="cust-1",
        ShipToZipCode="60601",
        OrderLines=[OrderLine(ItemID="HAMMER-001", OrderedQty=1, UnitPrice=19.99)],
    )
    decision = service.source_order(order, idempotency_key="test-key-2")
    explained = service.explain_decision(ExplainDecisionRequest(decision_id=decision.decision_id, audience="ops"))
    assert "decision_trace" in explained
    assert explained["decision_trace"]["assignments"][0]["node_id"] == "store-chi"


def test_solver_picks_nearest_feasible_node() -> None:
    service = OpenOMSService(store=build_seed_store())
    order = Order(
        BuyerUserId="cust-dal",
        ShipToZipCode="75201",
        OrderLines=[OrderLine(ItemID="HAMMER-001", OrderedQty=1, UnitPrice=19.99)],
    )
    decision = service.source_order(order, idempotency_key="test-nearest-1")
    assert decision.reasoning_trace["assignments"][0]["node_id"] == "store-dal"


def test_event_log_captures_full_decision_sequence() -> None:
    service = OpenOMSService(store=build_seed_store())
    order = Order(
        BuyerUserId="cust-ev",
        ShipToZipCode="60601",
        OrderLines=[OrderLine(ItemID="HAMMER-001", OrderedQty=1, UnitPrice=19.99)],
    )
    service.source_order(order, idempotency_key="test-events-1")
    event_types = [e.event_type for e in service.store.events]
    assert "order_received" in event_types
    assert "candidates_evaluated" in event_types
    assert "solver_completed" in event_types
    assert "reservations_placed" in event_types
    assert "decision_committed" in event_types
