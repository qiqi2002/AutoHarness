# AutoHarness

AutoHarness is a controllable and auditable multi-agent harness/runtime for building and refining task pipelines.

The core idea is simple:

- A strong Orchestrator designs a reusable `HarnessSpec` for a task.
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
5. `docs/spec/SPEC-120-webwalk-tool.md`
6. `docs/spec/SPEC-130-harness-spec.md`
7. `schemas/action-envelope.schema.json`
8. `schemas/harness-spec.schema.json`
9. `examples/m1-action-trace.json`

## Maintenance Rule

Any behavior-changing implementation should update at least one of:

- a SPEC
- a schema
- an example trace
- a conformance test
- an ADR

## M1 Local Test Entry

Use the project-local environment:

```powershell
python -m venv .venv
$env:PIP_CACHE_DIR='.pip-cache'; .\.venv\bin\python.exe -m pip install -e ".[test,demo]"
```

Run the example trace through the deterministic M1 runtime:

```powershell
.\.venv\bin\python.exe -m autoharness.run_trace examples/m1-action-trace.json
```

Run the tool-backed trace:

```powershell
.\.venv\bin\python.exe -m autoharness.run_trace examples/tool-action-trace.json
```

Run the Runtime-backed WebWalk tool trace:

```powershell
.\.venv\bin\python.exe -m autoharness.run_trace examples/webwalk-tool-action-trace.json
```

Validate the first generated harness spec:

```powershell
.\.venv\bin\python.exe -m autoharness.schema_validation schemas/harness-spec.schema.json examples/harnesses/atcoder_problem_editorial_abc220_a.harness.json
```

Validate both baseline harness specs:

```powershell
.\.venv\bin\python.exe -m autoharness.schema_validation schemas/harness-spec.schema.json examples/harnesses/atcoder_latest_editorial.harness.json
```

Run a generated harness end to end with Runtime WebWalk, task-aware weak executor, and acceptance validation:

```powershell
.\.venv\bin\python.exe -m autoharness.run_harness examples/harnesses/atcoder_problem_editorial_abc220_a.harness.json --output artifacts/harness_runs/atcoder_problem_editorial_abc220_a.json --trace-output artifacts/harness_runs/atcoder_problem_editorial_abc220_a.trace.json
.\.venv\bin\python.exe -m autoharness.run_harness examples/harnesses/atcoder_latest_editorial.harness.json --output artifacts/harness_runs/atcoder_latest_editorial.json --trace-output artifacts/harness_runs/atcoder_latest_editorial.trace.json
```

Use the model-backed weak executor instead of the task-aware executor:

```powershell
$env:MINIMAX_API_KEY='...'
$env:MINIMAX_BASE_URL='https://api.minimaxi.com/v1/'
$env:MINIMAX_MODEL='MiniMax-M2.7-highspeed'
$env:AUTOHARNESS_LLM_INSECURE_TLS='1'
.\.venv\bin\python.exe -m autoharness.run_harness examples/harnesses/atcoder_latest_editorial.harness.json --executor model
```

Smoke-test model-backed strong builder and weak executor adapters with the same API:

```powershell
$env:MINIMAX_API_KEY='...'
$env:MINIMAX_BASE_URL='https://api.minimaxi.com/v1/'
$env:MINIMAX_MODEL='MiniMax-M2.7-highspeed'
$env:AUTOHARNESS_LLM_INSECURE_TLS='1'
.\.venv\bin\python.exe scripts\model_harness_smoke.py
```

Run the current test suite:

```powershell
.\.venv\bin\python.exe -m unittest discover -s tests
```

Schema contract tests use `jsonschema` when installed:

```powershell
.\.venv\bin\python.exe -m unittest discover -s tests
```

Without `jsonschema`, runtime tests still run and schema contract tests are skipped.

## M1 Implemented Surface

- Action envelope and payload validation
- Runtime state guard
- idempotency guard
- temp buffer lock guard
- agent dependency guard
- fake tool dispatch guard
- Tool Host dispatch abstraction
- HarnessSpec schema and deterministic harness runner
- double-buffer accept/reject semantics
- `finish.final_result == current_payload` enforcement
- happy-path, tool-path, and negative trace fixtures

## Demo: AtCoder WebWalk

The AtCoder demo walks pages directly from AtCoder without using a search tool.

Run WebWalk extraction without a model:

```powershell
.\.venv\bin\python.exe -m autoharness.demos.atcoder_latest_editorial --no-model
```

Run WebWalk plus MiniMax structuring:

```powershell
$env:MINIMAX_API_KEY='...'
$env:MINIMAX_BASE_URL='https://api.minimaxi.com/v1/'
$env:MINIMAX_MODEL='MiniMax-M2.7-highspeed'
.\.venv\bin\python.exe -m autoharness.demos.atcoder_latest_editorial
```

The key is read only from the process environment and should not be committed.

If your local Python is behind a proxy with a self-signed certificate chain, set this only for local development:

```powershell
$env:AUTOHARNESS_LLM_INSECURE_TLS='1'
```

Find a specific problem editorial:

```powershell
.\.venv\bin\python.exe -m autoharness.demos.atcoder_problem_editorial abc220 abc220_a --no-model
```

Record and validate a live fixture:

```powershell
.\.venv\bin\python.exe -m autoharness.demos.atcoder_problem_editorial abc220 abc220_a --no-model --validate-schema --output examples/recorded/atcoder_problem_editorial_abc220_a.json
```

With MiniMax structuring:

```powershell
$env:MINIMAX_API_KEY='...'
$env:MINIMAX_BASE_URL='https://api.minimaxi.com/v1/'
$env:MINIMAX_MODEL='MiniMax-M2.7-highspeed'
.\.venv\bin\python.exe -m autoharness.demos.atcoder_problem_editorial abc220 abc220_a
```

Run the full agentic loop where the model emits WebWalk actions:

```powershell
$env:MINIMAX_API_KEY='...'
$env:MINIMAX_BASE_URL='https://api.minimaxi.com/v1/'
$env:MINIMAX_MODEL='MiniMax-M2.7-highspeed'
$env:AUTOHARNESS_LLM_INSECURE_TLS='1'
.\.venv\bin\python.exe -m autoharness.demos.agentic_webwalk abc220 abc220_a --validate-schema
```
