"""FastMCP server for the OpenOMS v0.1 tool surface."""

from __future__ import annotations

from openoms.models.domain import ExplainDecisionRequest, InventoryQuery, Order
from openoms.service import OpenOMSService

try:
    from fastmcp import FastMCP
except Exception:  # pragma: no cover - handled for local environments without deps
    FastMCP = None  # type: ignore[assignment,misc]

service = OpenOMSService()

if FastMCP is not None:
    mcp = FastMCP("OpenOMS")

    @mcp.tool()
    def get_inventory(sku: str, near_zip: str | None = None, radius_miles: int = 50) -> list[dict]:
        """Return available inventory for a SKU, sorted nearest-first."""
        request = InventoryQuery(sku=sku, near_zip=near_zip, radius_miles=radius_miles)
        return [item.model_dump(mode="json") for item in service.get_inventory(request)]

    @mcp.tool()
    def source_order(order: dict, idempotency_key: str) -> dict:
        """Source an order using the active policy. Places reservations and returns the decision."""
        parsed = Order.model_validate(order)
        return service.source_order(parsed, idempotency_key).model_dump(mode="json", by_alias=True)

    @mcp.tool()
    def relax_and_source_order(order: dict, idempotency_key: str) -> dict:
        """Source an order, automatically relaxing radius constraints until feasible.

        Use this instead of source_order when inventory may be locally constrained.
        Returns the sourcing decision plus a full relaxation history so the agent
        knows exactly what constraints had to expand and why.
        """
        parsed = Order.model_validate(order)
        result = service.relax_and_source(parsed, idempotency_key)
        return result.model_dump(mode="json", by_alias=True)

    @mcp.tool()
    def get_sourcing_options(order: dict) -> list[dict]:
        """Dry-run two policy profiles — 'speed' and 'consolidate' — for the same order.

        No reservations are placed.  Returns both options with pros, cons, and full
        decision details (split count, promise dates, node assignments) so the agent
        or customer can make an informed choice before committing.

        After the customer picks, call source_order with the desired idempotency_key.
        """
        parsed = Order.model_validate(order)
        options = service.get_sourcing_options(parsed)
        return [opt.model_dump(mode="json", by_alias=True) for opt in options]

    @mcp.tool()
    def explain_resourcing(old_decision_id: str, new_decision_id: str) -> dict:
        """Diff two sourcing decisions and explain per-line what changed and why.

        Use after inventory depletion forces a re-source, or after an order
        modification triggers re-optimisation.  Each changed line includes a
        machine-readable reason ('inventory_depleted' | 'reoptimized') and a
        human-readable explanation the agent can relay to the customer.
        """
        return service.explain_resourcing(old_decision_id, new_decision_id).model_dump(
            mode="json", by_alias=True
        )

    @mcp.tool()
    def explain_decision(decision_id: str, audience: str = "customer") -> dict:
        """Return a natural-language explanation and structured trace for a committed decision."""
        request = ExplainDecisionRequest(decision_id=decision_id, audience=audience)
        return service.explain_decision(request)


def main() -> None:
    if FastMCP is None:
        raise RuntimeError("fastmcp is not installed. Install dependencies first.")
    mcp.run()


if __name__ == "__main__":
    main()
