# RFC-0001: 多智能体自主搭建 Harness 系统总览

## 1. 背景与目标

我们希望构建一个由 Orchestrator Agent 主导、可控可审计可演进的多智能体协作框架，用于自主搭建与优化任务 pipeline/harness。

### 1.1 目标

- 将“流程决策”与“数据修改/工具执行”彻底解耦。
- 用受限 Action 协议约束编排 Agent 行为。
- 用双缓冲验收（`current_payload` / `temp_buffer`）保障数据不可被直接篡改。
- 形成 Build → Execute → Refine 的持续优化闭环。

### 1.2 非目标

- 不追求无监督完全自治。
- 不在 v1 强制引入复杂多租户隔离。
- 不在本 RFC 中定义具体业务 Agent prompt 模板。

## 2. 设计原则

1. 控制平面与数据平面分离。
2. 规划与执行分离。
3. 逻辑与工具分离。
4. 默认拒绝（Deny-by-default）与最小权限。
5. 每一步可追溯、可回放。
6. 先验收后提交（Two-phase commit）。

## 3. 系统角色与高层架构

- **Orchestrator Agent**：只输出结构化 Action；不直接改 payload，不直接调用工具。
- **Sub-Agent**：执行局部任务，返回候选输出。
- **Pipeline Runtime**：解析、校验、执行 Action；维护状态机。
- **Tool Host/Sandbox**：托管工具并施加权限和资源限制。
- **Judge（可选）**：自动质量评估。
- **Human Gate（可选）**：关键步骤人工审批。

## 4. 生命周期

1. **Build**：定义任务规划、实例化子 Agent、明确 payload 约定。
2. **Execute**：按状态机调度子 Agent 与工具执行，产出候选结果。
3. **Accept/Reject**：通过验收动作决定是否提交到 `current_payload`。
4. **Refine**：基于失败原因、成本和质量指标更新 plan/agent。
5. **Finish**：输出结果与过程摘要。

## 5. 范围边界

- 本 RFC 只定义总体框架与运行原则。
- 协议细节见 `SPEC-100-action-protocol.md`。
- 状态机细节见 `SPEC-110-runtime-state-machine.md`。

## 6. 路线图（摘要）

- **M1（跑通）**：6 Action + 基础状态机 + 强制验收锁。
- **M2（可靠）**：重试、超时、checkpoint 回滚、基础观测指标。
- **M3（自治）**：Refiner 自动触发策略、A/B 方案比较。

## 7. 开放问题

- Judge 在 v1 是否默认启用？
- 何种任务默认启用 Human Gate？
- 自主更新 prompt 的审批阈值如何定义？
