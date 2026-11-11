# OpenOMS Architecture

## Core rule

If a decision changes inventory, commitments, or order state, deterministic code owns it.

## Implemented runtime

```text
Client or AI agent
        |
        | validated MCP/HTTP request
        v
FastMCP tools / API route
        |
        v
OpenOMSService
        |
        +--> candidate inventory lookup
        +--> CP-SAT joint assignment or greedy comparison baseline
        +--> deterministic promise calculation
        +--> line-aware reservations (commit path only)
        +--> decision trace, lifecycle events, explanations
        |
        v
MemoryStore + seeded Hearthline data
```

The LLM boundary is outside the commit path. The repository currently contains no model call: an agent may invoke tools and present results, but CP-SAT and application services select nodes, calculate promises, reserve inventory, and persist the in-memory decision.

## Sourcing model

For each order line and feasible node, the solver creates a Boolean assignment variable. It enforces:

1. Exactly one node per order line.
2. Enough available inventory for each candidate assignment.
3. Aggregate inventory capacity for multiple lines that share a SKU and node.

The minimized objective is:

```text
weighted distance
+ capacity-pressure penalty
+ split penalty for every node used
```

Weights and the normal service time limit are loaded from `policies/default.yaml`. The current default limit is 200 ms. If the solver reaches the limit with a feasible solution it returns `FEASIBLE`; if it produces no feasible solution, the request fails rather than committing a guessed assignment.

## Commit sequence

```text
source_order(order, idempotency_key)
    |
    +-- validate Order with Pydantic
    +-- append order_received event
    +-- retrieve candidates for every line
    +-- append candidates_evaluated event
    +-- solve all lines jointly with CP-SAT
    +-- append solver_completed event
    +-- group assignments into shipments by node
    +-- calculate a deterministic promise per shipment
    +-- reserve each line with <caller key>::<line id>
    +-- append reservations_placed event
    +-- save the decision and reasoning trace
    +-- append decision_committed event
    v
committed SourcingDecision
```

Reservation creation is sequential. The in-memory store makes an individual reservation idempotent, but the multi-line commit is not transactional: if a later reservation fails, earlier reservations are not automatically rolled back.

## Agent-facing workflows

### Constraint relaxation

`relax_and_source_order` tries the radius cascade in `policies/default.yaml` (currently 150, 500, 1,500, and 5,000 miles). Each failed or successful attempt is returned. The first feasible candidate set is then passed through the normal commit sequence.

This is bounded retry logic, not durable orchestration. There is no persisted workflow state, retry queue, or resume-after-restart behavior.

### Option comparison

`get_sourcing_options` runs two dry-run profiles over the same candidates:

- **speed** favors shorter distance with a low split penalty;
- **consolidate** uses a high split penalty to favor fewer boxes.

Dry runs skip reservations, event writes, and decision persistence. The current API does not accept an option identifier when committing; callers that need to commit a chosen custom profile require an explicit policy mechanism that is not yet implemented.

### Re-sourcing evidence

The repository does not run an automatic re-sourcing workflow. A caller creates a later decision, then `explain_resourcing` compares the two stored traces. A changed line is classified as `inventory_depleted` when the original node no longer has the ordered quantity; otherwise it is described as `reoptimized`.

### Explanations

`explain_decision` and `explain_resourcing` render deterministic text from structured traces. They do not call an LLM and do not expose hidden chain-of-thought.

## Failure behavior

| Condition | Implemented behavior |
|---|---|
| Invalid order or MCP arguments | Pydantic/FastMCP validation rejects the request. |
| No feasible node for a line | Solver path raises `ValueError`; no decision is saved. |
| Initial search radius too small | Relaxation tool records the failed step and tries the next configured radius. |
| All radius steps infeasible | The relaxation request fails; no decision is committed. |
| Solver times out without a feasible solution | Request fails as infeasible. |
| Duplicate reservation key for a line | `MemoryStore` returns the existing reservation. |
| Later line fails during reservation | Earlier reservations can remain; automatic compensation is not implemented. |
| Process restart | In-memory reservations, events, and decisions are lost. |

## Observability available now

- CP-SAT status and wall time in every reasoning trace
- selected node, quantity, distance, and inventory-before for every line
- reservation IDs and split count
- order, candidate, solver, reservation, and commit events in memory
- benchmark output for solver time, weighted distance, shipment count, and assignment differences

There is no OpenTelemetry exporter, centralized log sink, token/cost telemetry, or production dashboard.

## Persistence and security boundary

The active service uses `MemoryStore`. `openoms/store/postgres.py`, `sql/init.sql`, Postgres, and Redis are incomplete infrastructure scaffolds rather than the current execution path.

The tool and HTTP surfaces have no authentication, authorization, tenant scoping, rate limiting, or audit retention. They should be treated as local reference/demo interfaces until those controls and transactional persistence are added.

## Highest-priority production gaps

1. Atomic reservation transactions with rollback or compensation.
2. Durable repositories for inventory, reservations, decisions, and events.
3. Concurrency control and durable idempotency.
4. Authentication, authorization, tenant isolation, and MCP tool policy.
5. Timeouts, retry policy, and resumable orchestration around external dependencies.
6. Real carrier calendars, node capacity, sourcing constraints, and operational datasets.
7. Repeated performance and solution-quality evaluation under documented environments.
8. Exported traces, metrics, and operational alerting.
