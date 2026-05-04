"""Application services for the OpenOMS decisioning kernel."""

from __future__ import annotations

from collections import defaultdict

from openoms.kernel.promise import compute_promise
from openoms.kernel.relaxer import relax_and_solve
from openoms.kernel.solver import solve_sourcing
from openoms.models.domain import (
    ExplainDecisionRequest,
    InventoryQuery,
    InventoryView,
    Order,
    RelaxationAttempt,
    RelaxationResult,
    ResourcingChangeLine,
    ResourcingDiff,
    ReserveRequest,
    Shipment,
    SourcingDecision,
    SourcingOption,
)
from openoms.models.events import DecisionEvent
from openoms.policy import load_policy
from openoms.store.memory import MemoryStore, build_seed_store

# Built-in option profiles for get_sourcing_options.
# Each entry: (option_id, label, weights_overrides, description, pros, cons)
_OPTION_PROFILES = [
    (
        "speed",
        "Ship fastest",
        {"shipping_cost": 1.0, "split_penalty": 5.0, "capacity_pressure": 1.5},
        "Nearest fulfillment node per line — minimises transit time.",
        ["Fastest delivery promise", "Uses closest available stock"],
        ["May ship in multiple boxes", "Higher total shipping cost if split"],
    ),
    (
        "consolidate",
        "Fewest boxes",
        {"shipping_cost": 0.5, "split_penalty": 500.0, "capacity_pressure": 1.5},
        "Pack into fewest shipments — minimises boxes at the door.",
        ["Single delivery if possible", "Simpler returns", "Better unboxing experience"],
        ["May add 1-2 days if consolidation node is farther", "Higher per-mile distance"],
    ),
]


class OpenOMSService:
    def __init__(self, store: MemoryStore | None = None, policy_path: str | None = None) -> None:
        if store is not None:
            self.store = store
        else:
            from openoms.seed.hearthline import build_hearthline_store
            self.store = build_hearthline_store()
        self.policy = load_policy(policy_path)
        self.policy_version = str(self.policy.get("version", "2026-04-25"))

    # ── public read ───────────────────────────────────────────────────────────

    def get_inventory(self, request: InventoryQuery) -> list[InventoryView]:
        return self.store.get_inventory(request.sku, request.near_zip, request.radius_miles)

    # ── core sourcing ─────────────────────────────────────────────────────────

    def source_order(self, order: Order, idempotency_key: str) -> SourcingDecision:
        self.store.append_event(DecisionEvent(
            decision_id=order.order_id,
            event_type="order_received",
            payload=order.model_dump(),
        ))

        radius_miles = int(self.policy.get("radius_miles", 5000))
        weights: dict = self.policy.get("weights", {})
        time_limit_ms = int(self.policy.get("solver_time_limit_ms", 200))

        candidates_by_line: dict[str, list[InventoryView]] = {
            line.line_id: self.get_inventory(
                InventoryQuery(sku=line.sku, near_zip=order.shipping_zip, radius_miles=radius_miles)
            )
            for line in order.lines
        }

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

        return self._execute_sourcing(
            order, idempotency_key, candidates_by_line, weights, time_limit_ms
        )

    # ── agentic: constraint relaxation ───────────────────────────────────────

    def relax_and_source(self, order: Order, idempotency_key: str) -> RelaxationResult:
        """Source the order, automatically relaxing radius until feasible.

        The relaxation cascade is configured in the policy under
        ``relaxation_cascade.radius_miles``.  Each step is recorded so the
        calling agent knows exactly what constraint was relaxed and why.
        """
        self.store.append_event(DecisionEvent(
            decision_id=order.order_id,
            event_type="order_received",
            payload=order.model_dump(),
        ))

        weights: dict = self.policy.get("weights", {})
        time_limit_ms = int(self.policy.get("solver_time_limit_ms", 200))
        cascade = self.policy.get("relaxation_cascade", {})
        radius_steps: list[int] = [int(r) for r in cascade.get("radius_miles", [500, 1500, 5000])]

        result, candidates_by_line, raw_attempts, original_met = relax_and_solve(
            order, self.store, weights, radius_steps, time_limit_ms
        )

        winning_radius = int(raw_attempts[-1].value)
        self.store.append_event(DecisionEvent(
            decision_id=order.order_id,
            event_type="relaxation_resolved",
            payload={
                "original_constraints_met": original_met,
                "winning_radius_miles": winning_radius,
                "attempts": [
                    {"step": a.step, "radius": a.value, "outcome": a.outcome, "detail": a.detail}
                    for a in raw_attempts
                ],
            },
        ))

        decision = self._execute_sourcing(
            order, idempotency_key, candidates_by_line, weights, time_limit_ms
        )

        attempts = [
            RelaxationAttempt(
                step=a.step, param=a.param,
                value=float(a.value),
                outcome=a.outcome, detail=a.detail,
            )
            for a in raw_attempts
        ]

        if original_met:
            agent_summary = (
                f"Order sourced within the initial {winning_radius}-mile radius. "
                f"No constraint relaxation was required."
            )
        else:
            failed = [a for a in raw_attempts if a.outcome == "INFEASIBLE"]
            agent_summary = (
                f"Original radius constraints were too tight "
                f"({len(failed)} step(s) infeasible). "
                f"Expanded search to {winning_radius} miles to find feasible inventory."
            )

        return RelaxationResult(
            decision=decision,
            attempts=attempts,
            original_constraints_met=original_met,
            winning_radius_miles=winning_radius,
            agent_summary=agent_summary,
        )

    # ── agentic: multi-option comparison ─────────────────────────────────────

    def get_sourcing_options(self, order: Order) -> list[SourcingOption]:
        """Dry-run two policy profiles and return both as options.

        No reservations are placed.  The agent or customer picks an option,
        then the caller commits with ``source_order`` using the chosen weights.
        """
        radius_miles = int(self.policy.get("radius_miles", 5000))
        time_limit_ms = int(self.policy.get("solver_time_limit_ms", 200))

        # Fetch candidates once — shared by both profiles
        candidates_by_line: dict[str, list[InventoryView]] = {
            line.line_id: self.get_inventory(
                InventoryQuery(sku=line.sku, near_zip=order.shipping_zip, radius_miles=radius_miles)
            )
            for line in order.lines
        }

        options: list[SourcingOption] = []
        for option_id, label, weights, description, pros, cons in _OPTION_PROFILES:
            try:
                decision = self._execute_sourcing(
                    order,
                    idempotency_key=f"__opt__{option_id}",
                    candidates_by_line=candidates_by_line,
                    weights=weights,
                    time_limit_ms=time_limit_ms,
                    dry_run=True,
                )
                options.append(SourcingOption(
                    option_id=option_id,
                    label=label,
                    description=description,
                    decision=decision,
                    pros=pros,
                    cons=cons,
                ))
            except ValueError:
                pass  # profile infeasible for this order — skip silently

        return options

    # ── agentic: re-sourcing diff ─────────────────────────────────────────────

    def explain_resourcing(
        self, old_decision_id: str, new_decision_id: str
    ) -> ResourcingDiff:
        """Diff two decisions and explain per-line what changed and why.

        Typical use: after inventory depletion forces a re-source, the agent
        calls this to generate a structured explanation for the customer or
        for downstream orchestration.
        """
        old = self.store.get_decision(ExplainDecisionRequest(decision_id=old_decision_id))
        new = self.store.get_decision(ExplainDecisionRequest(decision_id=new_decision_id))

        old_map = {a["line_id"]: a for a in old.reasoning_trace["assignments"]}
        new_map = {a["line_id"]: a for a in new.reasoning_trace["assignments"]}

        changed: list[ResourcingChangeLine] = []
        unchanged_line_ids: list[str] = []

        for line_id, old_a in old_map.items():
            if line_id not in new_map:
                continue  # line cancelled — not a re-source scenario
            new_a = new_map[line_id]
            if old_a["node_id"] == new_a["node_id"]:
                unchanged_line_ids.append(line_id)
                continue

            # Infer reason: check if inventory at the original node is now depleted
            inv = self.store.inventory.get((old_a["sku"], old_a["node_id"]))
            ordered_qty = old_a.get("quantity", 1)
            if inv is None or inv.available < ordered_qty:
                reason = "inventory_depleted"
                explanation = (
                    f"{old_a['sku']} at {old_a['node_id']} dropped below ordered qty "
                    f"({ordered_qty}); re-routed to {new_a['node_id']} "
                    f"({new_a['distance_miles']:.0f} mi)."
                )
            else:
                reason = "reoptimized"
                delta = new_a["distance_miles"] - old_a["distance_miles"]
                direction = "farther" if delta > 0 else "closer"
                explanation = (
                    f"{old_a['sku']} moved {old_a['node_id']} → {new_a['node_id']} "
                    f"({abs(delta):.0f} mi {direction}) during global re-optimisation."
                )

            changed.append(ResourcingChangeLine(
                line_id=line_id,
                sku=old_a["sku"],
                old_node_id=old_a["node_id"],
                new_node_id=new_a["node_id"],
                old_distance_miles=old_a["distance_miles"],
                new_distance_miles=new_a["distance_miles"],
                reason=reason,
                explanation=explanation,
            ))

        split_delta = new.split_count - old.split_count

        if not changed:
            agent_summary = "Re-sourcing produced identical assignments — no changes required."
        else:
            depleted = [c for c in changed if c.reason == "inventory_depleted"]
            reopt = [c for c in changed if c.reason == "reoptimized"]
            parts: list[str] = []
            if depleted:
                parts.append(f"{len(depleted)} line(s) re-routed due to inventory depletion")
            if reopt:
                parts.append(f"{len(reopt)} line(s) globally re-optimised")
            if split_delta > 0:
                parts.append(f"split count increased by {split_delta}")
            elif split_delta < 0:
                parts.append(f"split count reduced by {-split_delta}")
            agent_summary = "; ".join(parts) + "."

        return ResourcingDiff(
            old_decision_id=old_decision_id,
            new_decision_id=new_decision_id,
            order_id=old.order_id,
            changed_lines=changed,
            unchanged_line_ids=unchanged_line_ids,
            split_count_delta=split_delta,
            agent_summary=agent_summary,
        )

    # ── explain ───────────────────────────────────────────────────────────────

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

    # ── private ───────────────────────────────────────────────────────────────

    def _execute_sourcing(
        self,
        order: Order,
        idempotency_key: str,
        candidates_by_line: dict[str, list[InventoryView]],
        weights: dict,
        time_limit_ms: int,
        dry_run: bool = False,
    ) -> SourcingDecision:
        """Run the solver on pre-fetched candidates and (unless dry_run) commit.

        dry_run=True skips reservations, event logging, and store persistence.
        Used by get_sourcing_options to compare profiles without side effects.
        """
        result = solve_sourcing(order, candidates_by_line, weights=weights, time_limit_ms=time_limit_ms)

        if not dry_run:
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

        node_to_assignments: dict[str, list] = defaultdict(list)
        for assignment in result.assignments:
            node_to_assignments[assignment.node_id].append(assignment)

        shipments: list[Shipment] = []
        all_reservation_ids: list[str] = []
        total_cost = 0.0

        for node_id, assignments in node_to_assignments.items():
            node = self.store.nodes[node_id]
            promise = compute_promise(node.lat, node.lon, order.shipping_zip)

            for a in assignments:
                if not dry_run:
                    reservation = self.store.reserve(ReserveRequest(
                        sku=a.sku,
                        node_id=node_id,
                        quantity=a.quantity,
                        idempotency_key=f"{idempotency_key}::{a.line_id}",
                        order_id=order.order_id,
                        line_id=a.line_id,
                    ))
                    all_reservation_ids.append(reservation.reservation_id)
                total_cost += a.distance_miles * node.cost_to_ship_factor

            shipments.append(Shipment(
                node_id=node_id,
                node_type=node.node_type,
                line_ids=[a.line_id for a in assignments],
                carrier="ground",
                promise=promise,
            ))

        if not dry_run:
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
                    "quantity": a.quantity,          # needed for explain_resourcing
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
            node_id_single = result.assignments[0].node_id
            explanation = (
                f"OpenOMS sourced all {len(order.lines)} line(s) from {node_id_single} "
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
            status="draft" if dry_run else "committed",
        )

        if not dry_run:
            self.store.save_decision(decision)
            self.store.append_event(DecisionEvent(
                decision_id=decision.decision_id,
                event_type="decision_committed",
                payload=decision.model_dump(mode="json"),
            ))

        return decision
