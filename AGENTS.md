# AGENTS.md

This file is the working guide for Codex and other coding agents maintaining AutoHarness.

## Project Intent

AutoHarness is a controllable, auditable multi-agent harness/runtime.

The central invariant is:

> Orchestrator decides; Runtime validates and executes; payload changes only after acceptance.

## Canonical Docs

- `README.md`: project entry point and reading order
- `ROADMAP.md`: current milestone direction
- `docs/rfc/`: design context, goals, non-goals, and scope
- `docs/spec/`: normative behavior that implementations must follow
- `docs/adr/`: durable architecture decisions
- `schemas/`: machine-readable protocol contracts
- `examples/`: executable or testable scenario traces

## Working Rules

1. Do not change protocol semantics without updating the matching SPEC.
2. Do not add runtime behavior that is not covered by a SPEC, schema, example, test, or ADR.
3. Keep RFCs descriptive, SPECs normative, and ADRs decision-focused.
4. Preserve the Orchestrator/Runtime boundary unless an ADR explicitly changes it.
5. Preserve double-buffer acceptance semantics unless an ADR explicitly changes them.
6. Prefer small commits grouped by concern.
7. Before finalizing implementation work, run the relevant schema and conformance tests once they exist.

## Current Milestone

M1: implement the minimum viable runtime contract:

- six Action types
- Action envelope validation
- runtime state guard
- agent/tool dependency guard
- `temp_buffer` lock guard
- `accept_output` commit/reject semantics

## Editing Guidance

- Use Markdown docs for human-facing design.
- Use JSON Schema for machine-checkable protocol contracts.
- Use examples as future conformance fixtures.
- Keep terminology stable: `Orchestrator`, `Runtime`, `Sub-Agent`, `Tool Host`, `current_payload`, `temp_buffer`, `Action`.

## When Unsure

Prefer writing a short ADR over silently changing the system model.
