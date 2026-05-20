# Roadmap

## M1: Runnable Contract

Goal: prove the protocol and state machine with a minimal runtime.

Scope:

- Action envelope schema
- six Action payload schemas
- state transition table
- state guard
- dependency guard
- lock guard
- double-buffer accept/reject behavior
- example traces usable as conformance fixtures

Exit criteria:

- valid M1 traces pass schema validation
- invalid state transitions are rejected with stable error codes
- `dispatch` cannot mutate `current_payload` directly
- `accept_output.Accept` commits `temp_buffer`
- `accept_output.Reject` clears `temp_buffer` without changing `current_payload`

## M2: Reliable Runtime

Goal: make M1 resilient enough for repeated local use.

Scope:

- retry policy
- timeout policy
- checkpoint creation
- checkpoint rollback
- trace persistence
- basic observability metrics
- deterministic replay fixtures

## M3: Controlled Autonomy

Goal: allow bounded self-improvement without losing auditability.

Scope:

- Refiner trigger policy
- Judge integration
- Human Gate policy
- A/B plan comparison
- prompt update approval thresholds

## Deferred

- multi-tenant isolation
- distributed execution
- hosted UI
- broad tool marketplace integration
