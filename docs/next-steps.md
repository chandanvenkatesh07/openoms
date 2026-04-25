# Next Steps

## Immediate follow-on build items

1. Replace the in-memory store with Postgres-backed repositories.
2. Add Redis-backed idempotency and hot inventory caching.
3. Persist decision events to the database rather than memory only.
4. Introduce OR-Tools for richer scoring once multi-candidate constraints matter.
5. Add real MCP client setup instructions after local validation.

## Intentional decisions I made

- Chose **OpenOMS** as the product name everywhere.
- Deferred LLM-based explanation generation; current explanations are deterministic and trace-backed.
- Started with an in-memory service layer so the kernel can be tested before infrastructure complexity grows.
- Kept the tool surface to `get_inventory`, `source_order`, and `explain_decision` for the first working slice.
