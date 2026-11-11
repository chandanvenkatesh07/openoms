# OpenOMS

OpenOMS is an open-source reference implementation of the order-sourcing decision layer inside an order management system. It assigns multi-line orders to fulfillment nodes, creates inventory reservations, calculates deterministic promise windows, records decision traces, and exposes the workflow through MCP tools.

The project is deliberately narrower than a commercial OMS. The implemented path is a deterministic, inspectable kernel backed by synthetic data and in-memory state—not a production fulfillment platform.

## Implemented capabilities

| Capability | Current implementation |
|---|---|
| Multi-line sourcing | OR-Tools CP-SAT assigns every order line to exactly one feasible node. |
| Fulfillment constraints | Each line requires sufficient node inventory; aggregate demand for the same SKU cannot exceed a node's available stock. |
| Split shipments | The objective trades weighted distance and capacity pressure against a configurable per-node split penalty. |
| Baseline comparison | `openoms/kernel/greedy.py` provides a sequential nearest-first baseline. |
| Reservations | Committed sourcing creates one line-aware reservation per assignment with a derived idempotency key. |
| Constraint relaxation | `relax_and_source_order` expands the inventory search radius through policy-defined steps until a feasible solution is found. |
| Sourcing options | A dry-run compares speed and consolidation profiles without reserving inventory or persisting a decision. |
| Re-sourcing explanations | `explain_resourcing` compares two stored decisions and identifies depleted-inventory versus re-optimization changes. |
| Decision evidence | Solver status, wall time, assignments, inventory-before values, reservation IDs, promise windows, and lifecycle events are retained in memory. |
| MCP integration | Six FastMCP tools expose inventory, sourcing, relaxation, option comparison, re-sourcing diffs, and explanations. |
| Benchmarking | A seeded Hearthline dataset and three-scenario CP-SAT-versus-greedy harness are included. |

## Deterministic decision boundary

If a decision changes inventory, fulfillment assignments, or customer commitments, deterministic code owns it. The current explanation strings are also generated from stored traces; there is no LLM in the sourcing or reservation path.

An AI agent can call the MCP tools, compare dry-run options, or relay explanations. It cannot bypass the Pydantic order contract, change the solver constraints, or directly mutate inventory.

## Order payload

The public model accepts enterprise-style aliases and supports one or more order lines:

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
    },
    {
      "PrimeLineNo": "2",
      "ItemID": "DRILL-001",
      "OrderedQty": 1,
      "UnitPrice": 89.99,
      "FulfillmentType": "ship"
    }
  ]
}
```

## Quick start

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python -m openoms.demo
```

Run the MCP server:

```bash
python -m openoms.server
```

Run the reproducible benchmark scenarios:

```bash
python -m openoms.benchmark
```

The benchmark uses a seeded synthetic Hearthline network (200 nodes, 500 SKUs, and roughly 30,000 inventory records) plus a small pinned constrained-inventory case. It reports solver wall time, nodes used, weighted distance, and divergent assignments for CP-SAT and greedy. The harness gives CP-SAT a 2,000 ms limit; the service policy defaults to 200 ms. Results are machine-dependent and should be reported with the commit, environment, and repeated-run method.

## MCP tool surface

| Tool | State effect | Purpose |
|---|---|---|
| `get_inventory` | Read only | Return available inventory for a SKU, sorted by distance. |
| `source_order` | Commits | Solve, reserve each line, save the decision, and append lifecycle events. |
| `relax_and_source_order` | Commits | Try policy-defined radius steps, then commit the first feasible result. |
| `get_sourcing_options` | Dry run | Compare the speed and consolidation profiles without reservations. |
| `explain_resourcing` | Read only | Diff two committed decisions line by line. |
| `explain_decision` | Read only | Return a customer or operations explanation backed by the stored trace. |

## Current reliability behavior

- Pydantic validates order and tool inputs before service execution.
- The solver rejects a line with no feasible inventory and raises when CP-SAT cannot produce a solution within the configured limit.
- Radius relaxation records every infeasible and feasible attempt.
- Dry-run options do not reserve inventory, append events, or save decisions.
- Reservation idempotency is scoped to the in-memory store and the caller-provided key plus line ID.
- Solver and decision lifecycle data are inspectable through the in-memory event log and reasoning trace.

## Honest boundaries

- `MemoryStore` is the active runtime. State, idempotency keys, events, and decisions are lost on restart.
- Reservations for a multi-line order are placed sequentially and are not wrapped in an atomic transaction. A failure after an earlier line reserves does not automatically roll that reservation back.
- The included Postgres schema and Docker services are scaffolding; `OpenOMSService` does not use the Postgres repository or Redis at runtime.
- The MCP and HTTP surfaces do not implement authentication, authorization, tenant isolation, rate limiting, or durable workflow recovery.
- Promise dates use a deterministic distance-based approximation, not carrier calendars or live capacity.
- The benchmark is synthetic and does not establish production throughput, solution quality, or operational reliability.
- No LLM explanation layer, LangGraph workflow, OpenTelemetry exporter, or production replay mechanism is implemented.

Install the infrastructure extras only for future persistence work:

```bash
pip install -e ".[postgres,redis]"
```

`docker compose up` starts Postgres and Redis scaffolding, but sourcing still runs against `MemoryStore`.

## Repository map

- `openoms/kernel/solver.py` — CP-SAT model, constraints, objective, and solver limit
- `openoms/kernel/greedy.py` — sequential nearest-first comparison baseline
- `openoms/kernel/relaxer.py` — policy-driven search-radius relaxation
- `openoms/kernel/promise.py` — deterministic promise windows
- `openoms/service.py` — commit, dry-run, reservation, event, and explanation flows
- `openoms/server.py` — six MCP tool registrations
- `openoms/store/memory.py` — active in-memory repositories and idempotent reservations
- `openoms/seed/hearthline.py` — seeded large synthetic network
- `openoms/benchmark.py` — CP-SAT-versus-greedy scenarios
- `tests/` — solver, reservation, split-shipment, relaxation, option, and re-sourcing tests

## Documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`docs/product-thesis.md`](docs/product-thesis.md)
- [`docs/architecture-notes.md`](docs/architecture-notes.md)
- [`docs/next-steps.md`](docs/next-steps.md)
- [`docs/v0.1-plan.md`](docs/v0.1-plan.md) — historical initial plan
