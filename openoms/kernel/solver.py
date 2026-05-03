"""OR-Tools CP-SAT sourcing solver for multi-line order fulfillment.

Formulation
-----------
Decision variable  x[line_id][node_id] ∈ {0, 1}
  = 1 iff line is fulfilled from node

Hard constraints
  1. Each line assigned to exactly one node (add_exactly_one per line)
  2. Inventory cap: for each (sku, node) pair the total qty assigned
     cannot exceed available inventory at that node

Objective (minimise)
  sum_{l,n} x[l][n] * (distance_cost + capacity_pressure_cost)
  + sum_n node_used[n] * split_penalty

Weights are loaded from the active policy YAML.
Solver is capped at 200 ms; returns best-feasible solution if time runs out.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from openoms.models.domain import InventoryView, Order

_SCALE = 100  # integer precision: multiply float weights by this


@dataclass
class LineAssignment:
    line_id: str
    sku: str
    quantity: int
    node_id: str
    distance_miles: float
    available_before: int


@dataclass
class SolverResult:
    assignments: list[LineAssignment] = field(default_factory=list)
    split_count: int = 0
    solve_status: str = "OPTIMAL"
    wall_ms: float = 0.0


def solve_sourcing(
    order: Order,
    candidates_by_line: dict[str, list[InventoryView]],
    weights: dict[str, float] | None = None,
    time_limit_ms: int = 200,
) -> SolverResult:
    """Assign each order line to a fulfillment node using CP-SAT."""
    w = weights or {}
    shipping_w = int(w.get("shipping_cost", 1.0) * _SCALE)
    cap_w = int(w.get("capacity_pressure", 1.5) * _SCALE)
    split_w = int(w.get("split_penalty", 5.0) * _SCALE)

    model = cp_model.CpModel()

    # ── guard: every line needs at least one feasible candidate ──────────────
    for line in order.lines:
        feasible = [v for v in candidates_by_line.get(line.line_id, []) if v.available >= line.quantity]
        if not feasible:
            raise ValueError(f"no feasible inventory for line {line.line_id} (sku={line.sku}, qty={line.quantity})")

    # ── decision variables ────────────────────────────────────────────────────
    # x[(line_id, node_id)] only created for feasible (line, node) pairs
    x: dict[tuple[str, str], cp_model.IntVar] = {}
    for line in order.lines:
        for view in candidates_by_line.get(line.line_id, []):
            if view.available >= line.quantity:
                x[(line.line_id, view.node_id)] = model.new_bool_var(f"x_{line.line_id[:8]}_{view.node_id}")

    # ── constraint 1: each line assigned to exactly one node ─────────────────
    for line in order.lines:
        line_vars = [v for (lid, _), v in x.items() if lid == line.line_id]
        model.add_exactly_one(line_vars)

    # ── constraint 2: inventory cap per (sku, node) ───────────────────────────
    # Required when multiple lines share the same SKU and compete for one node
    sku_node_groups: dict[tuple[str, str], list[tuple[cp_model.IntVar, int, int]]] = defaultdict(list)
    for line in order.lines:
        for view in candidates_by_line.get(line.line_id, []):
            if (line.line_id, view.node_id) in x:
                sku_node_groups[(line.sku, view.node_id)].append(
                    (x[(line.line_id, view.node_id)], line.quantity, view.available)
                )
    for (_sku, _node), triples in sku_node_groups.items():
        if len(triples) > 1:
            available = triples[0][2]
            model.add(sum(var * qty for var, qty, _ in triples) <= available)

    # ── node-used variables (for split penalty) ───────────────────────────────
    all_node_ids = {nid for (_, nid) in x}
    node_used: dict[str, cp_model.IntVar] = {}
    for node_id in all_node_ids:
        nv = model.new_bool_var(f"used_{node_id}")
        node_used[node_id] = nv
        node_line_vars = [x[(lid, nid)] for (lid, nid) in x if nid == node_id]
        # node_used[n] = 1 iff any line is assigned to n
        for var in node_line_vars:
            model.add_implication(var, nv)
        model.add(nv <= sum(node_line_vars))

    # ── objective ─────────────────────────────────────────────────────────────
    obj: list[cp_model.LinearExprT] = []
    for line in order.lines:
        for view in candidates_by_line.get(line.line_id, []):
            key = (line.line_id, view.node_id)
            if key not in x:
                continue
            dist_cost = int(round(view.distance_miles)) * shipping_w
            cap_cost = 10 * cap_w // max(view.available, 1)
            obj.append(x[key] * (dist_cost + cap_cost))
    for nv in node_used.values():
        obj.append(nv * split_w)
    if obj:
        model.minimize(sum(obj))

    # ── solve ─────────────────────────────────────────────────────────────────
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_ms / 1000.0
    status = solver.solve(model)

    _STATUS = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.MODEL_INVALID: "INFEASIBLE",
        cp_model.UNKNOWN: "INFEASIBLE",
    }
    status_str = _STATUS.get(status, "INFEASIBLE")
    if status_str == "INFEASIBLE":
        raise ValueError("CP-SAT solver found no feasible sourcing solution")

    # ── extract assignments ───────────────────────────────────────────────────
    assignments: list[LineAssignment] = []
    for line in order.lines:
        for view in candidates_by_line.get(line.line_id, []):
            key = (line.line_id, view.node_id)
            if key in x and solver.value(x[key]) == 1:
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
                break

    return SolverResult(
        assignments=assignments,
        split_count=len({a.node_id for a in assignments}),
        solve_status=status_str,
        wall_ms=round(solver.wall_time * 1000, 1),
    )
