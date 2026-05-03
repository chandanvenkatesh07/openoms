"""Application services for the OpenOMS decisioning kernel."""

from __future__ import annotations

from collections import defaultdict

from openoms.kernel.promise import compute_promise
from openoms.kernel.solver import solve_sourcing
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
from openoms.policy import load_policy
from openoms.store.memory import MemoryStore, build_seed_store


class OpenOMSService:
    def __init__(self, store: MemoryStore | None = None, policy_path: str | None = None) -> None:
        if store is not None:
            self.store = store
        else:
            from openoms.seed.hearthline import build_hearthline_store
            self.store = build_hearthline_store()
        self.policy = load_policy(policy_path)
        self.policy_version = str(self.policy.get("version", "2026-04-25"))

    def get_inventory(self, request: InventoryQuery) -> list[InventoryView]:
        return self.store.get_inventory(request.sku, request.near_zip, request.radius_miles)

    def source_order(self, order: Order, idempotency_key: str) -> SourcingDecision:
        self.store.append_event(DecisionEvent(
            decision_id=order.order_id,
            event_type="order_received",
            payload=order.model_dump(),
        ))

        radius_miles = int(self.policy.get("radius_miles", 5000))
        weights: dict = self.policy.get("weights", {})
        time_limit_ms = int(self.policy.get("solver_time_limit_ms", 200))

        # Fetch candidate nodes for each line independently
        candidates_by_line: dict[str, list[InventoryView]] = {}
        for line in order.lines:
            candidates_by_line[line.line_id] = self.get_inventory(
                InventoryQuery(sku=line.sku, near_zip=order.shipping_zip, radius_miles=radius_miles)
            )

        self.store.append_event(DecisionEvent(
            decision_id=order.order_id,
            event_type="candidates_evaluated",
            payload={
                "line_count": len(order.lines),
                "candidates": {
                    lid: [c.model_dump() for c in views]
                    for lid, views in candidates_by_line.items()
                },
            },
        ))

        # CP-SAT solver assigns each line to the optimal node
        result = solve_sourcing(order, candidates_by_line, weights=weights, time_limit_ms=time_limit_ms)

        self.store.append_event(DecisionEvent(
            decision_id=order.order_id,
            event_type="solver_completed",
            payload={
                "status": result.solve_status,
                "wall_ms": result.wall_ms,
                "split_count": result.split_count,
                "assignments": [
                    {"line_id": a.line_id, "node_id": a.node_id, "distance_miles": a.distance_miles}
                    for a in result.assignments
                ],
            },
        ))

        # Group assignments by node to form shipments
        node_to_assignments = defaultdict(list)
        for assignment in result.assignments:
            node_to_assignments[assignment.node_id].append(assignment)

        # Place one reservation per line, compute shipments per node
        shipments: list[Shipment] = []
        all_reservation_ids: list[str] = []
        total_cost = 0.0

        for node_id, assignments in node_to_assignments.items():
            node = self.store.nodes[node_id]
            promise = compute_promise(node.lat, node.lon, order.shipping_zip)

            for a in assignments:
                reservation = self.store.reserve(
                    ReserveRequest(
                        sku=a.sku,
                        node_id=node_id,
                        quantity=a.quantity,
                        # unique key per line so idempotency works for multi-line
                        idempotency_key=f"{idempotency_key}::{a.line_id}",
                        order_id=order.order_id,
                        line_id=a.line_id,
                    )
                )
                all_reservation_ids.append(reservation.reservation_id)
                total_cost += a.distance_miles * node.cost_to_ship_factor

            shipments.append(Shipment(
                node_id=node_id,
                node_type=node.node_type,
                line_ids=[a.line_id for a in assignments],
                carrier="ground",
                promise=promise,
            ))

        self.store.append_event(DecisionEvent(
            decision_id=order.order_id,
            event_type="reservations_placed",
            payload={"reservation_ids": all_reservation_ids},
        ))

        reasoning_trace = {
            "assignments": [
                {
                    "line_id": a.line_id,
                    "sku": a.sku,
                    "node_id": a.node_id,
                    "distance_miles": a.distance_miles,
                    "available_before": a.available_before,
                }
                for a in result.assignments
            ],
            "split_count": result.split_count,
            "solve_status": result.solve_status,
            "solver_wall_ms": result.wall_ms,
            "reservation_ids": all_reservation_ids,
        }

        if result.split_count == 1:
            node_id = result.assignments[0].node_id
            explanation = (
                f"OpenOMS sourced all {len(order.lines)} line(s) from {node_id} "
                f"({result.assignments[0].distance_miles:.1f} miles) under policy {self.policy_version}."
            )
        else:
            node_summaries = ", ".join(
                f"{nid} ({len(asns)} line(s))"
                for nid, asns in node_to_assignments.items()
            )
            explanation = (
                f"OpenOMS split {len(order.lines)} lines across {result.split_count} nodes "
                f"[{node_summaries}] to minimise cost under policy {self.policy_version}."
            )

        decision = SourcingDecision(
            order_id=order.order_id,
            shipments=shipments,
            total_cost=round(total_cost, 2),
            split_count=result.split_count,
            policy_version_used=self.policy_version,
            reasoning_trace=reasoning_trace,
            explanation=explanation,
        )
        self.store.save_decision(decision)
        self.store.append_event(DecisionEvent(
            decision_id=decision.decision_id,
            event_type="decision_committed",
            payload=decision.model_dump(mode="json"),
        ))
        return decision

    def explain_decision(self, request: ExplainDecisionRequest) -> dict:
        decision = self.store.get_decision(request)
        if request.audience == "ops":
            explanation = (
                f"Decision {decision.decision_id} sourced order {decision.order_id} "
                f"with split_count={decision.split_count} "
                f"under policy {decision.policy_version_used}. "
                f"Solver: {decision.reasoning_trace.get('solve_status')} "
                f"in {decision.reasoning_trace.get('solver_wall_ms')}ms."
            )
        else:
            explanation = decision.explanation
        return {"explanation": explanation, "decision_trace": decision.reasoning_trace}
