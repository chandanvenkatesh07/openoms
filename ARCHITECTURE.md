# OpenOMS Architecture

## Core rule

If a decision changes inventory, commitments, or order state, deterministic code owns it.

## Current v0.1 implementation

```text
Client / MCP caller
    |
    v
openoms.server
    |
    v
OpenOMSService
    |
    +--> inventory lookup
    +--> policy-backed nearest-feasible scoring
    +--> deterministic promise dates
    +--> reservation creation
    +--> decision trace + deterministic explanation
    |
    v
MemoryStore (seeded synthetic dataset)
```

## Source order sequence

```text
Client / MCP caller
    |
    | 1. source_order(order, idempotency_key)
    v
openoms.server
    |
    v
OpenOMSService
    |
    | 2. load policy weights + radius from policies/default.yaml
    | 3. fetch candidate inventory from MemoryStore
    | 4. rank feasible nodes with deterministic scorer
    | 5. compute promise window deterministically
    | 6. reserve inventory with idempotency key
    | 7. persist decision trace + event log
    | 8. generate trace-backed explanation
    v
Decision response

LLM boundary: outside the commit path. An LLM may explain or triage later,
but it does not choose the node, reserve inventory, or create the promise.
```

## Working flow today

1. `get_inventory` looks up candidate nodes for a SKU.
2. `source_order` validates a single-line order.
3. The nearest-feasible scorer ranks feasible nodes by distance and available inventory using policy weights.
4. The service reserves inventory using an idempotency key.
5. A promise window is generated deterministically.
6. The decision and trace are stored.
7. `explain_decision` returns a trace-backed explanation.

## Deliberate temporary compromises

- Storage is in-memory so the vertical slice can be tested easily.
- Explanation is deterministic text instead of an LLM call.
- Optimization is heuristic ranking, not a full constraint solver.
- Only single-line orders are supported.

## Planned next upgrades

- Postgres repositories
- Redis-backed idempotency and inventory cache
- richer multi-constraint optimization
- richer event store persistence
- multi-line orders and split shipments
- LLM explanation and exception handling behind the deterministic boundary
