# Contributing

AutoHarness is design-first. Keep the written contract and implementation aligned.

## Change Types

- RFC changes explain goals, non-goals, and design boundaries.
- SPEC changes define required behavior.
- ADR changes record durable architecture decisions.
- Schema changes define machine-checkable contracts.
- Example changes demonstrate expected traces and edge cases.
- Runtime changes implement the contract.

## Required Updates

For behavior-changing work, update at least one of:

- `docs/spec/`
- `schemas/`
- `examples/`
- conformance tests
- `docs/adr/`

## Compatibility

Protocol changes must preserve `schema_version` semantics. Breaking protocol changes require:

- a SPEC update
- schema update
- migration note
- changelog entry

## Review Checklist

- Does this preserve the Orchestrator/Runtime boundary?
- Can the Runtime validate the behavior without trusting free-form text?
- Does this preserve double-buffer acceptance?
- Is the error behavior explicit?
- Is there an example or test fixture for the changed behavior?
