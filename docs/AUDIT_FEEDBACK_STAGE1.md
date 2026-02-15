# Stage 1 Implementation Audit Feedback (Strict vs. Frozen Ruleset v3.3.0)

Date: 2026-02-13  
Scope: `Game/` (engine/server/web/tools/tests/content/docs)  
Authoritative references (must match):  
- `Game/docs/ruleset/v3.3.0.md`  
- `Game/docs/IMPLEMENTATION_HANDOFF.md`  
- `Game/docs/engine-contract.md`  

Goal of this report: strictly flag anything that does not match the frozen spec/contract/Stage 1 goals, especially anything that leaks numbers/mechanics to players, breaks resumability/anti-tamper guarantees, or threatens production stability/security.

## Verification Performed

- Content validation: `python Game/tools/validate_content.py` passed (`OK: content v3.3.0 validated`)
- Tests: after installing `Game/pyproject.toml` deps, `python -m pytest -q` passed (8 passed)
- Codebase scan (high-risk keywords): no use of Python salted `hash()` or wall-clock time as RNG inputs in the engine; run seed generation uses `secrets.randbits` (acceptable for generating a new run seed)

## Blocking Issues (Must Fix Before Launch)

### 1) Final outcome leaks internal mechanics and numeric state (Critical)

Frozen requirements:
- During the week-flow stage (weeks 1..12), do not show numeric attributes or numeric deltas; only show feedback (edge glows / warnings). See “Numeric display rules” in `Game/docs/ruleset/v3.3.0.md`.
- The engine contract explicitly requires public exposure to follow “no numbers during week stage.” See `Game/docs/engine-contract.md`.
- The final report may show full numbers and radar chart; the `final_outcome` (and any in-run screens) should not reveal win probability, RNG roll, or applied delta numbers.

Current implementation:
- The `final_outcome` API payload includes `win_rate`, `roll_int`, `applied_deltas`, and `attributes`.
  - Location: `Game/server/app/presentation.py:91-114`
- The web UI renders “win rate” and tier directly to the player.
  - Location: `Game/web/src/App.tsx:343-379`, especially `Game/web/src/App.tsx:358-360`

Why this is a problem:
- This exposes the internal probability model and deterministic roll to players, violating the “hide inner mechanics” goal and enabling reverse engineering of the system.

Recommended fix direction:
- The public `final_outcome` payload should contain only player-visible fields, e.g.:
  - `final_result` (win / close loss / loss)
  - `tactic_name_cn`
  - `requirements_met` (yes/no)
  - Optional: a player-friendly localized tier label (e.g. “华丽/一般/险胜”), but do not return internal tier codes (`fancy/normal/close`) and do not return `win_rate` / `roll_int`.
- `win_rate`, `roll_int`, `applied_deltas`, and current `attributes` should remain DB/internal-only for debugging and audit, not in the player-facing API.

### 2) Finals tactics payload leaks `on_meet_apply` / `on_fail_apply` numeric deltas (Critical)

Frozen requirements:
- Week 12 may show requirements (thresholds), but in-run screens still must not show numeric attribute changes (deltas). See `Game/docs/ruleset/v3.3.0.md` numeric display rules.

Current implementation:
- Finals screen returns `content.finals["tactics"]` verbatim, which includes numeric `on_meet_apply` and `on_fail_apply` deltas.
  - Location: `Game/server/app/presentation.py:56-70` (`"tactics": content.finals["tactics"],`)
  - Data fact: `Game/content/v3.3.0/finals.json` tactics include keys `on_meet_apply` and `on_fail_apply`.

Recommended fix direction:
- Add a “public tactic DTO” on the server side and only return:
  - `id`, `name_cn`, `desc_cn`, `requirements`
- Frontend should render requirements only; do not display or rely on `on_meet_apply/on_fail_apply`.

## Security and Stability Issues (High Priority)

### 3) Default `SECRET_KEY` makes sessions forgeable (Critical security risk)

Current implementation:
- `Game/server/app/config.py:11` defaults `secret_key = "change-me-in-production"`.
- Session cookie is signed using `itsdangerous.URLSafeSerializer`. If production is deployed without changing the key, attackers can forge cookies containing `user_id`/`guest_id` and access/modify others’ runs.
  - Locations: `Game/server/app/security.py:13`, `Game/server/app/service.py:46-80`

Recommended fix direction:
- On startup, if `SECRET_KEY` equals the default, refuse to start in production mode.
- At minimum, make this a hard deployment requirement and document it loudly.

Secondary note:
- The token itself is not time-stamped (non-timed serializer). Cookie `max_age` helps, but stolen tokens can still be replayed within the cookie lifetime.

### 4) Migration strategy conflict: Alembic exists but app still calls `create_all()` (High risk of schema drift)

Current implementation:
- Alembic migration exists: `Game/server/alembic/versions/20260213_0001_init.py`
- App still executes `Base.metadata.create_all()` on startup:
  - Location: `Game/server/app/main.py:52-55`

Risk:
- `create_all()` can create schema that diverges from migrations, masking drift and causing production-only issues.

Recommended fix direction:
- Disable `create_all()` in production; run `alembic upgrade head` during deployment.
- If you want one-command local dev, gate it behind a dev-only env flag (e.g. `AUTO_CREATE_TABLES=true`).

### 5) SQLite default DB URL is cwd-relative and easy to mispoint (Stability / “lost save” risk)

Current implementation:
- `Game/server/app/config.py:10` default is `sqlite:///./game.db`.

Risk:
- Starting the server from different working directories will silently create/use different `game.db` files, creating “lost progress” and confusing behavior.

Recommended fix direction:
- Default to an absolute path derived from the project directory, or require explicit `DATABASE_URL`.

## Product / UX Gaps (Affects “playable” definition)

### 6) Web app has no register/login UI, only guest (Spec mismatch)

Current state:
- Backend implements `/api/auth/register|login|logout` (`Game/server/app/main.py:69-98`)
- Frontend boot flow is guest-only (`guestInit` + `getActiveRun/createRun`) with no auth UI.
  - Location: `Game/web/src/App.tsx:74-100`

Impact:
- “Guest and login both allowed” is not actually available on the website as a player feature.

Recommended fix direction:
- Add a minimal auth panel (register/login/logout) and after login support:
  - `GET /api/runs` list runs
  - pick a run to resume or create a new run

### 7) Chinese-only requirement not fully met (User-visible English errors)

Current state:
- Many HTTPException `.detail` strings are English, e.g.:
  - `Game/server/app/service.py:234` (`run is not in weekly stage`)
  - `Game/server/app/main.py:85` (`invalid credentials`)
- Frontend default error message is English:
  - `Game/web/src/api.ts:14` (`Request failed (...)`)

Recommended fix direction:
- Localize all user-visible errors to Chinese (or drive via `content/v3.3.0/ui.json`).
- Keep English only in logs, not in player responses.

## Medium / Low Priority Issues

### 8) Finals title is hardcoded in UI (Content-driven consistency)

Current state:
- Finals screen title is hardcoded to “最终淬炼：决胜一分”
  - Location: `Game/web/src/App.tsx:319`
- Server payload includes week 12 `title_cn`; UI should use the payload to avoid drift when content updates.

### 9) FastAPI `on_event` deprecation warning (Maintainability)

Current state:
- Uses `@app.on_event("startup")` (`Game/server/app/main.py:52`), pytest emits DeprecationWarning.

Recommendation:
- Switch to lifespan handlers later (not functionally blocking).

### 10) CI/workflow placement likely won’t run depending on repo root (Engineering hygiene)

Current state:
- Workflow is at `Game/.github/workflows/ci.yml`.
- If the git repository root is `/workspace` (current `git status` shows `?? Game/`), GitHub Actions will not pick up workflows under `Game/.github/workflows`.
- The workflow also assumes `Game/` is repo root (`python tools/validate_content.py`, `working-directory: web`), which will be wrong if `/workspace` is root.

Recommendation:
- If repo root is `/workspace`: move workflow to `/workspace/.github/workflows/` and update paths to `Game/tools/...` and `Game/web/...`.
- If repo root will be `Game/`: make `Game/` its own repository or adjust layout accordingly.

## Pass Items (Matches Frozen Spec)

- Deterministic RNG: `Game/engine/rng.py` (SHA-256 domain seed + SplitMix64)
- Deterministic weekly 3-of-6 presentation with server persistence (anti-tamper): `Game/engine/core.py:66-80`, `Game/server/app/service.py:139-157`
- `±n` implemented as integer binomial (center-biased): `Game/engine/core.py:269-279`
- Clamp to `[0, 100]` after each application: `Game/engine/core.py:285-294` (reads `rules.json`)
- Redline collapse check (`<= redline`): `Game/engine/core.py:295-300`
- Warning threshold `redline + 5`: `Game/engine/core.py:302-306` (reads `warning_offset=5`)
- Finals win-rate model + cap and deterministic `roll_int`: `Game/engine/core.py:174-184` (reads `rules.json` final_win config)
- Scoring factor + deterministic microtweak + half-up rounding: `Game/engine/scoring.py:11-69`
- Report generation matches `docs/report-mapping.md`: `Game/engine/report.py` (strengths/weakness/risk/turning_point/teammate_line, etc.)

## Suggested Fix Order (Directly actionable)

1. Remove internal mechanics/numeric state from `final_outcome` and `finals` public payloads (Issues 1 and 2).
2. Enforce non-default `SECRET_KEY` for production startup (Issue 3).
3. Decide and enforce migration strategy: disable `create_all()` in production, use Alembic (Issue 4).
4. Add auth UI or explicitly de-scope account support for Stage 1 (Issue 6).
5. Localize all user-visible errors to Chinese (Issue 7).
