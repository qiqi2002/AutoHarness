# ADR-0001: Preserve the Orchestrator/Runtime Boundary

## Status

Accepted

## Context

AutoHarness needs agent-driven planning without letting free-form model output mutate system state directly. The project also needs replayability, auditability, and stable failure behavior.

## Decision

The Orchestrator may only emit structured Actions. The Runtime owns:

- schema validation
- state transition validation
- dependency validation
- tool execution
- payload mutation
- checkpoint and trace persistence

The Orchestrator must not directly mutate `current_payload`, write `temp_buffer`, or call tools outside the Runtime contract.

## Consequences

Benefits:

- runtime behavior is auditable and replayable
- protocol contracts can be validated independently
- tool permissions remain centralized
- payload integrity does not depend on prompt compliance

Tradeoffs:

- more upfront protocol work is required
- new behavior usually needs a SPEC/schema/example update
- agent flexibility is intentionally bounded
