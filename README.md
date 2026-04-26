# OpenOMS

OpenOMS is an open-source reference implementation of the **decisioning brain** inside an order management system.

It is intentionally being built as a narrow, credible reference first — not as a fake-complete enterprise platform.

## v0.1 status

This repository now includes a working first vertical slice for:

- inventory lookup
- deterministic single-line order sourcing
- reservation creation
- deterministic promise-date calculation
- decision explanation from stored trace

The current implementation is intentionally narrow. It proves the architecture before scaling the scope.

## What is implemented now

- Python package scaffold
- FastMCP server entrypoint
- Pydantic domain models
- Sterling-style order input schema
- in-memory repositories for local development and tests
- small seeded synthetic dataset
- `get_inventory`, `source_order`, and `explain_decision`
- basic demo script and tests
- Docker skeleton for the future Postgres/Redis-backed runtime

## Order schema shape

The inbound order payload now uses IBM Sterling-inspired field names so examples look closer to a real OMS integration surface.

```json
{
  "OrderNo": "Y10000001",
  "EnterpriseCode": "DEFAULT",
  "SellerOrganizationCode": "DEFAULT",
  "DocumentType": "0001",
  "BuyerUserId": "cust-1",
  "ShipToZipCode": "60601",
  "EntryType": "WEB",
  "OrderLines": [
    {
      "PrimeLineNo": "1",
      "ItemID": "HAMMER-001",
      "OrderedQty": 1,
      "UnitPrice": 19.99,
      "FulfillmentType": "ship"
    }
  ]
}
```

## What is intentionally deferred

- multi-line orders
- split shipment optimization
- Postgres-backed repositories
- Redis-backed idempotency
- OR-Tools optimization beyond simple deterministic scoring
- LLM explanation generation
- LangGraph exception handling

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pydantic pytest PyYAML
PYTHONPATH=. pytest
PYTHONPATH=. python -m openoms.demo
```

## Current local validation note

I validated the service layer and tests locally under the host Python available in this workspace.
The FastMCP server and Docker path are scaffolded for Python 3.11+, but they were not executed here because this machine currently lacks both Python 3.11 and Docker.

## Run the MCP server

```bash
python -m openoms.server
```

## Repository map

- `openoms/models/domain.py` — domain models
- `openoms/store/memory.py` — seeded in-memory store
- `openoms/kernel/solver.py` — deterministic node selection
- `openoms/kernel/promise.py` — deterministic promise windows
- `openoms/service.py` — application service flow
- `openoms/server.py` — MCP tool registration

## Documentation

- `ARCHITECTURE.md`
- `docs/product-thesis.md`
- `docs/v0.1-plan.md`
- `docs/architecture-notes.md`
- `docs/next-steps.md`
