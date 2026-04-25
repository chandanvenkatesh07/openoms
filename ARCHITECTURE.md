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
    +--> deterministic node scoring
    +--> deterministic promise dates
    +--> reservation creation
    +--> decision trace + explanation
    |
    v
MemoryStore (seeded synthetic dataset)
```

## Working flow today

1. `get_inventory` looks up candidate nodes for a SKU.
2. `source_order` validates a single-line order.
3. The solver ranks feasible nodes by distance and available inventory.
4. The service reserves inventory using an idempotency key.
5. A promise window is generated deterministically.
6. The decision and trace are stored.
7. `explain_decision` returns a trace-backed explanation.

## Deliberate temporary compromises

- Storage is in-memory so the vertical slice can be tested easily.
- Explanation is deterministic text instead of an LLM call.
- Optimization is heuristic ranking, not full OR-Tools constraint solving yet.
- Only single-line orders are supported.

## Planned next upgrades

- Postgres repositories
- Redis-backed idempotency and inventory cache
- OR-Tools solver
- richer event store persistence
- multi-line orders and split shipments
- LLM explanation and exception handling behind the deterministic boundary
