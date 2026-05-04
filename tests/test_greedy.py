"""Tests for the nearest-first greedy sourcing solver."""

import pytest

from openoms.kernel.greedy import solve_sourcing_greedy
from openoms.kernel.solver import solve_sourcing
from openoms.models.domain import InventoryQuery, Order, OrderLine
from openoms.store.memory import build_seed_store


def _make_order(ship_zip: str, lines: list[tuple[str, int]]) -> Order:
    return Order(
        BuyerUserId="test",
        ShipToZipCode=ship_zip,
        OrderLines=[OrderLine(ItemID=sku, OrderedQty=qty, UnitPrice=1.0) for sku, qty in lines],
    )


def _candidates(store, order, radius=5000):
    return {
        line.line_id: store.get_inventory(line.sku, order.shipping_zip, radius)
        for line in order.lines
    }


def test_greedy_single_line_picks_nearest():
    store = build_seed_store()
    order = _make_order("60601", [("HAMMER-001", 1)])
    cands = _candidates(store, order)
    result = solve_sourcing_greedy(order, cands)
    assert result.split_count == 1
    assert result.assignments[0].node_id == "store-chi"
    assert result.solve_status == "GREEDY"


def test_greedy_respects_inventory_cap():
    """Greedy must not assign more units than available at a node."""
    store = build_seed_store()
    # store-chi has 4 HAMMER-001 units; order 5 → should fall back to dc-east
    order = _make_order("60601", [("HAMMER-001", 5)])
    cands = _candidates(store, order)
    result = solve_sourcing_greedy(order, cands)
    assert result.assignments[0].node_id != "store-chi"  # store-chi only has 4
    assert result.assignments[0].available_before >= 5


def test_greedy_tracks_virtual_inventory_across_lines():
    """Two lines competing for the same limited stock at the nearest node."""
    store = build_seed_store()
    # store-chi has exactly 4 HAMMER-001 units.
    # Line 1 takes 3 → 1 unit left.  Line 2 needs 2 → must go elsewhere.
    order = _make_order("60601", [("HAMMER-001", 3), ("HAMMER-001", 2)])
    cands = _candidates(store, order)
    result = solve_sourcing_greedy(order, cands)
    node_ids = [a.node_id for a in result.assignments]
    # Line 1 at store-chi, line 2 at dc-east (next nearest with stock)
    assert node_ids[0] == "store-chi"
    assert node_ids[1] != "store-chi"


def test_greedy_multi_line_different_skus():
    store = build_seed_store()
    # HAMMER-001 at store-chi; PAINT-RED-1G only at dc-south / dc-west
    order = _make_order("60601", [("HAMMER-001", 1), ("PAINT-RED-1G", 1)])
    cands = _candidates(store, order)
    result = solve_sourcing_greedy(order, cands)
    assert result.split_count == 2
    node_ids = {a.node_id for a in result.assignments}
    assert "store-chi" in node_ids


def test_greedy_raises_on_infeasible():
    store = build_seed_store()
    order = _make_order("60601", [("HAMMER-001", 999)])
    cands = _candidates(store, order)
    with pytest.raises(ValueError, match="no feasible inventory"):
        solve_sourcing_greedy(order, cands)


def test_greedy_wall_ms_is_positive():
    store = build_seed_store()
    order = _make_order("60601", [("HAMMER-001", 1)])
    cands = _candidates(store, order)
    result = solve_sourcing_greedy(order, cands)
    assert result.wall_ms >= 0


def test_ilp_beats_greedy_on_split_count_with_high_penalty():
    """ILP consolidates more aggressively than greedy under high split penalty.

    HAMMER-001 is available at store-chi (near Chicago) AND dc-east.
    PAINT-RED-1G is only at dc-south / dc-west.
    With split_penalty=500, ILP may assign HAMMER from the same region as
    PAINT if it finds a consolidating node — greedy always takes nearest first.

    At minimum, ILP split_count <= greedy split_count under high penalty.
    """
    store = build_seed_store()
    order = _make_order(
        "60601",
        [("HAMMER-001", 1), ("PAINT-RED-1G", 1)],
    )
    cands = _candidates(store, order)
    weights_high = {"shipping_cost": 1.0, "split_penalty": 500.0, "capacity_pressure": 1.5}
    ilp = solve_sourcing(order, cands, weights=weights_high, time_limit_ms=500)
    greedy = solve_sourcing_greedy(order, cands)
    assert ilp.split_count <= greedy.split_count
