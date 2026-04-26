"""Deterministic nearest-feasible scorer for v0.1."""

from __future__ import annotations

from dataclasses import dataclass

from openoms.models.domain import InventoryView, Order


DEFAULT_WEIGHTS = {
    "shipping_cost": 1.0,
    "capacity_pressure": 1.5,
}


@dataclass
class CandidateScore:
    node_id: str
    total_score: float
    distance_miles: float
    available: int


def choose_best_node(
    order: Order,
    candidates: list[InventoryView],
    weights: dict[str, float] | None = None,
) -> CandidateScore:
    """Pick the best feasible node for a single-line order using fixed heuristic weights."""
    if len(order.lines) != 1:
        raise ValueError("v0.1 only supports single-line orders")
    line = order.lines[0]
    feasible = [candidate for candidate in candidates if candidate.available >= line.quantity]
    if not feasible:
        raise ValueError("no feasible inventory candidates found")

    active_weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    ranked = [
        CandidateScore(
            node_id=candidate.node_id,
            distance_miles=candidate.distance_miles,
            available=candidate.available,
            total_score=round(
                (candidate.distance_miles * active_weights["shipping_cost"])
                + ((10 / max(candidate.available, 1)) * active_weights["capacity_pressure"]),
                2,
            ),
        )
        for candidate in feasible
    ]
    return min(ranked, key=lambda item: item.total_score)
