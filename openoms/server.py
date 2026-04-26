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
        request = InventoryQuery(sku=sku, near_zip=near_zip, radius_miles=radius_miles)
        return [item.model_dump(mode="json") for item in service.get_inventory(request)]

    @mcp.tool()
    def source_order(order: dict, idempotency_key: str) -> dict:
        parsed = Order.model_validate(order)
        return service.source_order(parsed, idempotency_key).model_dump(mode="json", by_alias=True)

    @mcp.tool()
    def explain_decision(decision_id: str, audience: str = "customer") -> dict:
        request = ExplainDecisionRequest(decision_id=decision_id, audience=audience)
        return service.explain_decision(request)


def main() -> None:
    if FastMCP is None:
        raise RuntimeError("fastmcp is not installed. Install dependencies first.")
    mcp.run()


if __name__ == "__main__":
    main()
