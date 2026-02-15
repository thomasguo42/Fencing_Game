# 引擎契约 (Engine Contract)

本文件定义“引擎/服务端/前端”的边界与交互数据形态，Stage 1 以此为准。

## 核心原则

- 服务端权威：前端不提交属性数值，只提交“选择了哪个 ID”。
- 可复现：相同 seed 与相同选择序列 => 相同展示选项、相同随机 roll、相同结局与报告。
- 可续玩：服务端持久化每周“展示的 3 个选项”和每个 `±n` 的 roll 结果。

## RunState (概念字段)

- `run_id`
- `ruleset_version` (固定 `v3.3.0`)
- `seed` (整数或 32-bit/64-bit)
- `status`: `in_progress | collapsed | finished`
- `week`: 0..12
- `attributes`: 六维整数 (0..100)
- `personality_start`: 人格 ID
- `presented_options`: 当前周展示的 3 个 option_id (仅 week=1..11 用；week=12 展示战术)
- `history`:
  - 每周记录：`week_id`、`presented_option_ids[3]`、`chosen_id`、`resolved_rolls`、`applied_deltas`
- `final_outcome`: 胜/负/惜败等(若发生)
- `personality_end`: 终局人格(对终局属性重新判定)
- `score`、`grade`、`achievements`、`report` (完成后)

## 引擎 API (纯函数)

- `allocate(run_seed, attributes_initial) -> personality_start`
- `present_week(run_seed, ruleset_version, week, history_hash) -> option_id[3]`
- `apply_choice(state, option_id, resolved_rolls?) -> new_state`
  - resolved_rolls 可选：通常由引擎内部确定性生成；服务端存储并在续玩时重放。
- `resolve_final(state, tactic_id) -> new_state + outcome`
- `finalize(state) -> result(report, score, grade, achievements)`

## 服务端职责

- 生成 `run_id`、`seed`，维护 guest/user 身份。
- 存储并校验：
  - 当周展示的 3 个选项(防止“选择未展示选项”)
  - `±n` 的 roll 结果(确保续玩一致，便于 debug)
- 对外暴露状态给前端时，遵循“周事件阶段不暴露具体数值”的规则。

## 前端职责

- 渲染叙事、选项与反馈(微光/裂纹等)。
- 周事件阶段不展示数值；最终报告展示数值与雷达图。
- 处理断线/刷新后通过 `GET current run` 恢复。
