# OpenOMS

Every commercial OMS vendor — Manhattan, Blue Yonder, and the rest of the OMS market — hides the sourcing brain behind SaaS walls and product sprawl. The part that actually decides where to ship from, when it will arrive, and how to handle exceptions is usually the least inspectable part of the stack. OpenOMS is an open-source reference implementation of that **decisioning brain**.

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
- enterprise-style order input schema
- in-memory repositories for local development and tests
- policy-backed deterministic scoring weights loaded from `policies/default.yaml`
- small 5-node seeded synthetic dataset
- `get_inventory`, `source_order`, and `explain_decision`
- basic demo script and tests
- Docker skeleton for the future Postgres/Redis-backed runtime

## Order schema shape

The inbound order payload uses enterprise OMS-style field names so examples look closer to a real integration surface.

```json
{
  "OrderNo": "A10000001",
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
- richer optimization beyond simple deterministic scoring
- LLM explanation generation
- LangGraph exception handling

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
PYTHONPATH=. pytest
PYTHONPATH=. python -m openoms.demo
```

For future persistence work, install the infrastructure extras only when you need them:

```bash
pip install -e ".[postgres,redis]"
```

## Current local validation note

I validated the service layer and tests locally under the host Python available in this workspace.
The FastMCP server and Docker path are scaffolded for Python 3.11+, but they were not executed here because this machine currently lacks both Python 3.11 and Docker.

## Demo output proof

Here's what sourcing HAMMER-001 to Chicago looks like.

```json
{
  "decision_id": "5f6f2dee-dac1-401e-8a00-7f5341253da8",
  "order_id": "6ee8f71a-c814-477e-a66e-557934296dc5",
  "shipments": [
    {
      "node_id": "store-chi",
      "node_type": "store",
      "line_ids": [
        "e351a95d-8d4c-4792-a7df-54cc24f1df5e"
      ],
      "carrier": "ground",
      "promise": {
        "p50_date": "2026-04-27",
        "p80_date": "2026-04-28",
        "p95_date": "2026-04-29",
        "confidence": 0.8,
        "method": "deterministic"
      }
    }
  ],
  "total_cost": 0.0,
  "split_count": 1,
  "policy_version_used": "2026-04-25",
  "reasoning_trace": {
    "selected_node": "store-chi",
    "score": 3.75,
    "distance_miles": 0.0,
    "available_before_reservation": 4,
    "reservation_id": "f6dc0749-d7b7-4d57-8015-72cfe1dfdd50"
  },
  "explanation": "OpenOMS sourced SKU HAMMER-001 from store-chi because it had enough inventory and the best tradeoff between proximity and availability for destination 60601.",
  "created_at": "2026-04-26T19:49:20.701231",
  "status": "committed"
}
```

## Docker note

`docker compose up` brings up Postgres and Redis for the future persistence path, but v0.1 sourcing still runs against the in-memory `MemoryStore`.

## Run the MCP server

```bash
python -m openoms.server
```

## Repository map

- `openoms/models/domain.py` — domain models
- `openoms/store/memory.py` — seeded in-memory store
- `openoms/kernel/scorer.py` — deterministic nearest-feasible scoring
- `openoms/kernel/promise.py` — deterministic promise windows
- `openoms/service.py` — application service flow
- `openoms/server.py` — MCP tool registration

## Documentation

- `ARCHITECTURE.md`
- `docs/product-thesis.md`
- `docs/v0.1-plan.md`
- `docs/architecture-notes.md`
- `docs/next-steps.md`
