"""Application services for the OpenOMS v0.1 vertical slice."""

from __future__ import annotations

from openoms.kernel.promise import compute_promise
from openoms.kernel.solver import choose_best_node
from openoms.models.domain import (
    ExplainDecisionRequest,
    InventoryQuery,
    InventoryView,
    Order,
    ReserveRequest,
    Shipment,
    SourcingDecision,
)
from openoms.models.events import DecisionEvent
from openoms.store.memory import MemoryStore, build_seed_store


class OpenOMSService:
    def __init__(self, store: MemoryStore | None = None, policy_version: str = "2026-04-25") -> None:
        self.store = store or build_seed_store()
        self.policy_version = policy_version

    def get_inventory(self, request: InventoryQuery) -> list[InventoryView]:
        return self.store.get_inventory(request.sku, request.near_zip, request.radius_miles)

    def source_order(self, order: Order, idempotency_key: str) -> SourcingDecision:
        if len(order.lines) != 1:
            raise ValueError("v0.1 only supports single-line orders")
        self.store.append_event(DecisionEvent(decision_id=order.order_id, event_type="order_received", payload=order.model_dump()))
        line = order.lines[0]
        candidates = self.get_inventory(InventoryQuery(sku=line.sku, near_zip=order.shipping_zip, radius_miles=5000))
        self.store.append_event(DecisionEvent(decision_id=order.order_id, event_type="candidates_evaluated", payload={"candidates": [candidate.model_dump() for candidate in candidates]}))
        best = choose_best_node(order, candidates)
        node = self.store.nodes[best.node_id]
        promise = compute_promise(node.zip_code, order.shipping_zip)
        reservation = self.store.reserve(
            ReserveRequest(
                sku=line.sku,
                node_id=node.node_id,
                quantity=line.quantity,
                idempotency_key=idempotency_key,
                order_id=order.order_id,
                line_id=line.line_id,
            )
        )
        self.store.append_event(DecisionEvent(decision_id=order.order_id, event_type="reservations_placed", payload=reservation.model_dump(mode="json")))
        shipment = Shipment(node_id=node.node_id, node_type=node.node_type, line_ids=[line.line_id], carrier="ground", promise=promise)
        trace = {
            "selected_node": node.node_id,
            "score": best.total_score,
            "distance_miles": best.distance_miles,
            "available_before_reservation": best.available,
            "reservation_id": reservation.reservation_id,
        }
        explanation = (
            f"OpenOMS sourced SKU {line.sku} from {node.node_id} because it had enough inventory "
            f"and the best tradeoff between proximity and availability for destination {order.shipping_zip}."
        )
        decision = SourcingDecision(
            order_id=order.order_id,
            shipments=[shipment],
            total_cost=round(best.distance_miles * node.cost_to_ship_factor, 2),
            split_count=1,
            policy_version_used=self.policy_version,
            reasoning_trace=trace,
            explanation=explanation,
        )
        self.store.save_decision(decision)
        self.store.append_event(DecisionEvent(decision_id=decision.decision_id, event_type="decision_committed", payload=decision.model_dump(mode="json")))
        return decision

    def explain_decision(self, request: ExplainDecisionRequest) -> dict:
        decision = self.store.get_decision(request)
        audience = request.audience
        if audience == "ops":
            explanation = (
                f"Decision {decision.decision_id} sourced order {decision.order_id} with split_count={decision.split_count} "
                f"under policy {decision.policy_version_used}. Trace: {decision.reasoning_trace}."
            )
        else:
            explanation = decision.explanation
        return {"explanation": explanation, "decision_trace": decision.reasoning_trace}
