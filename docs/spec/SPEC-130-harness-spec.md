# SPEC-130: Harness Spec

## 1. Goal

Define the durable object produced by a strong Orchestrator model when it designs
a reusable harness for weaker task models.

A `HarnessSpec` describes:

- task inputs and expected output schema
- weak model agent roles and prompts
- tools the Runtime may expose
- an optional auditable plan graph that explains the Orchestrator intent
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

Every harness spec MAY include:

- `plan`
- `evaluations`

`plan`, when present, is the strong Orchestrator's intent record. It is not
directly executable. Runtime executes `workflow`; the plan explains why the
workflow exists and how to detect divergence.

A plan MUST include:

- `representation`: `sequence` or `graph`
- `summary`
- `nodes`
- `edges`
- `success_criteria`
- `divergence_policy`

Each plan node MUST include `workflow_step_ids` that point to workflow
`step_id` values. A plan node MAY point to multiple workflow steps, such as a
`dispatch` and the following `accept_output`.

## 3. Execution Semantics

Runtime MUST execute a harness by compiling it into the existing M1 Action
protocol:

1. `update_plan`
2. one `create_agent` per harness agent
3. workflow `dispatch` and `accept_output` steps
4. `finish` using the accepted `current_payload`

`finish.final_result` MUST be populated from Runtime `current_payload`, not from
the harness spec. This preserves double-buffer acceptance semantics.

`update_plan.plan_description` SHOULD include the HarnessSpec `plan` when one
is present, so the trace records both the Orchestrator intent and the executable
workflow selected to implement it.

Workflow tool arguments MAY contain runtime references:

```json
{"$from_current_payload": "editorial_url"}
```

Runtime MUST resolve those references against the latest accepted
`current_payload` before compiling the dispatch step into an M1 Action. Missing
paths are schema/runtime errors because they indicate the harness workflow
depends on data that has not been accepted yet.

## 4. Strong and Weak Model Boundary

The strong Orchestrator may generate or revise the HarnessSpec. Weak task models
operate only inside agent dispatches defined by that spec.

Runtime validates and executes the spec. Payload changes still occur only after
`accept_output.Accept`.

If a weak model output or Runtime observation contradicts the plan, the
Orchestrator SHOULD follow `plan.divergence_policy`. M1 records this policy but
does not yet automatically revise plans; current enforcement still happens
through workflow, acceptance rules, and explicit Orchestrator Actions.

## 5. Current Scope

M1 supports deterministic local harnesses and tool-backed harnesses. Strong-model
generation is an adapter concern: generated specs must match this same schema
before execution.
