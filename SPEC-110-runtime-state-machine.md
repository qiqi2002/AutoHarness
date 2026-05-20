# SPEC-110: Runtime State Machine 规范

## 1. 目标

定义 Runtime 的合法状态转移与执行守卫，避免流程漂移与状态不一致。

## 2. 状态集合

- `INIT`
- `PLANNING`
- `BUILDING_AGENTS`
- `EXECUTING`
- `AWAITING_ACCEPTANCE`
- `REPLANNING`
- `FINALIZING`
- `DONE`
- `FAILED`

## 3. 状态转移（v1）

- `INIT` → `PLANNING`
- `PLANNING` --`update_plan`--> `BUILDING_AGENTS`
- `BUILDING_AGENTS` --`create_agent|update_agent`--> `BUILDING_AGENTS`
- `BUILDING_AGENTS` --`dispatch`--> `AWAITING_ACCEPTANCE`
- `EXECUTING` --`dispatch`--> `AWAITING_ACCEPTANCE`
- `AWAITING_ACCEPTANCE` --`accept_output(Accept)`--> `EXECUTING`
- `AWAITING_ACCEPTANCE` --`accept_output(Reject)`--> `REPLANNING`
- `REPLANNING` --`update_plan|update_agent`--> `EXECUTING`
- `EXECUTING` --`finish`--> `FINALIZING`
- `FINALIZING` → `DONE`
- `*` --fatal error--> `FAILED`

## 4. Guard 规则

### 4.1 Schema Guard
每个 action 必须通过 `SPEC-100` 对应 schema 校验。

### 4.2 State Guard
仅允许当前状态支持的 action；否则返回 `E_ACTION_NOT_ALLOWED`。

### 4.3 Dependency Guard
- `dispatch` 前校验 agent 存在。
- 工具模式下校验 tool 存在、参数通过 schema。

### 4.4 Lock Guard
当 `temp_buffer != null`，除 `accept_output` 外全部拒绝，返回 `E_TEMP_BUFFER_LOCKED`。

## 5. 双缓冲提交语义

- `dispatch` 只写 `temp_buffer`，不改 `current_payload`。
- `accept_output.Accept`：`temp_buffer -> current_payload`，然后清空 `temp_buffer`。
- `accept_output.Reject`：仅清空 `temp_buffer`，`current_payload` 保持不变。

## 6. 一致性与恢复

- 使用 `state_version` 做乐观锁，防止并发覆盖。
- 每次成功提交 `current_payload` 后可创建 checkpoint。
- 出现不可恢复错误时，Runtime 可回滚到最近 checkpoint 并进入 `REPLANNING` 或 `FAILED`。

## 7. 终止条件

任务在以下任一条件终止：

1. 收到合法 `finish` 并完成 `FINALIZING -> DONE`。
2. 触发 fatal error 且回滚失败，进入 `FAILED`。
3. 达到系统硬限制（最大轮数/预算上限）并被策略中止。
