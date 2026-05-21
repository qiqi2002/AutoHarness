# SPEC-130: Harness Spec

## 1. Goal

Define the durable object produced by a strong Orchestrator model when it designs
a reusable harness for weaker task models.

A `HarnessSpec` describes:

- task inputs and expected output schema
- weak model agent roles and prompts
- tools the Runtime may expose
- workflow steps compiled into M1 Actions
- acceptance rules and evaluation fixtures

The spec is the boundary between harness generation and harness execution.

## 2. Contract

Machine-readable schema:

```text
schemas/harness-spec.schema.json
```

Every harness spec MUST include:

- `schema_version`
- `harness_id`
- `name`
- `task`
- `agents`
- `tools`
- `workflow`
- `acceptance`

## 3. Execution Semantics

Runtime MUST execute a harness by compiling it into the existing M1 Action
protocol:

1. `update_plan`
2. one `create_agent` per harness agent
3. workflow `dispatch` and `accept_output` steps
4. `finish` using the accepted `current_payload`

`finish.final_result` MUST be populated from Runtime `current_payload`, not from
the harness spec. This preserves double-buffer acceptance semantics.

## 4. Strong and Weak Model Boundary

The strong Orchestrator may generate or revise the HarnessSpec. Weak task models
operate only inside agent dispatches defined by that spec.

Runtime validates and executes the spec. Payload changes still occur only after
`accept_output.Accept`.

## 5. Current Scope

M1 supports deterministic local harnesses and tool-backed harnesses. Strong-model
generation is an adapter concern: generated specs must match this same schema
before execution.
