"""Single-line deterministic sourcing solver for v0.1."""

from __future__ import annotations

from dataclasses import dataclass

from openoms.models.domain import InventoryView, Order


@dataclass
class CandidateScore:
    node_id: str
    total_score: float
    distance_miles: float
    available: int


def choose_best_node(order: Order, candidates: list[InventoryView]) -> CandidateScore:
    """Pick the best feasible node for a single-line order."""
    if len(order.lines) != 1:
        raise ValueError("v0.1 only supports single-line orders")
    line = order.lines[0]
    feasible = [candidate for candidate in candidates if candidate.available >= line.quantity]
    if not feasible:
        raise ValueError("no feasible inventory candidates found")
    ranked = [
        CandidateScore(
            node_id=candidate.node_id,
            distance_miles=candidate.distance_miles,
            available=candidate.available,
            total_score=round(candidate.distance_miles + (10 / max(candidate.available, 1)), 2),
        )
        for candidate in feasible
    ]
    return min(ranked, key=lambda item: item.total_score)
