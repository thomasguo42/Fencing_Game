# 年度成长报告：确定性生成规则 (v3.3.0)

目标：不使用 LLM，基于 run 数据确定性生成报告字段，用于填充 `content/v3.3.0/report_templates.json` 的占位符。

## 输入数据 (引擎侧)

- 初始属性：`attrs_start[6]`
- 终局属性：`attrs_end[6]` (包含决赛结算后的属性；若崩解则为崩解时刻属性)
- 属性最小值轨迹：`attrs_min[6]` (run 全程每项属性的最小值)
- 选择历史：每周 `week_id`、`chosen_option_id`、`applied_deltas`、`presented_options`
- 决赛信息(如有)：`tactic_id`、`requirements_met`、`final_result`、`final_tier`
- 人格：`personality_start`、`personality_end`

## 关键派生量

- `delta[attr] = attrs_end[attr] - attrs_start[attr]`
- `strengths_final`：按 `attrs_end` 从高到低排序取前 2 (并列时按 `delta` 高者优先)
- `weaknesses_final`：按 `attrs_end` 从低到高排序取前 1 (并列时按 `attrs_min` 更低者优先)
- `risk_attr`：取 `attrs_min` 最低的那一项；若崩解则固定为崩解属性

## 文本字段规则

### `start_tone` / `end_tone`

取人格对应的短句(建议取 `personality.copy_cn.short`)。

### `strengths`

将 `strengths_final` 映射为属性名中文并用“与”连接：

- stamina=体能, skill=技巧, mind=心态, academics=学业, social=人际, finance=理财
- 例：`技巧与心态`

### `weaknesses`

同上，将 `weaknesses_final` 的 1 项映射为中文名。

### `turning_point`

确定性选择一个“转折周”：

1. 若存在首次进入预警(`attr <= redline+5`)的周：取最早一周。
2. 否则取“单周属性变化绝对值之和”最大的周：
   - `impact(week) = sum(abs(applied_deltas[attr]))`
   - 取 impact 最大的最早一周。

输出格式建议：

- `第{week_num}周《{week_title}》`

### `lesson`

按 `risk_attr` 映射为一句“学会什么”的短语：

- stamina → `节制与恢复`
- skill → `基础与耐心`
- mind → `稳定与呼吸`
- academics → `平衡与纪律`
- social → `联结与边界`
- finance → `规划与取舍`

### `coach_open`

基于 `personality_start` 给一句开头(固定映射，保持风格一致)：

- mirror → `你很快学会了“形”，但真正的答案在“里”。`
- flint → `你的火很旺，学会让它照亮，而不是烧伤。`
- analysis → `你的思考锋利，别忘了让身体也参与回答。`
- network → `你擅长联结，但剑道上终究要独对。`
- planner → `你会算每一步，偶尔也要允许一次不计回报的投入。`
- flash_flow → `你的灵感像闪电，先把地线接稳，才能不被反噬。`
- contrast → `你有光也有影，学会让它们彼此成全。`
- white_paper → `你从空白出发，能长成任何样子。`

### `notable_growth`

选择 `delta` 最大的 1 项属性中文名；若全为非正，则取 `strengths_final[0]`。

### `risk_area`

取 `risk_attr` 的中文名。

### `coach_motto`

按 `risk_attr` 给一句收束句(固定映射)：

- stamina → `别把身体当成燃料，把它当成同行的伙伴。`
- skill → `基础不是枷锁，是你最后一剑的底气。`
- mind → `真正的稳，不是没有波动，而是能把自己带回中心。`
- academics → `地基不稳，再锋利的剑也站不住。`
- social → `同伴能托住你，但出剑必须由你自己完成。`
- finance → `资源有限，取舍要清晰；无序才是锁链。`

### `teammate_line`

按终局 `social` 分档选择固定句：

- `social >= 60`：`“你很会把人串起来。到最后，我也愿意和你并肩。”——林薇`
- `social >= 45`：`“你有时候沉默，但关键时刻不会躲。加油。”——林薇`
- `social < 45`：`“你总是自己扛着。别忘了，训练馆里也有人愿意听你说。”——林薇`

### `tactic_name`

来自 `content/v3.3.0/finals.json` 对应战术 `name_cn`。

### `final_action`

按 `tactic_id` 输出固定短句：

- w12_t01 → `你把一年里最扎实的基本功压进这一剑，距离与时机像刻在骨里。`
- w12_t02 → `你把节奏握在手心，耐心像一面盾，逼对方先露出破绽。`
- w12_t03 → `你用体能把对方的防守撕开，连续的压迫不给喘息。`
- w12_t04 → `你用眼神与停顿诱导对方误判，在错位里完成致命一刺。`
- w12_t05 → `你执行预设方案，不被情绪带走，像按图纸完成最后的装配。`
- w12_t06 → `你把选择交给训练后的本能，在直觉里完成反应与衔接。`

## 崩解分支

若 run 崩解：

- 报告不使用 `final_moment_cn` 模板段落。
- `turning_point` 固定为崩解发生的周与崩解结局名。

