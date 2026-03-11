# 架构说明 (Architecture)

本文档说明当前 `Game/` 工程的实现结构、模块职责、运行时数据流，以及各层之间的边界。

## 1. 项目分层

- `content/`
  - 版本化 JSON 内容包。
  - 是规则、文本、战术、成就、报告模板的唯一事实来源。
- `engine/`
  - 纯 Python、确定性、无数据库依赖。
  - 负责属性分配、周事件结算、决赛结算、人格判定、分数/评级、成就、报告生成。
- `server/`
  - FastAPI + SQLAlchemy + Alembic。
  - 负责身份、持久化、续玩、防篡改校验、将引擎状态转换为前端可消费的 screen payload。
- `web/`
  - React + TypeScript + Vite SPA。
  - 负责展示 screen、提交玩家选择、处理游客/登录态、回看模式与最终报告渲染。
- `tests/`
  - 引擎与 API 的回归测试。

## 2. 目录职责

### `engine/`

- [content.py](/workspace/Game/engine/content.py)
  - 加载 `content/v3.3.0/*.json`，缓存 `ContentBundle`。
- [models.py](/workspace/Game/engine/models.py)
  - 引擎内部状态模型：`RunState`、`WeekHistoryRecord`、`FinalRecord`、`CollapseRecord`。
- [rng.py](/workspace/Game/engine/rng.py)
  - 确定性随机数实现，基于 `SplitMix64`。
- [personality.py](/workspace/Game/engine/personality.py)
  - 初始/终局人格判定。
- [core.py](/workspace/Game/engine/core.py)
  - 主要状态机：
    - `new_run_state`
    - `allocate`
    - `present_week`
    - `apply_choice`
    - `resolve_final`
    - `finalize`
- [scoring.py](/workspace/Game/engine/scoring.py)
  - 成长积分、评级、微调计算。
- [achievements.py](/workspace/Game/engine/achievements.py)
  - 成就条件解释与解锁判断。
- [report.py](/workspace/Game/engine/report.py)
  - 基于终局状态确定性生成报告文本字段。

### `server/app/`

- [config.py](/workspace/Game/server/app/config.py)
  - 从环境变量构建运行配置。
- [db.py](/workspace/Game/server/app/db.py)
  - SQLAlchemy engine / session / declarative base。
- [models.py](/workspace/Game/server/app/models.py)
  - 数据库存储模型：
    - `User`
    - `Guest`
    - `Run`
    - `RunWeekLog`
- [state_codec.py](/workspace/Game/server/app/state_codec.py)
  - 数据库模型与引擎模型之间的双向映射。
- [service.py](/workspace/Game/server/app/service.py)
  - 服务层编排：
    - actor/session 解析
    - 创建 run
    - 分配属性
    - 选择周事件
    - 确认人格揭示
    - 决赛
    - 报告生成
- [presentation.py](/workspace/Game/server/app/presentation.py)
  - 将 `RunState` 转成面向前端的 screen payload。
  - 在这里控制“运行中不暴露数值”的 API 边界。
- [main.py](/workspace/Game/server/app/main.py)
  - FastAPI 路由层，仅做请求接入、调用 service、提交事务。
- [security.py](/workspace/Game/server/app/security.py)
  - 密码哈希与签名 cookie 会话。

### `web/src/`

- [api.ts](/workspace/Game/web/src/api.ts)
  - 浏览器端 API 请求封装。
- [types.ts](/workspace/Game/web/src/types.ts)
  - 前端 screen 类型。
- [App.tsx](/workspace/Game/web/src/App.tsx)
  - 单页主流程容器：
    - 会话初始化
    - 游客/用户模式切换
    - 当前 run 加载
    - 回看模式
    - 各类 screen 渲染
- `components/`
  - UI 子组件：
    - `EdgeWarnings`
    - `MarkdownText`
    - `RadarChart`

## 3. 核心数据模型

### 运行时权威状态

权威状态始终在服务端，前端只提交：

- 初始分配值
- 当前选中的 `option_id`
- 决赛 `tactic_id`
- 人格揭示确认动作

前端不提交任何运行中的属性值。

### 数据库存储

`Run` 负责保存当前快照：

- 当前周数、状态、属性、人格、预警、终局结果、成绩、报告

`RunWeekLog` 负责保存逐周日志：

- 本周展示过的选项
- 实际选中的选项
- 已解析出的随机 `roll`
- 应用后的 `deltas`
- 结果文案

这种设计让服务端可以：

- 验证“玩家只能选择本周展示过的选项”
- 在刷新或续玩时恢复同一局面
- 保证相同 seed 的确定性行为

## 4. 主要运行流程

### A. 游客首次进入

1. 前端调用 `POST /api/guest/init`
2. 服务端创建或恢复 `Guest`，写入签名 cookie
3. 前端调用 `GET /api/runs/active`
4. 若没有 active run，则调用 `POST /api/runs` 创建新 run
5. 服务端返回 `allocation` screen

### B. 属性分配

1. 前端提交六维初始值到 `POST /api/runs/{run_id}/allocate`
2. `service.allocate_run()` 调用 `engine.allocate()`
3. 引擎校验总点数、单项上下限，并计算 `personality_start`
4. 服务端预生成第 1 周展示选项并写入 `RunWeekLog`
5. 服务端返回 `personality_reveal` screen

### C. 周事件 1..11

1. 前端先确认人格揭示：`POST /api/runs/{run_id}/personality/ack`
2. 前端看到 `week` screen，只包含：
   - 周标题
   - 周叙事
   - 3 个可选项
   - 预警边缘提示
3. 玩家提交 `option_id`
4. `service.choose_option()`：
   - 读取当前 `RunWeekLog`
   - 校验该选项确实在本周展示列表内
   - 调用 `engine.apply_choice()`
   - 写回 `Run` 与 `RunWeekLog`
5. 若崩解，返回 `collapse` screen
6. 若进入第 12 周，返回 `finals` screen
7. 否则返回下一周 `week` screen

### D. 决赛

1. 前端提交 `tactic_id` 到 `POST /api/runs/{run_id}/final`
2. `engine.resolve_final()` 先判断达标，再进行确定性胜负 roll
3. `engine.finalize()` 计算成绩、评级、成就、报告
4. 服务端返回 `final_outcome`，并附带 `report_payload`

### E. 崩解后报告

1. 玩家在 `collapse` screen 点击生成归档
2. 前端调用 `POST /api/runs/{run_id}/finish`
3. 服务端对 collapsed state 调用 `engine.finalize()`
4. 返回 `report` screen

## 5. Screen 驱动的前后端契约

后端并不直接暴露数据库字段给前端，而是统一返回：

- `run_id`
- `status`
- `week`
- `screen`
- `payload`

当前 screen 类型：

- `allocation`
- `personality_reveal`
- `week`
- `finals`
- `final_outcome`
- `collapse`
- `report`

这层抽象的作用：

- 前端不需要理解底层引擎细节
- 服务端可以在 `presentation.py` 中统一控制敏感字段暴露范围
- 便于续玩与页面刷新恢复

## 6. “隐藏数值”是如何实现的

规则要求运行中不展示具体数值，当前实现通过两层保证：

### 引擎层

- 引擎内部仍计算完整属性、delta、roll、胜率等真实数值。

### 服务端展示层

- `presentation.py` 只返回当前 screen 需要的公开字段。
- 周事件与决赛 screen 不返回属性快照、delta、roll、胜率、内部应用值。
- 最终只有 `report` screen 返回完整属性与报告内容。

因此：

- 数据真实计算在服务端内部完成
- 玩家在运行中只能看到叙事与边缘反馈

## 7. 确定性实现要点

确定性的关键依赖于以下组合：

- run 创建时固定 `seed`
- `engine.rng.deterministic_rng()` 基于稳定输入生成随机流
- 服务端持久化：
  - 每周展示的选项
  - 每周 resolved rolls

这保证：

- 同一局刷新不会改变展示选项
- 恢复后不会重新掷出不同随机结果
- 测试可以用固定 seed 验证完整路径

## 8. 测试覆盖的重点

当前测试主要覆盖：

- 分配合法性
- 相同 seed 的完全确定性
- 不能选择未展示选项
- 属性 clamp 与崩解基本行为
- API 隐藏数值约束
- 决赛 outcome/report 返回格式
- 游客完成一局后可新建下一局

测试文件：

- [test_engine.py](/workspace/Game/tests/engine/test_engine.py)
- [test_api.py](/workspace/Game/tests/server/test_api.py)

## 9. 当前已知结构特征

- 后端层次清晰：`main -> service -> state_codec/presentation -> engine`
- `App.tsx` 仍是较大的前端容器组件，适合后续继续拆分
- 内容采用 JSON 驱动，方便版本冻结与内容替换
- 运行中 UI 与最终报告的边界清晰

## 10. 建议的阅读顺序

新接手此项目时，建议按下面顺序阅读：

1. [README.md](/workspace/Game/README.md)
2. [v3.3.0.md](/workspace/Game/docs/ruleset/v3.3.0.md)
3. [engine-contract.md](/workspace/Game/docs/engine-contract.md)
4. [architecture.md](/workspace/Game/docs/architecture.md)
5. [engine/core.py](/workspace/Game/engine/core.py)
6. [server/app/service.py](/workspace/Game/server/app/service.py)
7. [server/app/presentation.py](/workspace/Game/server/app/presentation.py)
8. [web/src/App.tsx](/workspace/Game/web/src/App.tsx)
