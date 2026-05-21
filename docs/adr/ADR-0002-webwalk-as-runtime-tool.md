# ADR-0002: Model WebWalk Is a Runtime Tool

## Status

Accepted

## Context

The AtCoder demo needs a model to choose navigation steps while preserving the
core AutoHarness invariant:

> Orchestrator decides; Runtime validates and executes; payload changes only
> after acceptance.

Adding `open_url` and `open_link` as top-level Action types would expand M1
beyond its six Action contract and weaken the stability of the current protocol.

## Decision

WebWalk navigation is represented as a Runtime tool named `webwalk`. The
Orchestrator invokes it through the existing `dispatch` Action with
`input_source.type=tool`.

Agentic demos may keep using compact model actions, but those actions are
adapter-level planner messages. Runtime-facing execution continues to use the
M1 Action envelope and double-buffer acceptance semantics.

## Consequences

- The six M1 Action types remain unchanged.
- Web navigation benefits from existing Runtime guards: schema, state,
  dependency, tool existence, and temp-buffer lock guards.
- Tool observations can be accepted into `current_payload` only through
  `accept_output`.
- Future tools can follow the same Tool Host pattern without changing the
  top-level protocol.
