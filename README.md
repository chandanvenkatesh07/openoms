# OpenOMS

> Working title for an open-source, vendor-neutral order orchestration decisioning kernel for agentic commerce.

This repository starts with a planning-first foundation for the Sterling-X concept.

## Current framing

OpenOMS is a reference implementation of the **decisioning brain** inside an Order Management System (OMS). It focuses on:

- deterministic order sourcing
- inventory-aware reservation workflows
- promise-date computation
- replayable decision logs
- MCP-compatible agent access
- a strict deterministic / LLM split

## Why this exists

Most commerce platforms expose operational APIs, but not the fulfillment decisioning layer itself. OpenOMS aims to make that layer inspectable, replayable, and understandable.

## Current status

This repo is in the **planning / architecture** phase.

Start here:
- `docs/product-thesis.md`
- `docs/v0.1-plan.md`
- `docs/architecture-notes.md`

## Initial build recommendation

Build the smallest credible vertical slice first:

1. Postgres + Redis + FastMCP running via Docker Compose
2. Seed a small synthetic dataset
3. Implement domain models and persistence
4. Ship `get_inventory`, `source_order`, and `explain_decision`
5. Support single-line orders only in v0.1
6. Use deterministic promise dates first

## Working naming note

The assistant identity name is currently **Sterling-X** as a provisional bootstrap choice, but the product/repo naming can change later without affecting the architecture.
