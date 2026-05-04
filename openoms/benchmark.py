"""50-line order benchmark: CP-SAT ILP vs nearest-first greedy.

Runs three scenarios to expose where joint ILP optimization diverges from
the sequential greedy baseline:

  S1  — 50 distinct SKUs, qty=1  (baseline, low contention)
  S2  — 50 distinct SKUs, qty=1, split_penalty=500  (consolidation pressure)
  S3  — 10 lines of same SKU at constrained stock  (pre-commitment error)

Usage:
  python -m openoms.benchmark
  # or:
  openoms-demo  # (if you add an entry point in pyproject.toml)
"""

from __future__ import annotations

import time
from collections import Counter

from openoms.kernel.greedy import solve_sourcing_greedy
from openoms.kernel.solver import SolverResult, solve_sourcing
from openoms.models.domain import InventoryQuery, Order, OrderLine
from openoms.seed.hearthline import _build_skus, build_hearthline_store
from openoms.store.memory import MemoryStore

_SHIP_TO = "60601"  # Chicago — mid-continent, stresses coast-to-coast splits


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _weighted_distance(result: SolverResult) -> float:
    return sum(a.distance_miles * a.quantity for a in result.assignments)


def _node_histogram(result: SolverResult) -> list[tuple[str, int]]:
    counts = Counter(a.node_id for a in result.assignments)
    return sorted(counts.items(), key=lambda kv: -kv[1])


def _print_comparison(
    label: str,
    ilp: SolverResult,
    greedy: SolverResult,
    n_lines: int,
) -> None:
    ilp_dist = _weighted_distance(ilp)
    gr_dist = _weighted_distance(greedy)
    dist_saved = gr_dist - ilp_dist
    dist_pct = dist_saved / gr_dist * 100 if gr_dist else 0.0
    split_saved = greedy.split_count - ilp.split_count

    print(f"\n{'─'*62}")
    print(f"  {label}")
    print(f"{'─'*62}")
    print(f"  {'Metric':<30} {'ILP (CP-SAT)':>14} {'Greedy':>14}")
    print(f"  {'─'*58}")
    print(f"  {'Status':<30} {ilp.solve_status:>14} {greedy.solve_status:>14}")
    print(f"  {'Solve time (ms)':<30} {ilp.wall_ms:>14.1f} {greedy.wall_ms:>14.3f}")
    print(f"  {'Nodes used (shipments)':<30} {ilp.split_count:>14} {greedy.split_count:>14}")
    print(f"  {'Total weighted dist (mi)':<30} {ilp_dist:>14,.0f} {gr_dist:>14,.0f}")
    if dist_saved != 0:
        arrow = "▲" if dist_saved < 0 else "▼"
        print(f"  {'ILP distance delta':<30} {arrow} {abs(dist_pct):>12.1f}%")
    if split_saved > 0:
        print(f"  {'ILP split reduction':<30} {split_saved:>13} fewer")
    elif split_saved < 0:
        print(f"  {'ILP split increase':<30} {-split_saved:>13} more (consolidating)")

    # node breakdowns side by side
    ilp_nodes = dict(_node_histogram(ilp))
    gr_nodes = dict(_node_histogram(greedy))
    all_nodes = sorted(set(ilp_nodes) | set(gr_nodes), key=lambda n: -(ilp_nodes.get(n, 0)))
    print(f"\n  {'Node':<22} {'ILP lines':>10} {'Greedy lines':>12}")
    print(f"  {'─'*46}")
    for node_id in all_nodes[:20]:
        il = ilp_nodes.get(node_id, 0)
        gl = gr_nodes.get(node_id, 0)
        marker = " ←" if il != gl else ""
        print(f"  {node_id:<22} {il:>10} {gl:>12}{marker}")
    if len(all_nodes) > 20:
        print(f"  … {len(all_nodes) - 20} more nodes omitted")

    # divergent assignments
    ilp_map = {a.line_id: a for a in ilp.assignments}
    gr_map = {a.line_id: a for a in greedy.assignments}
    diffs = [
        (ilp_map[lid], gr_map[lid])
        for lid in ilp_map
        if ilp_map[lid].node_id != gr_map[lid].node_id
    ]
    print(f"\n  Divergent assignments: {len(diffs)} / {n_lines} lines")
    if diffs:
        header = f"  {'SKU':<20} {'ILP node':<20} {'ILP dist':>8}   {'Greedy node':<20} {'Greedy dist':>8}"
        print(header)
        print(f"  {'─'*80}")
        for ia, ga in diffs[:20]:
            print(
                f"  {ia.sku:<20} {ia.node_id:<20} {ia.distance_miles:>8.0f}"
                f"   {ga.node_id:<20} {ga.distance_miles:>8.0f}"
            )
        if len(diffs) > 20:
            print(f"  … {len(diffs) - 20} more")


def _fetch_candidates(
    store: MemoryStore,
    order: Order,
    radius_miles: int = 5000,
) -> dict[str, list]:
    return {
        line.line_id: store.get_inventory(line.sku, order.shipping_zip, radius_miles)
        for line in order.lines
    }


# ---------------------------------------------------------------------------
# Scenario builders
# ---------------------------------------------------------------------------

def _scenario_1(store: MemoryStore) -> tuple[str, Order, dict, dict, dict]:
    """50 distinct SKUs, qty=1, default weights."""
    all_skus = _build_skus()
    popular = all_skus[:100]
    long_tail = all_skus[100:]
    # stride-sample to get a representative spread across all categories
    selected = popular[::4][:25] + long_tail[::12][:25]
    lines = [OrderLine(ItemID=sku, OrderedQty=1, UnitPrice=10.0) for sku in selected]
    order = Order(BuyerUserId="bench-s1", ShipToZipCode=_SHIP_TO, OrderLines=lines)
    weights_low = {"shipping_cost": 1.0, "split_penalty": 5.0, "capacity_pressure": 1.5}
    return "S1 — 50 distinct SKUs, qty=1, split_penalty=5", order, _fetch_candidates(store, order), weights_low, weights_low


def _scenario_2(store: MemoryStore) -> tuple[str, Order, dict, dict]:
    """Same 50 SKUs, qty=1, but split_penalty=500 — consolidation incentive."""
    all_skus = _build_skus()
    popular = all_skus[:100]
    long_tail = all_skus[100:]
    selected = popular[::4][:25] + long_tail[::12][:25]
    lines = [OrderLine(ItemID=sku, OrderedQty=1, UnitPrice=10.0) for sku in selected]
    order = Order(BuyerUserId="bench-s2", ShipToZipCode=_SHIP_TO, OrderLines=lines)
    weights_high = {"shipping_cost": 1.0, "split_penalty": 500.0, "capacity_pressure": 1.5}
    return "S2 — same 50 SKUs, split_penalty=500 (high consolidation pressure)", order, _fetch_candidates(store, order), weights_high


def _scenario_3(_unused_store: MemoryStore) -> tuple[str, Order, dict, dict]:
    """Controlled pre-commitment error demonstration.

    Pinned inventory:
      node-a (Chicago,      ~0 mi):  3 units SKU-X  +  3 units SKU-Y
      node-b (Indianapolis, ~165 mi): 100 units SKU-X only
      node-c (Milwaukee,    ~81 mi): 100 units SKU-Y only

    Order: 4 lines — 2×SKU-X qty=2, 2×SKU-Y qty=2
      (total demand: 4 units SKU-X, 4 units SKU-Y)
      node-a cannot fully serve either SKU (only 3 units each).

    Greedy (sequential, nearest-first):
      L1 SKU-X → node-a  (0 mi;  uses 2 of 3)
      L2 SKU-X → node-a only has 1 left, need 2 → node-b  (165 mi)
      L3 SKU-Y → node-a  (0 mi;  uses 2 of 3)
      L4 SKU-Y → node-a only has 1 left, need 2 → node-c  (81 mi)
      Result: 3 NODES (node-a + node-b + node-c)

    ILP (split_penalty=300 ≡ 300 extra miles per shipment):
      Obj[greedy path 3 nodes] = 0+165+0+81 + 3×300 = 1146
      Obj[NodeB+NodeC only, 2 nodes] = 165×2 + 81×2 + 2×300 = 1092
      → ILP SKIPS node-a entirely and uses only 2 nodes.

    The pre-commitment error:
      Greedy greedily takes 2 units from node-a (nearest), but that partial
      use of node-a creates TWO extra splits (one for the overflow SKU-X line,
      one for the overflow SKU-Y line).  ILP sees globally that touching node-a
      at all forces 3 shipments; skipping it yields 2.
    """
    from openoms.models.domain import InventoryRecord, Node, NodeType

    custom = MemoryStore()
    custom.seed(
        nodes=[
            # Chicago-adjacent — essentially 0 miles from dest zip 60601
            Node(node_id="node-a", node_type=NodeType.DC, zip_code="60601",
                 lat=41.89, lon=-87.62, capacity_units_per_day=100, cost_to_ship_factor=1.0),
            # Indianapolis-area
            Node(node_id="node-b", node_type=NodeType.DC, zip_code="46202",
                 lat=39.77, lon=-86.16, capacity_units_per_day=1000, cost_to_ship_factor=1.0),
            # Milwaukee-area
            Node(node_id="node-c", node_type=NodeType.DC, zip_code="53202",
                 lat=43.04, lon=-87.91, capacity_units_per_day=1000, cost_to_ship_factor=1.0),
        ],
        inventory=[
            InventoryRecord(sku="SKU-X", node_id="node-a", on_hand=3),   # ← bottleneck
            InventoryRecord(sku="SKU-Y", node_id="node-a", on_hand=3),   # ← bottleneck
            InventoryRecord(sku="SKU-X", node_id="node-b", on_hand=100),
            InventoryRecord(sku="SKU-Y", node_id="node-c", on_hand=100),
        ],
    )

    lines = (
        [OrderLine(ItemID="SKU-X", OrderedQty=2, UnitPrice=5.0) for _ in range(2)]
        + [OrderLine(ItemID="SKU-Y", OrderedQty=2, UnitPrice=5.0) for _ in range(2)]
    )
    order = Order(BuyerUserId="bench-s3", ShipToZipCode="60601", OrderLines=lines)
    weights = {"shipping_cost": 1.0, "split_penalty": 300.0, "capacity_pressure": 0.0}
    candidates = _fetch_candidates(custom, order)

    print(f"\n  Pinned inventory:")
    print(f"    {'node-a (Chicago ~0 mi)':<30} SKU-X=3 units,  SKU-Y=3 units")
    print(f"    {'node-b (Indianapolis ~165 mi)':<30} SKU-X=100 units only")
    print(f"    {'node-c (Milwaukee ~81 mi)':<30} SKU-Y=100 units only")
    print(f"  Order: 2×SKU-X qty=2, 2×SKU-Y qty=2  (need 4+4 units)")
    print(f"  split_penalty=300 (each extra shipment ≡ 300 extra miles)")
    print(f"  ILP math: 3-node path costs 246+900=1146; 2-node path costs 492+600=1092")
    print(f"  ILP should skip node-a entirely and ship from node-b + node-c only.")

    label = "S3 — pre-commitment error (controlled): greedy=3 nodes, ILP=2 nodes"
    return label, order, candidates, weights


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 62)
    print("  OpenOMS 50-line Benchmark: CP-SAT ILP vs Greedy")
    print("=" * 62)

    t_load = time.perf_counter()
    store = build_hearthline_store()
    load_ms = (time.perf_counter() - t_load) * 1000
    print(f"\n  Hearthline store loaded in {load_ms:.0f} ms")
    print(f"  Nodes: {len(store.nodes)}  |  Inventory records: {len(store.inventory)}")

    # ── S1 ────────────────────────────────────────────────────────────────────
    label1, order1, cands1, w1, _ = _scenario_1(store)
    total_cands = sum(len(v) for v in cands1.values())
    print(f"\n  {label1}")
    print(f"  Lines: {len(order1.lines)}  |  Total candidates: {total_cands}  |  Avg per line: {total_cands // len(order1.lines)}")
    ilp1 = solve_sourcing(order1, cands1, weights=w1, time_limit_ms=2000)
    gr1 = solve_sourcing_greedy(order1, cands1)
    _print_comparison(label1, ilp1, gr1, len(order1.lines))

    # ── S2 ────────────────────────────────────────────────────────────────────
    label2, order2, cands2, w2 = _scenario_2(store)
    ilp2 = solve_sourcing(order2, cands2, weights=w2, time_limit_ms=2000)
    gr2 = solve_sourcing_greedy(order2, cands2)
    _print_comparison(label2, ilp2, gr2, len(order2.lines))

    # ── S3 ────────────────────────────────────────────────────────────────────
    label3, order3, cands3, w3 = _scenario_3(store)
    try:
        ilp3 = solve_sourcing(order3, cands3, weights=w3, time_limit_ms=2000)
        gr3 = solve_sourcing_greedy(order3, cands3)
        _print_comparison(label3, ilp3, gr3, len(order3.lines))
    except ValueError as exc:
        print(f"\n  {label3}")
        print(f"  (skipped — insufficient total stock: {exc})")

    print(f"\n{'─'*62}\n")


if __name__ == "__main__":
    main()
