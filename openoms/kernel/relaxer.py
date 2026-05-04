"""Constraint-relaxation loop for the CP-SAT sourcing solver.

Tries increasingly relaxed constraints (currently: widening radius) until the
solver finds a feasible solution.  Each attempt is recorded so the service
layer can tell the agent exactly what had to give and why.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from openoms.kernel.solver import SolverResult, solve_sourcing
from openoms.models.domain import InventoryView, Order


@dataclass
class RelaxationAttempt:
    step: int
    param: str
    value: object
    outcome: str  # "INFEASIBLE" | "OPTIMAL" | "FEASIBLE"
    detail: str = ""


def relax_and_solve(
    order: Order,
    store: object,          # MemoryStore — typed as object to avoid circular import
    weights: dict,
    radius_steps: list[int],
    time_limit_ms: int = 200,
) -> tuple[SolverResult, dict[str, list[InventoryView]], list[RelaxationAttempt], bool]:
    """Try each radius in `radius_steps` until the solver returns OPTIMAL/FEASIBLE.

    Returns
    -------
    (result, candidates_by_line, attempts, original_constraints_met)

    `original_constraints_met` is True only if the FIRST radius step succeeded —
    meaning the order was solvable without any relaxation.

    Raises ValueError if every step is infeasible.
    """
    attempts: list[RelaxationAttempt] = []

    for i, radius in enumerate(radius_steps):
        candidates: dict[str, list[InventoryView]] = {
            line.line_id: store.get_inventory(line.sku, order.shipping_zip, radius)  # type: ignore[attr-defined]
            for line in order.lines
        }
        try:
            result = solve_sourcing(order, candidates, weights=weights, time_limit_ms=time_limit_ms)
            attempts.append(RelaxationAttempt(
                step=i + 1,
                param="radius_miles",
                value=radius,
                outcome=result.solve_status,
            ))
            return result, candidates, attempts, i == 0
        except ValueError as exc:
            attempts.append(RelaxationAttempt(
                step=i + 1,
                param="radius_miles",
                value=radius,
                outcome="INFEASIBLE",
                detail=str(exc),
            ))

    tried = ", ".join(str(r) for r in radius_steps)
    raise ValueError(
        f"No feasible sourcing solution after {len(radius_steps)} relaxation steps "
        f"(radii tried: {tried} miles)"
    )
