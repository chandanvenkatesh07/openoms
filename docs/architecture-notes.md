# Architecture Notes

## Non-negotiable principle

If a decision affects state, money, inventory, or customer commitments, deterministic code must own it.

The LLM may:
- parse intent
- explain outcomes
- classify exceptions
- draft candidate resolutions

The LLM may not:
- choose a fulfillment node
- compute ATP
- reserve or release inventory
- commit sourcing decisions
- create customer commitments directly

## Suggested v0.1 architecture

```text
Agent / Client
    |
    v
FastMCP server
    |
    v
Deterministic kernel
  - candidate filter
  - sourcing solver
  - promise-date calculator
  - reservation service
    |
    +--> Postgres
    +--> Redis
    +--> Event log
    |
    +--> LLM explanation layer (read-only)
```

## Design simplifications for v0.1

### 1. Keep source_order synchronous
That is acceptable in a reference implementation, but structure it so explanation generation can move async later.

### 2. Start policy as config, not a language
Begin with a small YAML config containing:
- objective weights
- node filtering toggles
- a few hard constraints

Only promote it into a richer DSL after 2–3 real policies exist.

### 3. Treat promise dates as deterministic first
A simple baseline is enough for v0.1:
- origin cutoff
- transit lane table
- destination estimate

Conformal prediction should land only once the deterministic path is clean.

### 4. Make reservations line-aware early
Even in v0.1, reservation records should preserve order and line identity.

### 5. Log every decision phase
Recommended event sequence:
- `order_received`
- `candidates_evaluated`
- `solver_completed`
- `reservations_placed`
- `explanation_generated`
- `decision_committed`

## Suggested future architecture boundaries

### Kernel package
Pure decisioning logic. Minimal side effects.

### Store package
Transactions, repositories, concurrency, event persistence.

### Tools package
Thin MCP wrappers over validated application services.

### Reasoner package
Deferred until later. Must remain advisory-only.
