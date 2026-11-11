# Next Steps

The multi-line CP-SAT kernel, split-shipment objective, greedy baseline, bounded radius relaxation, sourcing-option dry runs, re-sourcing diffs, six MCP tools, seeded benchmark, and in-memory decision traces are implemented. The next work is production hardening rather than adding another demo workflow.

## Highest-priority engineering gaps

1. Replace `MemoryStore` with transactional repositories for inventory, reservations, decisions, and events.
2. Make multi-line reservation commits atomic, or add tested compensation that releases earlier reservations after a later failure.
3. Add concurrency control and durable idempotency for competing orders.
4. Add authentication, tenant-aware authorization, MCP tool policy, rate limiting, and retained audit logs.
5. Add durable retry and recovery behavior for external dependencies before describing the workflow as agent orchestration.
6. Export request, solver, reservation, and error telemetry to an observability backend.
7. Turn the benchmark into a repeated, versioned evaluation with pinned environments and saved result artifacts.
8. Validate sourcing quality and promise behavior on representative operational data before making production claims.

## Deliberate boundaries that remain

- Explanations are deterministic and trace-backed; an LLM explanation layer remains optional and advisory-only.
- The solver and reservation path remains deterministic even when invoked by an AI agent.
- Postgres and Redis files are scaffolding until the service actually uses them.
- Automatic re-sourcing is not implemented; the current tool compares two decisions supplied by a caller.
- The speed/consolidate option endpoint is a dry-run comparison, not a complete choose-and-commit workflow.
