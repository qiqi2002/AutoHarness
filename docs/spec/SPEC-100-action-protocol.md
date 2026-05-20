# SPEC-100: Action Protocol 规范

## 1. 协议目标

定义 Orchestrator 与 Runtime 间唯一控制接口，确保可验证、可审计、可版本化。

## 2. Action Envelope

每条指令必须是单个 JSON 对象：

```json
{
  "schema_version": "1.0",
  "action_id": "uuid",
  "trace_id": "uuid",
  "action_type": "create_agent | update_agent | update_plan | dispatch | accept_output | finish",
  "payload": {}
}
```

### 字段约束

- `schema_version`：当前固定 `1.0`。
- `action_id`：幂等键；重复提交不可重复执行。
- `trace_id`：同一次任务链路追踪 ID。
- `action_type`：仅允许 6 个枚举。
- `payload`：需匹配对应 action schema。

## 3. 六类 Action

### 3.1 `create_agent`

```json
{
  "name": "string",
  "role": "string",
  "prompt": "string",
  "io_schema": {"type": "object"}
}
```

语义：创建并注册 Sub-Agent。

### 3.2 `update_agent`

```json
{
  "name": "string",
  "new_prompt": "string",
  "reason": "string"
}
```

语义：更新已注册 agent 的 prompt。

### 3.3 `update_plan`

```json
{
  "plan_description": {"type": "object"},
  "execution_config": {"type": "object"},
  "reason": "string"
}
```

语义：更新全局规划（包含 payload 结构约定）。

### 3.4 `dispatch`

```json
{
  "target_agent_name": "string",
  "input_source": {
    "type": "variable",
    "data": {}
  }
}
```

或：

```json
{
  "target_agent_name": "string",
  "input_source": {
    "type": "tool",
    "data": {
      "tool_name": "string",
      "arguments": {}
    }
  }
}
```

语义：将输入路由到目标 Sub-Agent；若 `type=tool` 则 Runtime 先执行工具，并把工具结果作为输入的一部分交给目标 Sub-Agent。Action 中的 `input_source.data` 不包含工具结果，工具结果只存在于 Runtime 内部调度上下文和 trace/snapshot 实现中。

### 3.5 `accept_output`

```json
{
  "decision": "Accept | Reject",
  "reason": "string"
}
```

语义：对 `temp_buffer` 内容进行提交或丢弃。

### 3.6 `finish`

```json
{
  "final_result": {},
  "summary": "string"
}
```

语义：结束任务并输出结果。

## 4. 通用执行约束

1. 当 `temp_buffer != null` 时，只允许 `accept_output`。
2. `dispatch` 必须校验 `target_agent_name` 存在。
3. `dispatch` 使用工具时必须校验 `tool_name` 存在且 `arguments` 为 object。
4. 工具执行结果必须是 object，否则返回 `E_SCHEMA_INVALID`。
5. Sub-Agent 候选输出必须是 object，否则返回 `E_SCHEMA_INVALID`。
6. `accept_output` 只能在存在 `temp_buffer` 时执行；若无待验收输出，返回 `E_ACTION_NOT_ALLOWED`。
7. `finish` 只能在可终止状态触发（详见 SPEC-110）。
8. M1 中 `finish.final_result` 必须等于当前已接受的 `current_payload`，否则返回 `E_ACTION_NOT_ALLOWED`。

## 5. 错误码（v0）

- `E_SCHEMA_INVALID`：JSON 或字段不合法
- `E_ACTION_NOT_ALLOWED`：当前状态不允许该动作
- `E_AGENT_NOT_FOUND`：目标 agent 不存在
- `E_TOOL_NOT_FOUND`：目标工具不存在
- `E_TEMP_BUFFER_LOCKED`：存在待验收结果，操作被锁
- `E_IDEMPOTENCY_CONFLICT`：重复 action_id 冲突

## 6. Machine-Readable Contract

Initial JSON Schema is maintained at `schemas/action-envelope.schema.json`.
