# Product Thesis

## One-line thesis

OpenOMS is an open-source reference implementation of the **decisioning kernel** for modern order orchestration.

## What feels strong

- The central insight is solid: expose the orchestration brain, not just the order APIs.
- The deterministic / LLM split is the right architectural rule.
- MCP is a useful access layer for agent-native workflows.
- Replayable decision logs make the system auditable and educational.

## What should be true of v0.1

v0.1 should prove one thing clearly:

> A real order can enter the system, be sourced deterministically, produce a promise date, reserve inventory, and explain the result in plain language.

If that flow works end-to-end, the project is credible.

## Positioning recommendation

Prefer this framing:

**An open reference architecture for agent-native order orchestration.**

Avoid positioning it as:
- a full OMS replacement
- an AI shopping agent
- a production-grade fulfillment platform

## Strategic constraints

This should optimize for:
- clarity over completeness
- inspectability over scale
- deterministic correctness over model cleverness
- educational value over enterprise breadth

## Key differentiator

LLMs may interpret, explain, and triage.
Deterministic code owns state changes, commitments, and inventory mutation.
