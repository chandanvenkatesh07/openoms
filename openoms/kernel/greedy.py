"""Nearest-first greedy sourcing solver.

Sequential algorithm: for each order line (in arrival order), assign it to
the nearest feasible node.  After each commit, virtual inventory is decremented
so that downstream lines see the correct remaining stock.

This is the industry-standard baseline — equivalent to the evaluation model
used by most legacy OMS platforms: evaluate each line independently, take the
locally optimal choice, move on.  No global visibility.
"""

from __future__ import annotations

import time

from openoms.kernel.solver import LineAssignment, SolverResult
from openoms.models.domain import InventoryView, Order


def solve_sourcing_greedy(
    order: Order,
    candidates_by_line: dict[str, list[InventoryView]],
) -> SolverResult:
    """Assign each line to the nearest node that has sufficient stock.

    Candidates must already be sorted nearest-first (as returned by
    MemoryStore.get_inventory).  Virtual inventory is tracked in-process
    so the same units are not double-booked across lines.
    """
    t0 = time.perf_counter()

    # (sku, node_id) → remaining available units after prior line commits
    virtual: dict[tuple[str, str], int] = {}

    assignments: list[LineAssignment] = []
    for line in order.lines:
        candidates = candidates_by_line.get(line.line_id, [])
        committed = False
        for view in candidates:  # sorted nearest-first
            key = (line.sku, view.node_id)
            avail = virtual.get(key, view.available)
            if avail >= line.quantity:
                virtual[key] = avail - line.quantity
                assignments.append(
                    LineAssignment(
                        line_id=line.line_id,
                        sku=line.sku,
                        quantity=line.quantity,
                        node_id=view.node_id,
                        distance_miles=view.distance_miles,
                        available_before=view.available,
                    )
                )
                committed = True
                break
        if not committed:
            raise ValueError(
                f"no feasible inventory for line {line.line_id} "
                f"(sku={line.sku}, qty={line.quantity})"
            )

    wall_ms = round((time.perf_counter() - t0) * 1000, 3)
    return SolverResult(
        assignments=assignments,
        split_count=len({a.node_id for a in assignments}),
        solve_status="GREEDY",
        wall_ms=wall_ms,
    )
