# AutoHarness

AutoHarness is a controllable and auditable multi-agent harness/runtime for building and refining task pipelines.

The core idea is simple:

- The Orchestrator decides by emitting structured Actions.
- The Runtime validates Actions, applies state guards, and executes allowed work.
- Sub-Agents produce candidate outputs.
- Payload changes first enter `temp_buffer`.
- Only accepted outputs are committed to `current_payload`.

## Current Status

- Version: v0.1 draft
- Phase: design-first M1 planning
- M1 goal: Action protocol, runtime state machine, and double-buffer acceptance lock

## Repository Map

- `AGENTS.md`: working instructions for Codex and other coding agents
- `ROADMAP.md`: milestone plan
- `CONTRIBUTING.md`: maintenance and contribution rules
- `CHANGELOG.md`: project history
- `docs/rfc/`: design intent and system boundaries
- `docs/spec/`: normative protocol and runtime specifications
- `docs/adr/`: durable architecture decisions
- `schemas/`: machine-readable protocol schemas
- `examples/`: example traces and scenarios

## Recommended Reading Order

1. `docs/rfc/RFC-0001-system-overview.md`
2. `docs/adr/ADR-0001-orchestrator-runtime-boundary.md`
3. `docs/spec/SPEC-100-action-protocol.md`
4. `docs/spec/SPEC-110-runtime-state-machine.md`
5. `schemas/action-envelope.schema.json`
6. `examples/m1-action-trace.json`

## Maintenance Rule

Any behavior-changing implementation should update at least one of:

- a SPEC
- a schema
- an example trace
- a conformance test
- an ADR
