"""Tests for the three agentic capabilities: relax_and_source, get_sourcing_options,
explain_resourcing."""

from __future__ import annotations

import pytest

from openoms.models.domain import Order, OrderLine
from openoms.service import OpenOMSService
from openoms.store.memory import MemoryStore, build_seed_store


def _svc(store: MemoryStore | None = None) -> OpenOMSService:
    return OpenOMSService(store=store or build_seed_store())


def _order(ship_zip: str, lines: list[tuple[str, int]]) -> Order:
    return Order(
        BuyerUserId="agent-test",
        ShipToZipCode=ship_zip,
        OrderLines=[OrderLine(ItemID=sku, OrderedQty=qty, UnitPrice=1.0) for sku, qty in lines],
    )


# ── relax_and_source ─────────────────────────────────────────────────────────

def test_relax_succeeds_within_first_step_when_local_stock_exists():
    """HAMMER-001 is at store-chi — tight radius should work on step 1."""
    svc = _svc()
    svc.policy["relaxation_cascade"] = {"radius_miles": [10, 100, 5000]}
    order = _order("60601", [("HAMMER-001", 1)])
    result = svc.relax_and_source(order, "test-relax-local")
    assert result.original_constraints_met is True
    assert result.attempts[0].outcome == "OPTIMAL"
    assert len([a for a in result.attempts if a.outcome == "INFEASIBLE"]) == 0
    assert result.decision.split_count == 1


def test_relax_expands_radius_when_sku_only_at_distant_node():
    """PAINT-RED-1G is only at dc-south (~720 mi) and dc-west (~2000 mi).
    Steps at 10/100/500 miles should all be infeasible; 5000 succeeds."""
    svc = _svc()
    svc.policy["relaxation_cascade"] = {"radius_miles": [10, 100, 500, 5000]}
    order = _order("60601", [("PAINT-RED-1G", 1)])
    result = svc.relax_and_source(order, "test-relax-distant")
    assert result.original_constraints_met is False
    infeasible = [a for a in result.attempts if a.outcome == "INFEASIBLE"]
    assert len(infeasible) >= 3
    assert result.attempts[-1].outcome == "OPTIMAL"
    assert result.winning_radius_miles == 5000


def test_relax_agent_summary_reflects_relaxation():
    svc = _svc()
    svc.policy["relaxation_cascade"] = {"radius_miles": [10, 5000]}
    order = _order("60601", [("PAINT-RED-1G", 1)])
    result = svc.relax_and_source(order, "test-relax-summary")
    assert "tight" in result.agent_summary.lower() or "infeasible" in result.agent_summary.lower()
    assert "5000" in result.agent_summary


def test_relax_raises_when_all_steps_infeasible():
    svc = _svc()
    svc.policy["relaxation_cascade"] = {"radius_miles": [1, 2]}
    order = _order("60601", [("PAINT-RED-1G", 1)])
    with pytest.raises(ValueError, match="relaxation"):
        svc.relax_and_source(order, "test-relax-fail")


def test_relax_places_reservations_and_commits_decision():
    svc = _svc()
    svc.policy["relaxation_cascade"] = {"radius_miles": [5000]}
    order = _order("60601", [("HAMMER-001", 1)])
    result = svc.relax_and_source(order, "test-relax-commit")
    assert result.decision.status == "committed"
    assert result.decision.decision_id in svc.store.decisions


# ── get_sourcing_options ──────────────────────────────────────────────────────

def test_get_sourcing_options_returns_two_profiles():
    svc = _svc()
    order = _order("60601", [("HAMMER-001", 1)])
    options = svc.get_sourcing_options(order)
    assert len(options) == 2
    ids = {o.option_id for o in options}
    assert ids == {"speed", "consolidate"}


def test_get_sourcing_options_are_dry_run():
    """Options must not place reservations or persist decisions."""
    svc = _svc()
    order = _order("60601", [("HAMMER-001", 1)])
    before_decisions = len(svc.store.decisions)
    before_reservations = len(svc.store.reservations_by_id)
    svc.get_sourcing_options(order)
    assert len(svc.store.decisions) == before_decisions
    assert len(svc.store.reservations_by_id) == before_reservations


def test_get_sourcing_options_decisions_marked_draft():
    svc = _svc()
    order = _order("60601", [("HAMMER-001", 1)])
    options = svc.get_sourcing_options(order)
    for opt in options:
        assert opt.decision.status == "draft"


def test_get_sourcing_options_consolidate_le_speed_splits():
    """Consolidate profile should never produce more splits than speed."""
    svc = _svc()
    order = _order("60601", [("HAMMER-001", 1), ("PAINT-RED-1G", 1)])
    options = svc.get_sourcing_options(order)
    speed = next(o for o in options if o.option_id == "speed")
    consolidate = next(o for o in options if o.option_id == "consolidate")
    assert consolidate.decision.split_count <= speed.decision.split_count


# ── explain_resourcing ────────────────────────────────────────────────────────

def test_explain_resourcing_no_change_when_inventory_unchanged():
    """Source the same order twice — assignments should be identical."""
    svc = _svc()
    order1 = _order("60601", [("HAMMER-001", 1)])
    order2 = _order("60601", [("HAMMER-001", 1)])
    d1 = svc.source_order(order1, "test-resrc-same-1")
    d2 = svc.source_order(order2, "test-resrc-same-2")
    diff = svc.explain_resourcing(d1.decision_id, d2.decision_id)
    assert diff.changed_lines == []
    assert diff.split_count_delta == 0
    assert "identical" in diff.agent_summary.lower()


def test_explain_resourcing_detects_inventory_depletion():
    """Deplete store-chi → re-source must move HAMMER-001 to dc-east.

    Both sourcings use the SAME order object so line_ids are identical —
    explain_resourcing matches assignments by line_id across decisions.
    """
    svc = _svc()
    # One order, two sourcing calls with different idempotency keys
    order = _order("60601", [("HAMMER-001", 1)])
    d1 = svc.source_order(order, "test-resrc-deplete-1")
    assert d1.reasoning_trace["assignments"][0]["node_id"] == "store-chi"

    # Simulate full depletion of store-chi
    record = svc.store.inventory[("HAMMER-001", "store-chi")]
    record.reserved = record.on_hand  # available = 0

    # Re-source same order — solver must fall back to dc-east
    d2 = svc.source_order(order, "test-resrc-deplete-2")
    assert d2.reasoning_trace["assignments"][0]["node_id"] != "store-chi"

    diff = svc.explain_resourcing(d1.decision_id, d2.decision_id)
    assert len(diff.changed_lines) == 1
    changed = diff.changed_lines[0]
    assert changed.old_node_id == "store-chi"
    assert changed.reason == "inventory_depleted"
    assert "depleted" in diff.agent_summary.lower() or "depletion" in diff.agent_summary.lower()


def test_explain_resourcing_captures_per_line_explanation():
    svc = _svc()
    order = _order("60601", [("HAMMER-001", 1)])
    d1 = svc.source_order(order, "test-resrc-expl-1")
    record = svc.store.inventory[("HAMMER-001", "store-chi")]
    record.reserved = record.on_hand
    d2 = svc.source_order(order, "test-resrc-expl-2")
    diff = svc.explain_resourcing(d1.decision_id, d2.decision_id)
    assert diff.changed_lines[0].explanation != ""
    assert diff.changed_lines[0].sku == "HAMMER-001"
