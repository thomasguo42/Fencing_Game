# 剑之初程：淬炼之路 (Web Game)

本目录是该叙事选择游戏的项目根目录。

## Stage 1 实现目录

- `engine/`: 纯 Python 确定性引擎（规则、RNG、结算、成就、报告）
- `server/`: FastAPI + SQLAlchemy + Alembic（服务端权威、可续玩）
- `web/`: React + TypeScript + Vite + Tailwind SPA（周内隐藏数值）
- `tests/`: 引擎与 API 测试
- `.github/workflows/ci.yml`: CI（内容校验 + Python tests + Web build）

## Stage 1 (Playable Alpha) 目标

- 玩家可在网页完成：开场 → 属性分配 → 12周事件 → 决赛/崩解 → 年度成长报告。
- 全流程确定性：相同 seed + 相同选择序列 ⇒ 相同结果。
- 游玩中不显示具体数值（仅边缘微光反馈），仅在最终报告展示完整数值与雷达图。
- 游客可在同一设备续玩（一个进行中的 run）；账号用户可保留多个 run。

## 文档入口

- 规则冻结：`docs/ruleset/v3.3.0.md`
- 内容 ID 规范：`docs/content-ids.md`
- 引擎契约：`docs/engine-contract.md`
- 内容校验清单：`docs/content-validation.md`

## 内容数据 (v3.3.0)

所有可执行内容以版本化 JSON 存放于 `content/v3.3.0/`，作为引擎与服务端的唯一事实来源。

## 本地运行

推荐一键启动（含迁移 + API + Web，Web 走 `8080`）：
`bash scripts/dev_up.sh`

手动启动（推荐使用 Alembic，而不是 `create_all()`）：

1. 安装 Python 依赖
`python3 -m pip install -e '.[dev]'`

2. 运行迁移
`python3 -m alembic -c server/alembic.ini upgrade head`

3. 启动后端 API
`AUTO_CREATE_TABLES=false uvicorn server.app.main:app --reload --host 127.0.0.1 --port 8000`

4. 启动前端
`cd web && npm install && npm run dev`

如果你之前在开发环境用过 `AUTO_CREATE_TABLES=true` 启动服务，可能已经生成了包含表但缺少 `alembic_version`
的 `game.db`，此时直接 `upgrade head` 会报 “table ... already exists”。修复方式是先 `stamp` 再 `upgrade`：
`python3 -m alembic -c server/alembic.ini stamp 20260213_0002`
`python3 -m alembic -c server/alembic.ini upgrade head`

## 部署注意事项

- 生产环境必须设置强随机 `SECRET_KEY`（默认值会导致启动失败）。
- 建议生产环境使用 Alembic 迁移并设置：`APP_ENV=production`、`AUTO_CREATE_TABLES=false`。
- 按部署域名设置 `CORS_ORIGINS`（逗号分隔）。
- `CORS_ORIGINS` 不能包含 `*`（服务启用凭证跨域）。
- 跨站部署时设置：`COOKIE_SAMESITE=none` 且 `COOKIE_SECURE=true`（可配 `COOKIE_DOMAIN`）。
