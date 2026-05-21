# ADR-0003: HarnessSpec Is the Main Product Object

## Status

Accepted

## Context

AutoHarness should not be centered on a single task demo. The project goal is to
use a strong orchestration model to design harnesses that allow weaker models to
complete tasks under Runtime control.

The existing M1 Runtime already provides Action validation, Tool Host dispatch,
and double-buffer acceptance. What is missing is the durable object that the
strong Orchestrator produces.

## Decision

Introduce `HarnessSpec` as the main generated artifact.

The strong model generates or revises `HarnessSpec`. Runtime compiles a valid
spec into M1 Actions and executes it with weak model executors and approved
tools.

## Consequences

- Demos become examples of generated harnesses rather than one-off agents.
- Strong-model generation can evolve independently from Runtime execution.
- Weak model behavior is constrained by explicit agents, tools, workflow, and
  acceptance rules.
- Future evaluation and refinement loops can compare HarnessSpec revisions.
