# Implementation Handoff (Stage 1)

This document is the complete handoff for building the game at the current milestone: content/specs are prepared and audited; next work is engine + backend + web implementation.

Project root: `Game/`

## 1) What This Project Is

- Game: `剑之初程：淬炼之路`
- Ruleset/content version: `v3.3.0` (frozen)
- Genre: single-run narrative choice game with a 12-week structure.
- Loop:
  1. Opening (ink mood, voiceover)
  2. Attribute allocation (250 points across 6 attributes; numbers visible here)
  3. Weeks 1–11: each week presents 3 options drawn deterministically from a fixed set of 6; player chooses 1; results are applied immediately; numbers are hidden during play
  4. Week 12: finals tactics (attribute-locked), deterministic win roll
  5. End: win / 惜败 / 失利 / 崩解, then deterministic “年度成长报告” + achievements
- Determinism: same `seed + allocation + choices` must always produce the same presented options, the same `±n` rolls, the same final outcome, and the same score.

## 2) Current Status (What’s Done)

All Stage 1 content/spec work is complete enough to start implementation:

- Frozen ruleset decisions in `Game/docs/ruleset/v3.3.0.md`.
- Stable ID conventions in `Game/docs/content-ids.md`.
- Engine/server/web boundary contract in `Game/docs/engine-contract.md`.
- Deterministic report mapping spec (no LLM) in `Game/docs/report-mapping.md`.
- Versioned executable content in `Game/content/v3.3.0/` (JSON) including:
  - Numeric truth for all week option deltas, finals requirements/deltas, redlines, weights/factors.
  - Verbatim story blocks: opening, week narratives, personality long prose, collapse endings, “给体验者的话”, v3.3 changelog, report template/sample reference.
  - UI string bundle and experience/feedback copy.
  - Per-option post-choice consequence blurbs (`result_cn`) written to fulfill “叙事反馈” while hiding numbers.
- Content validator: `Game/tools/validate_content.py` (passes).

## 3) Canonical Specs (Single Source of Truth)

When there is ambiguity or conflicts between the original docs, the implementation must follow:

- `Game/docs/ruleset/v3.3.0.md`

Key frozen decisions (must implement exactly):

- Collapse score factor: `0.80`.
- Warning threshold: `warn_threshold = redline + 5`.
- Attribute clamp after each application: `[0, 100]`.
- `±n` randomness: integer-only, deterministic, center-biased via binomial:
  - `k ~ Binomial(2n, 0.5)`
  - `delta = k - n`
- Finals win rate:
  - `base = 0.70`
  - `excess`:
    - single req: `attr - req`
    - dual req: `min(skill-60, mind-60)`
  - `win_rate = clamp(0.70 + floor(excess/10) * 0.05, 0.0, 0.95)`
- Win tiers by excess (only if requirements met and roll wins):
  - `excess >= 10` → 华丽胜利
  - `excess >= 5` → 一般胜利
  - else → 险胜
- Loss tiers:
  - Requirements met but roll loses → 惜败 (factor 0.97)
  - Requirements not met → 失利 (factor 0.94)
- Score microtweak: deterministic ±(1–3)% with half-up rounding (see ruleset doc).
- `personality_end`: re-classify on end-of-run attributes using the same classifier.

## 4) Files You Must Read and Treat As Truth

### A) Content (Executable JSON)

Directory: `Game/content/v3.3.0/`

- `rules.json`
  - Allocation constraints, redlines, warning offset, scoring weights/factors, grade bands, RNG config, rounding mode.
- `weeks.json`
  - Weeks 1–12.
  - Weeks 1–11:
    - `options[6]`: `title_cn`, `desc_cn` (verbatim neutral option description), `deltas` (numeric truth), `result_cn` (post-choice consequence narrative).
  - Week 12:
    - `options` empty (final tactics live elsewhere).
- `finals.json`
  - 6 tactics: `requirements`, `on_meet_apply`, `on_fail_apply`, plus `name_cn` and `desc_cn`.
- `personality.json`
  - 8 personality types, conditions, priority order, CN prose (long is verbatim from story doc).
  - Default fallback behavior is defined in ruleset doc; implementation should return the `is_default=true` type when no other match.
- `achievements.json`
  - Core/special/legend achievements with machine-checkable `conditions` and `desc_cn`.
- `endings.json`
  - Collapse endings (verbatim text).
- `intro.json`
  - Opening scene + voiceover lines (verbatim, including pacing blank lines).
  - Attribute allocation descriptions/rules (verbatim).
- `experience.json`
  - Journey steps, feedback rules copy, and “给体验者的话” (verbatim line array).
- `ui.json`
  - CN UI strings (nav, allocation errors, week/final/report labels, auth labels).
- `changelog.json`
  - v3.3 update summary (verbatim), including item-3 bullets and a summary line.
- `report_templates.json`
  - Deterministic report templates with placeholders.
- `report_reference.json`
  - Verbatim “年度成长报告（完整模板）” and the provided sample win report, stored for reference/UI parity.

### B) Specs/Docs

- `Game/docs/ruleset/v3.3.0.md` (canonical rules)
- `Game/docs/content-ids.md` (stable IDs)
- `Game/docs/engine-contract.md` (server-authoritative + resume/tamper-proofing)
- `Game/docs/report-mapping.md` (deterministic report field generation)
- `Game/docs/content-validation.md` (what content must satisfy)

### C) Validation Tool

- `Game/tools/validate_content.py`
  - Must be run in CI and locally.
  - Command: `python Game/tools/validate_content.py`

## 5) Important Notes About “Verbatim” vs “Authored”

Verbatim (pulled from the provided story doc dump):
- Opening scene + voiceover lines: `intro.json`
- Personality long prose: `personality.json`
- Week narrative blocks: `weeks.json` (`narrative_cn`)
- Neutral option descriptions: `weeks.json` (`desc_cn`)
- Collapse ending texts: `endings.json`
- “给体验者的话”: `experience.json`
- v3.3 changelog: `changelog.json`
- Annual report template + sample: `report_reference.json`

Authored for implementation completeness (not present as dedicated blocks in the docs):
- Per-option post-choice consequence blurbs: `weeks.json` (`result_cn`)
- UI strings bundle: `ui.json`
- Deterministic report templates and mapping rules: `report_templates.json` + `docs/report-mapping.md`

## 6) Tech Stack to Use (Implementation)

Team preference: Python.

### Backend (API + persistence)
- Python 3.11+ (or 3.12)
- FastAPI
- SQLAlchemy 2.0 + Alembic
- Postgres for production; SQLite acceptable for local dev
- Password hashing: Argon2 (`argon2-cffi`) preferred (bcrypt acceptable)
- Cookie-based session:
  - Signed cookie session for `guest_id` and/or `user_id`.
  - All gameplay state must live in DB, not in the cookie.

### Engine (pure logic)
- Pure Python package under `Game/engine/`
- No DB/HTTP/time; deterministic RNG only.
- Loads JSON content from `Game/content/v3.3.0/`.

### Frontend (polished SPA)
- React + TypeScript + Vite
- TailwindCSS
- Motion/animation: Framer Motion recommended
- Rendering:
  - Some text contains markdown markers like `**...**` and quote markers `>`.
  - Either render as plain pre-wrapped text, or use a strict markdown renderer (no raw HTML).

## 7) Implementation Order (Must Follow)

1. Engine + tests (pure python)
2. Backend API + DB persistence (server-authoritative + resumable guest)
3. SPA UI (polish) wired to API with “hidden numbers during weeks”

## 8) Engine Requirements (Detailed)

### A) Deterministic RNG (do not use Python’s salted hash)

Implement a stable RNG that is version-independent:
- Recommended: `splitmix64` or `xorshift64*`.
- You must be able to generate:
  - deterministic integers in a range
  - deterministic coin flips (for binomial)
  - deterministic threshold checks for win_rate (use integers; avoid floats if possible)

Do not use:
- Python `hash()` (salted per process)
- Wall clock time

### B) State model (minimum)

State must track:
- `ruleset_version`, `seed`, `week`, `status`
- `attributes` (6 ints)
- `min_attributes` (track min observed values per attr for achievements)
- `personality_start`, `personality_end` (end computed at finish)
- Per-week history records:
  - presented 3 option IDs
  - chosen option ID
  - resolved `±n` rolls
  - applied deltas (resolved ints)
- Final record if reached:
  - `tactic_id`, `requirements_met`, `win_rate`, deterministic roll, `final_result`, `final_tier`
- Collapse record if collapsed:
  - which attribute triggered
  - which ending ID

### C) Weekly option presentation (3-of-6)

For weeks 1–11:
- Deterministically pick 3 distinct option IDs out of 6.
- Store these IDs for later verification and resume.

Suggested method:
- Deterministically shuffle the 6 option IDs with RNG seeded by `(seed, week, "present")`, then take the first 3.

### D) Applying deltas

- Resolve `{plus_minus:n}` using binomial center-biased integer roll.
- Apply deltas, clamp `[0,100]`, update mins.
- Immediately check redlines (`<= redline`):
  - if any triggers: status `collapsed` and stop.
- Compute warning flags for UI (danger zone):
  - `value <= redline + 5`

### E) Finals

Use `finals.json` for requirements and attribute changes.

- If requirements not met:
  - apply `on_fail_apply`
  - final_result = `失利`
- If met:
  - compute `excess` and `win_rate`
  - deterministic roll:
    - recommended: `roll_int = rand_int(0, 9999)` and win if `< floor(win_rate*10000)`
  - apply `on_meet_apply` when reqs are met
  - if roll wins:
    - tier by excess (fancy/normal/close)
  - if roll loses:
    - final_result = `惜败`

### F) Scoring

Implement exactly per `Game/docs/ruleset/v3.3.0.md` and `rules.json`:
- weighted sum → factor → deterministic microtweak → half-up rounding

### G) Personality and achievements

- `personality_end`: re-classify on end attributes.
- Achievements:
  - Implement machine-checkable conditions from `achievements.json`.
  - Must support:
    - `completed_weeks_eq`
    - `all_attrs_between_inclusive`
    - `attr_gte`
    - `total_score_gte`
    - `personality_end_not_equal_start`
    - `at_least_k_of_attrs_gte`
    - `no_attr_below`
    - `attr_never_below` (use `min_attributes`)
    - `final_win_with_requirements_met`
    - `not_collapsed`

### H) Report generation (no LLM)

Implement deterministic report field computation using:
- `Game/docs/report-mapping.md`
- Templates in `Game/content/v3.3.0/report_templates.json`

Also keep `report_reference.json` as a “reference view” in UI; it does not need to be generated.

## 9) Backend/API Requirements (Detailed)

### A) Identity and resume rules

- Guest:
  - Same-device resume only (cookie).
  - Exactly 1 active run.
- User:
  - Username/password.
  - Multiple concurrent runs supported.

### B) Server-authoritative / anti-tamper

Server must:
- Persist presented option IDs per week.
- Reject a choice if it was not in the presented 3.
- Persist resolved `±n` roll results per choice so resume is identical.

### C) Endpoints (minimum Stage 1)

Implement at least:

- `POST /api/guest/init`
  - create guest cookie if missing
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `POST /api/runs`
  - create run (seed, ruleset_version, status=in_progress, week=0)
  - for guest: set as the active run (replacing/archiving previous)
- `POST /api/runs/{run_id}/allocate`
  - validate 250 sum and 25..60 range
  - compute personality_start
  - return week 1 payload with 3 options presented
- `GET /api/runs/active`
  - guest: return active run resumable payload
- `GET /api/runs`
  - user: list all runs
- `GET /api/runs/{run_id}`
  - return current screen payload for resume
- `POST /api/runs/{run_id}/choose`
  - verify option_id in presented 3
  - apply engine transition
  - return next screen payload, plus the chosen option `result_cn` and warning flags
- `POST /api/runs/{run_id}/final`
  - apply finals transition
  - return outcome and then report payload
- `POST /api/runs/{run_id}/finish`
  - compute score/grade/achievements/report and store snapshot

### D) “Hidden numbers” response policy

During weeks 1–11:
- Do not include numeric `attributes` or `deltas` in responses used by the UI.
- Return:
  - narrative text, option titles/descriptions, `result_cn` after choosing
  - warning flags (danger attributes)

Only final report responses include numeric attributes and score.

## 10) Frontend Requirements (Detailed)

### Screens

- Opening:
  - display `intro.opening.scene_cn`
  - animate `voiceover_lines_cn` line-by-line; empty strings represent deliberate pauses
- Allocation:
  - display `intro.allocation` (attribute descriptions + rules)
  - allow numbers visible here
- Week (1–11):
  - render `weeks[n].narrative_cn` (preserve line breaks; markdown recommended)
  - show 3 options (title + desc)
  - on choice:
    - show `result_cn` before moving to next week
    - show feedback glows using warning flags
- Finals:
  - show `weeks[12].narrative_cn`
  - list 6 tactics from `finals.json` using only player-facing flavor fields
- Report:
  - render deterministic report sections returned by backend
  - show radar chart and numeric attributes
  - show achievements

### UX constraints

- Weeks 1–11: never show numeric attributes/deltas.
- Week 12 + report: numbers allowed.

## 11) Testing and CI Requirements

### Content validation
- Always run: `python Game/tools/validate_content.py`

### Engine tests
- Golden tests:
  - fixed seed + allocation + choices => exact output
- Invariants:
  - determinism (repeat run yields same)
  - clamp [0,100]
  - redline collapse immediate
  - must choose among presented 3

## 12) Known “Spec Deviations” vs Original Docs

These are deliberate clarifications; implement them as written:

- Collapse score factor is fixed to `0.80` (conflict existed across docs).
- RNG must be seed-only deterministic (original backend doc mentioned “选择时间” in one place).
- Rounding is defined as `round_half_up` to avoid platform `round()` differences.
- `白纸型` is treated as default fallback when no other personality matches; its story condition (35–45) remains in content for flavor/labeling, but fallback behavior is enforced by the ruleset.

## 13) Quick “Next Action” Checklist for the Coding Model

1. Add `Game/engine/` and implement the engine strictly per ruleset/content.
2. Add engine unit tests and golden tests; add CI running validator + tests.
3. Add `Game/server/` FastAPI app and DB schema/migrations; implement endpoints.
4. Add `Game/web/` SPA; render content + connect to API; enforce hidden-number rule.
