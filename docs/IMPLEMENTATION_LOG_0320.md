# 0320 Implementation Log

This document records the code and content changes implemented against `《剑之初程：淬炼之路》需求更新至0320.docx`.

Last updated: 2026-03-22 (UTC)

## Scope

The implementation in this round covered:

- content wording updates required by the 0320 requirement doc
- history, achievement, and personality data exposure requested by design
- daily play limits and share-based bonus plays
- share QR generation and redeem flow
- leaderboard APIs and frontend views
- profile fields needed for display and ranking

## Content Changes

Updated files:

- `content/v3.3.0/weeks.json`
- `content/v3.3.0/finals.json`
- `content/v3.3.0/report_reference.json`
- `content/v3.3.0/report_templates.json`
- `content/v3.3.0/endings.json`
- `engine/report.py`

Implemented content updates:

- week option wording synced to the latest doc wording
- post-choice micro-story copy synced for updated options
- finals tactic labels updated to the latest phrasing
- report turning-point wording changed from `第X周` to `阶段X`
- story references updated from `林薇` to `林毅` where required by the requirement doc

## Backend and Data Changes

Updated files:

- `server/app/config.py`
- `server/app/models.py`
- `server/app/schemas.py`
- `server/app/service.py`
- `server/app/main.py`
- `server/alembic/versions/20260322_0001_share_limits_leaderboard.py`

### New data structures

- `User` now stores `display_name`, `phone_number`, and `external_user_id`
- `DailyPlayQuota` tracks daily base plays, used plays, and share bonus plays
- `ShareInvite` stores generated share tokens and source run references
- `ShareRedeem` stores successful share redemption records to prevent duplicate grants

### New API surfaces

- `GET /api/profile`
- `POST /api/profile`
- `GET /api/play-quota`
- `POST /api/share/invites`
- `POST /api/share/invites/{invite_token}/redeem`
- `GET /api/leaderboards/{board}`

### Expanded API payloads

- `GET /api/archive` now returns:
  - `runs`
  - `history_records`
  - `achievement_records`
  - `achievement_catalog`
  - `play_quota`
- week choice results now include `result_segments` for frontend segmented rendering
- collapse and report payloads include starting and ending personality metadata

### Backend behavior changes

- creating a run now consumes daily play quota
- daily base quota defaults to 2 plays
- share bonus quota is capped per day
- history records are ordered by most recent play time
- leaderboard entries use masked display identity
- share QR payload is generated server-side as a data URL

## Frontend Changes

Updated files:

- `web/src/App.tsx`
- `web/src/api.ts`
- `web/src/types.ts`

Implemented UI changes:

- app bootstrap now shows a local start screen instead of auto-consuming a play
- header shows stage terminology and remaining daily play count
- logged-in users can edit profile fields needed for ranking and display
- archive screen now shows:
  - historical reports
  - in-progress journeys
  - achievement catalog
  - recent achievement unlocks
  - leaderboard tabs and pagination
- failure and report screens show initial and final personality data
- report screen can generate and display share QR code
- share token in URL is redeemed on app load
- option result copy renders as segmented lines instead of one large paragraph

## Verification

The following checks were run after implementation:

```bash
pytest -q
python tools/validate_content.py
cd web && npm run build
```

Current result:

- tests passed
- content validation passed
- web production build passed

## Follow-up Notes

- Vite build currently emits a chunk-size warning for the main bundle. This is not blocking, but code splitting may be worth doing later.
- `game.db` and `web/dist/` changed during local verification. Those are generated/runtime artifacts, not the source-of-truth implementation.
- If the requirement doc is revised again, re-run a targeted audit on wording-sensitive content files before touching gameplay logic.
