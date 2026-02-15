# 内容 ID 规范

目标：让 `content/`、引擎、服务端、前端在同一套稳定 ID 上协作，避免“文案改动导致逻辑漂移”。

## 版本

- `ruleset_version`: `v3.3.0`

## 属性 ID

- `stamina` / `skill` / `mind` / `academics` / `social` / `finance`

## 周事件与选项 ID

- 周 ID：`week_01`..`week_12`
- 选项 ID：`w01_o01`..`w01_o06`，以此类推

备注：
- 选项序号固定对应“该周 6 个固定选项”，不要因为文案调整而重排；需要替换时用同一 ID 更新内容。

## 决赛战术 ID

- `w12_t01`..`w12_t06`

## 崩解结局 ID

- `collapse_stamina`
- `collapse_skill`
- `collapse_mind`
- `collapse_academics`
- `collapse_social`
- `collapse_finance`

## 成就 ID

- 核心成就：`ach_core_01`.. (与 UI 展示顺序一致)
- 特殊成就：`ach_special_01`..
- 传说成就：`ach_legend_01`

