from __future__ import annotations

import base64
import io
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from secrets import randbits, token_urlsafe
from typing import Any
from zoneinfo import ZoneInfo

import qrcode
from fastapi import HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from engine import GameEngine
from engine.content import collapse_ending_by_id, option_by_id, personality_by_id
from engine.models import RunState
from server.app.config import settings
from server.app.models import DailyPlayQuota, Guest, Run, RunWeekLog, ShareInvite, ShareRedeem, User
from server.app.presentation import (
    build_allocation_screen,
    build_collapse_screen,
    build_final_outcome_screen,
    build_finals_screen,
    build_personality_reveal_screen,
    build_report_screen,
    build_week_screen,
)
from server.app.security import decode_session, encode_session
from server.app.state_codec import apply_engine_state_to_run, run_to_engine_state


engine = GameEngine()
content = engine.content
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class Actor:
    def __init__(self, user_id: int | None, guest_id: str | None):
        self.user_id = user_id
        self.guest_id = guest_id

    @property
    def actor_type(self) -> str:
        if self.is_user:
            return "user"
        if self.is_guest:
            return "guest"
        return "anonymous"

    @property
    def actor_key(self) -> str:
        if self.is_user:
            return str(self.user_id)
        if self.is_guest:
            return str(self.guest_id)
        return ""

    @property
    def is_user(self) -> bool:
        return self.user_id is not None

    @property
    def is_guest(self) -> bool:
        return self.user_id is None and self.guest_id is not None


def get_session_payload(request: Request) -> dict[str, Any]:
    token = request.cookies.get(settings.session_cookie)
    if not token:
        return {}
    payload = decode_session(token)
    return payload or {}


def set_session_cookie(response: Response, payload: dict[str, Any]) -> None:
    cookie_kwargs: dict[str, Any] = {}
    if settings.cookie_domain:
        cookie_kwargs["domain"] = settings.cookie_domain

    response.set_cookie(
        key=settings.session_cookie,
        value=encode_session(payload),
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.session_max_age_seconds,
        **cookie_kwargs,
    )


def clear_session_cookie(response: Response) -> None:
    cookie_kwargs: dict[str, Any] = {}
    if settings.cookie_domain:
        cookie_kwargs["domain"] = settings.cookie_domain
    response.delete_cookie(settings.session_cookie, samesite=settings.cookie_samesite, **cookie_kwargs)


def resolve_actor(request: Request) -> Actor:
    payload = get_session_payload(request)
    user_id = payload.get("user_id")
    guest_id = payload.get("guest_id")
    return Actor(user_id=int(user_id) if user_id is not None else None, guest_id=guest_id)


def require_actor(request: Request) -> Actor:
    actor = resolve_actor(request)
    if not actor.is_user and not actor.is_guest:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未找到有效会话，请先初始化游客或登录")
    return actor


def ensure_guest(db: Session, request: Request, response: Response) -> Guest:
    payload = get_session_payload(request)
    guest_id = payload.get("guest_id")

    guest = None
    if guest_id:
        guest = db.get(Guest, guest_id)

    if guest is None:
        guest = Guest()
        db.add(guest)
        db.flush()

    payload["guest_id"] = guest.id
    set_session_cookie(response, payload)
    return guest


def load_user_by_username(db: Session, username: str) -> User | None:
    stmt = select(User).where(User.username == username)
    return db.execute(stmt).scalar_one_or_none()


def load_user_profile(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="未找到对应用户")
    return user


def update_user_profile(
    db: Session,
    actor: Actor,
    *,
    display_name: str | None,
    phone_number: str | None,
    external_user_id: str | None,
) -> User:
    if not actor.is_user:
        raise HTTPException(status_code=400, detail="仅登录用户可更新资料")

    user = load_user_profile(db, actor.user_id)
    if external_user_id:
        stmt = select(User).where(User.external_user_id == external_user_id, User.id != user.id)
        existing = db.execute(stmt).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=400, detail="该外部用户标识已被绑定")

    user.display_name = display_name.strip() if display_name else None
    user.phone_number = phone_number.strip() if phone_number else None
    user.external_user_id = external_user_id.strip() if external_user_id else None
    db.add(user)
    db.flush()
    return user


def _fetch_run_week_logs(db: Session, run_id: str) -> list[RunWeekLog]:
    stmt = select(RunWeekLog).where(RunWeekLog.run_id == run_id)
    return list(db.execute(stmt).scalars().all())


def _today_utc() -> date:
    return datetime.now(UTC).date()


def _now_shanghai() -> datetime:
    return datetime.now(SHANGHAI_TZ)


def _week_bounds_shanghai(now: datetime) -> tuple[datetime, datetime]:
    local_now = now.astimezone(SHANGHAI_TZ)
    days_since_friday = (local_now.weekday() - 4) % 7
    start_date = local_now.date() - timedelta(days=days_since_friday)
    start = datetime.combine(start_date, datetime.min.time(), tzinfo=SHANGHAI_TZ)
    return start, start + timedelta(days=7)


def _mask_name(display_name: str | None) -> str:
    if not display_name:
        return "匿名玩家"
    if len(display_name) <= 1:
        return f"{display_name}**"
    return f"{display_name[0]}**"


def _mask_phone(phone_number: str | None) -> str:
    digits = "".join(ch for ch in (phone_number or "") if ch.isdigit())
    if len(digits) >= 7:
        return f"{digits[:3]}****{digits[-4:]}"
    if digits:
        return digits[:3] + "****"
    return ""


def _masked_identity(user: User) -> str:
    masked_name = _mask_name(user.display_name or user.username)
    masked_phone = _mask_phone(user.phone_number)
    return f"{masked_name}{masked_phone}" if masked_phone else masked_name


def _split_result_segments(text: str) -> list[str]:
    segments: list[str] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        parts: list[str] = []
        current = ""
        for ch in block:
            current += ch
            if ch in "，。！？；：":
                parts.append(current.strip())
                current = ""
        if current.strip():
            parts.append(current.strip())
        segments.extend(part for part in parts if part)
    return segments or [text]


def _get_or_create_daily_quota(db: Session, actor: Actor, quota_date: date | None = None) -> DailyPlayQuota:
    day = quota_date or _today_utc()
    stmt = select(DailyPlayQuota).where(
        DailyPlayQuota.actor_type == actor.actor_type,
        DailyPlayQuota.actor_key == actor.actor_key,
        DailyPlayQuota.quota_date == day,
    )
    quota = db.execute(stmt).scalar_one_or_none()
    if quota is not None:
        return quota

    quota = DailyPlayQuota(
        actor_type=actor.actor_type,
        actor_key=actor.actor_key,
        quota_date=day,
        used_runs=0,
        bonus_runs=0,
    )
    db.add(quota)
    db.flush()
    return quota


def _build_play_quota_payload(quota: DailyPlayQuota) -> dict[str, Any]:
    bonus_earned = min(quota.bonus_runs, settings.daily_share_bonus_limit)
    total_limit = settings.daily_play_base_limit + bonus_earned
    remaining_today = max(total_limit - quota.used_runs, 0)
    return {
        "remaining_today": remaining_today,
        "base_limit": settings.daily_play_base_limit,
        "base_used": quota.used_runs,
        "bonus_limit": settings.daily_share_bonus_limit,
        "bonus_earned": bonus_earned,
        "total_limit": total_limit,
        "can_start_game": remaining_today > 0,
    }


def _consume_play_attempt_or_raise(db: Session, actor: Actor) -> dict[str, Any]:
    quota = _get_or_create_daily_quota(db, actor)
    payload = _build_play_quota_payload(quota)
    if payload["remaining_today"] <= 0:
        raise HTTPException(status_code=429, detail="今日游玩次数已用尽，可通过分享获得额外次数。")
    quota.used_runs += 1
    db.add(quota)
    db.flush()
    return _build_play_quota_payload(quota)


def _personality_meta(personality_id: str | None) -> dict[str, Any] | None:
    if not personality_id:
        return None
    personality = personality_by_id(content, personality_id)
    return {
        "id": personality.get("id"),
        "name_cn": personality.get("name_cn"),
        "copy_cn": personality.get("copy_cn"),
    }


def _history_record_from_run(run: Run) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "status": run.status,
        "week": run.week,
        "played_at": (run.updated_at or run.created_at).isoformat(),
        "score": run.score,
        "grade_label": run.grade_label,
        "final_result": run.final_result,
        "attributes_end": run.attributes,
        "personality_start_meta": _personality_meta(run.personality_start),
        "personality_end_meta": _personality_meta(run.personality_end),
        "collapse_ending_name_cn": collapse_ending_by_id(content, run.collapse_ending_id)["name_cn"]
        if run.collapse_ending_id
        else None,
    }


def _grant_share_bonus(db: Session, actor_type: str, actor_key: str) -> bool:
    actor = Actor(user_id=int(actor_key) if actor_type == "user" else None, guest_id=actor_key if actor_type == "guest" else None)
    quota = _get_or_create_daily_quota(db, actor)
    if quota.bonus_runs >= settings.daily_share_bonus_limit:
        return False
    quota.bonus_runs += 1
    db.add(quota)
    db.flush()
    return True


def get_play_quota_payload(db: Session, actor: Actor) -> dict[str, Any]:
    quota = _get_or_create_daily_quota(db, actor)
    return _build_play_quota_payload(quota)


def _run_to_public(db: Session, run: Run) -> dict[str, Any]:
    week_logs = _fetch_run_week_logs(db, run.id)
    state = run_to_engine_state(run, week_logs)

    if state.status == "collapsed":
        if state.report is not None:
            return build_report_screen(content, run.id, state)
        return build_collapse_screen(content, run.id, state)

    if state.week == 0:
        return build_allocation_screen(content, run.id, state)

    if state.status == "finished":
        if state.report is not None:
            return build_report_screen(content, run.id, state)
        return build_final_outcome_screen(content, run.id, state)

    if 1 <= state.week <= 11:
        if not run.personality_reveal_ack and len(state.history) == 0:
            return build_personality_reveal_screen(content, run.id, state)
        week_log = _ensure_presented_week_log(db, run, state)
        state = replace(state, presented_options=list(week_log.presented_option_ids))
        return build_week_screen(content, run.id, state, list(week_log.presented_option_ids))

    if state.week == 12:
        return build_finals_screen(content, run.id, state)

    raise HTTPException(status_code=500, detail="当前进度状态异常，请刷新重试")


def _ensure_presented_week_log(db: Session, run: Run, state: RunState) -> RunWeekLog:
    stmt = select(RunWeekLog).where(
        RunWeekLog.run_id == run.id,
        RunWeekLog.week_number == state.week,
    )
    log = db.execute(stmt).scalar_one_or_none()
    if log is not None:
        return log

    presented = engine.present_week(run.seed, state.week)
    log = RunWeekLog(
        run_id=run.id,
        week_number=state.week,
        week_id=f"week_{state.week:02d}",
        presented_option_ids=presented,
    )
    db.add(log)
    db.flush()
    return log


def _assert_run_access(actor: Actor, run: Run) -> None:
    if actor.is_user and run.user_id == actor.user_id:
        return
    if actor.is_guest and run.guest_id == actor.guest_id:
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到对应旅程")


def get_run_for_actor(db: Session, actor: Actor, run_id: str) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到对应旅程")
    _assert_run_access(actor, run)
    return run


def create_run(db: Session, actor: Actor) -> Run:
    if actor.is_user:
        owner_type = "user"
        user_id = actor.user_id
        guest_id = None
    elif actor.is_guest:
        owner_type = "guest"
        user_id = None
        guest_id = actor.guest_id
    else:
        raise HTTPException(status_code=401, detail="未找到有效会话，请先初始化游客或登录")

    _consume_play_attempt_or_raise(db, actor)

    if owner_type == "guest":
        db.execute(
            update(Run)
            .where(Run.guest_id == guest_id, Run.is_active_guest_run.is_(True))
            .values(is_active_guest_run=False)
        )

    attrs_zero = {a: 0 for a in engine.content.rules["attributes"]}
    run = Run(
        seed=randbits(63),
        ruleset_version=settings.ruleset_version,
        status="in_progress",
        week=0,
        owner_type=owner_type,
        user_id=user_id,
        guest_id=guest_id,
        is_active_guest_run=(owner_type == "guest"),
        personality_reveal_ack=True,
        attributes=attrs_zero,
        min_attributes=attrs_zero,
        warning_attrs=[],
    )
    db.add(run)
    db.flush()
    return run


def allocate_run(db: Session, run: Run, attributes: dict[str, int]) -> dict[str, Any]:
    logs = _fetch_run_week_logs(db, run.id)
    state = run_to_engine_state(run, logs)
    state = engine.allocate(state, attributes)

    run = apply_engine_state_to_run(run, state)

    week_log = _ensure_presented_week_log(db, run, state)
    week_log.presented_option_ids = list(state.presented_options)

    # Personality reveal is a required, resumable step right after allocation.
    run.personality_reveal_ack = False

    db.add(run)
    db.flush()

    return build_personality_reveal_screen(content, run.id, state)


def ack_personality_reveal(db: Session, run: Run) -> dict[str, Any]:
    run.personality_reveal_ack = True
    db.add(run)
    db.flush()
    return public_run_payload(db, run)


def choose_option(db: Session, run: Run, option_id: str) -> dict[str, Any]:
    logs = _fetch_run_week_logs(db, run.id)
    state = run_to_engine_state(run, logs)
    if not run.personality_reveal_ack and state.week == 1 and len(state.history) == 0:
        raise HTTPException(status_code=400, detail="请先确认人格觉醒，再进行第一周选择。")
    if state.status != "in_progress" or state.week < 1 or state.week > 11:
        raise HTTPException(status_code=400, detail="当前不在周事件选择阶段")

    current_log = _ensure_presented_week_log(db, run, state)
    presented = list(current_log.presented_option_ids)
    if option_id not in presented:
        raise HTTPException(status_code=400, detail="该选项并非本周展示选项")

    state = replace(state, presented_options=presented)
    next_state = engine.apply_choice(state, option_id, presented_option_ids=presented)

    chosen = option_by_id(content, state.week, option_id)
    current_log.chosen_option_id = option_id
    current_log.resolved_rolls = dict(next_state.history[-1].resolved_rolls)
    current_log.applied_deltas = dict(next_state.history[-1].applied_deltas)
    current_log.result_cn = chosen["result_cn"]

    if next_state.status == "in_progress" and 1 <= next_state.week <= 11:
        next_log_stmt = select(RunWeekLog).where(
            RunWeekLog.run_id == run.id,
            RunWeekLog.week_number == next_state.week,
        )
        existing = db.execute(next_log_stmt).scalar_one_or_none()
        if existing is None:
            db.add(
                RunWeekLog(
                    run_id=run.id,
                    week_number=next_state.week,
                    week_id=f"week_{next_state.week:02d}",
                    presented_option_ids=list(next_state.presented_options),
                )
            )

    run = apply_engine_state_to_run(run, next_state)
    db.add(run)
    db.flush()

    if next_state.status == "collapsed":
        payload = build_collapse_screen(content, run.id, next_state)
    elif next_state.week == 12:
        payload = build_finals_screen(content, run.id, next_state)
    else:
        payload = build_week_screen(content, run.id, next_state, list(next_state.presented_options))

    payload["result_cn"] = chosen["result_cn"]
    payload["result_segments"] = _split_result_segments(chosen["result_cn"])
    payload["warning_attrs"] = list(next_state.warning_attrs)
    payload["chosen_option_id"] = option_id
    return payload


def resolve_final(db: Session, run: Run, tactic_id: str) -> dict[str, Any]:
    logs = _fetch_run_week_logs(db, run.id)
    state = run_to_engine_state(run, logs)
    if state.status != "in_progress" or state.week != 12:
        raise HTTPException(status_code=400, detail="当前不在决赛阶段")

    next_state = engine.resolve_final(state, tactic_id)
    final_state = engine.finalize(next_state)
    run = apply_engine_state_to_run(run, final_state)

    db.add(run)
    db.flush()

    payload = build_final_outcome_screen(content, run.id, final_state)
    payload["report_payload"] = build_report_screen(content, run.id, final_state)
    return payload


def finish_run(db: Session, run: Run) -> dict[str, Any]:
    logs = _fetch_run_week_logs(db, run.id)
    state = run_to_engine_state(run, logs)

    if state.report is not None and state.score is not None:
        return build_report_screen(content, run.id, state)

    if state.status not in {"finished", "collapsed"}:
        raise HTTPException(status_code=400, detail="当前状态尚不可生成报告")

    final_state = engine.finalize(state)
    run = apply_engine_state_to_run(run, final_state)
    db.add(run)
    db.flush()
    return build_report_screen(content, run.id, final_state)


def list_runs_for_actor(db: Session, actor: Actor) -> list[Run]:
    stmt = select(Run)
    if actor.is_user:
        stmt = stmt.where(Run.user_id == actor.user_id)
    elif actor.is_guest:
        stmt = stmt.where(Run.guest_id == actor.guest_id)
    else:
        raise HTTPException(status_code=401, detail="未找到有效会话，请先初始化游客或登录")

    stmt = stmt.order_by(Run.updated_at.desc(), Run.created_at.desc())
    return list(db.execute(stmt).scalars().all())


def list_runs_for_user(db: Session, user_id: int) -> list[Run]:
    return list_runs_for_actor(db, Actor(user_id=user_id, guest_id=None))


def build_archive_payload(db: Session, actor: Actor) -> dict[str, Any]:
    runs = list_runs_for_actor(db, actor)
    achievement_meta = {}
    for group in ("core", "special", "legend"):
        for item in content.achievements[group]:
            achievement_meta[item["id"]] = item

    achievement_records: list[dict[str, Any]] = []
    for run in runs:
        earned_at = run.updated_at or run.created_at
        for achievement_id in run.achievements or []:
            meta = achievement_meta.get(achievement_id)
            if meta is None:
                continue
            achievement_records.append(
                {
                    "achievement_id": achievement_id,
                    "name_cn": meta["name_cn"],
                    "desc_cn": meta["desc_cn"],
                    "run_id": run.id,
                    "status": run.status,
                    "week": run.week,
                    "earned_at": earned_at.isoformat(),
                }
            )

    achievement_records.sort(key=lambda item: item["earned_at"], reverse=True)

    unlocked_ids = {item["achievement_id"] for item in achievement_records}
    achievement_catalog: list[dict[str, Any]] = []
    for group in ("core", "special", "legend"):
        for item in content.achievements[group]:
            achievement_catalog.append(
                {
                    "achievement_id": item["id"],
                    "name_cn": item["name_cn"],
                    "desc_cn": item["desc_cn"],
                    "unlocked": item["id"] in unlocked_ids,
                }
            )

    history_records = [_history_record_from_run(run) for run in runs if run.report is not None]

    return {
        "runs": [
            {
                "run_id": run.id,
                "status": run.status,
                "week": run.week,
                "created_at": run.created_at.isoformat(),
                "updated_at": (run.updated_at or run.created_at).isoformat(),
                "score": run.score,
                "grade_label": run.grade_label,
                "final_result": run.final_result,
            }
            for run in runs
        ],
        "history_records": history_records,
        "achievement_records": achievement_records,
        "achievement_catalog": achievement_catalog,
        "play_quota": get_play_quota_payload(db, actor),
    }


def build_history_page_payload(db: Session, actor: Actor, page: int, page_size: int) -> dict[str, Any]:
    runs = [run for run in list_runs_for_actor(db, actor) if run.report is not None]
    total = len(runs)
    total_pages = max(1, (total + page_size - 1) // page_size)
    start_idx = max(page - 1, 0) * page_size
    end_idx = start_idx + page_size

    return {
        "items": [_history_record_from_run(run) for run in runs[start_idx:end_idx]],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def create_share_invite(db: Session, actor: Actor, source_run_id: str | None = None) -> dict[str, Any]:
    if source_run_id is not None:
        run = get_run_for_actor(db, actor, source_run_id)
        if run.report is None:
            raise HTTPException(status_code=400, detail="仅已生成报告的旅程可创建分享。")

    invite_token = token_urlsafe(24)
    invite = ShareInvite(
        invite_token=invite_token,
        actor_type=actor.actor_type,
        actor_key=actor.actor_key,
        source_run_id=source_run_id,
        page_path=settings.share_page_path,
        redeem_count=0,
    )
    db.add(invite)
    db.flush()

    share_url = f"{settings.public_web_base_url}/?share_token={invite.invite_token}"
    qr_image = qrcode.make(share_url)
    buffer = io.BytesIO()
    qr_image.save(buffer, format="PNG")
    qr_data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

    return {
        "invite_token": invite.invite_token,
        "share_url": share_url,
        "page_path": settings.share_page_path,
        "qr_data_url": qr_data_url,
        "bonus_limit": settings.daily_share_bonus_limit,
    }


def redeem_share_invite(db: Session, actor: Actor, invite_token: str) -> dict[str, Any]:
    stmt = select(ShareInvite).where(ShareInvite.invite_token == invite_token)
    invite = db.execute(stmt).scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="未找到对应分享二维码。")

    if invite.actor_type == actor.actor_type and invite.actor_key == actor.actor_key:
        return {
            "ok": True,
            "granted_bonus": False,
            "message": "不能通过自己的分享链接为自己增加次数。",
            "play_quota": get_play_quota_payload(db, actor),
        }

    existing_stmt = select(ShareRedeem).where(
        ShareRedeem.invite_id == invite.id,
        ShareRedeem.scanner_actor_type == actor.actor_type,
        ShareRedeem.scanner_actor_key == actor.actor_key,
    )
    existing = db.execute(existing_stmt).scalar_one_or_none()
    if existing is not None:
        return {
            "ok": True,
            "granted_bonus": bool(existing.granted_bonus),
            "message": "该分享链接今日已为你结算过。",
            "play_quota": get_play_quota_payload(db, actor),
        }

    granted_bonus = _grant_share_bonus(db, invite.actor_type, invite.actor_key)
    redeem = ShareRedeem(
        invite_id=invite.id,
        scanner_actor_type=actor.actor_type,
        scanner_actor_key=actor.actor_key,
        granted_bonus=granted_bonus,
    )
    db.add(redeem)
    invite.redeem_count += 1
    db.add(invite)
    db.flush()

    return {
        "ok": True,
        "granted_bonus": granted_bonus,
        "message": "分享加次已到账。" if granted_bonus else "对方今日通过分享可获得的额外次数已达上限。",
        "play_quota": get_play_quota_payload(db, actor),
    }


def _scoreboard_runs(
    db: Session,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[Run]:
    stmt = select(Run).where(Run.user_id.is_not(None), Run.score.is_not(None), Run.report.is_not(None))
    runs = list(db.execute(stmt).scalars().all())
    if start is None or end is None:
        return runs

    filtered: list[Run] = []
    for run in runs:
        achieved_at = (run.updated_at or run.created_at).astimezone(SHANGHAI_TZ)
        if start <= achieved_at < end:
            filtered.append(run)
    return filtered


def _build_score_leaderboard_entries(runs: list[Run], db: Session) -> list[dict[str, Any]]:
    best_by_user: dict[int, Run] = {}
    for run in runs:
        if run.user_id is None or run.score is None:
            continue
        current = best_by_user.get(run.user_id)
        if current is None or (run.score, run.updated_at or run.created_at, run.id) > (
            current.score or 0,
            current.updated_at or current.created_at,
            current.id,
        ):
            best_by_user[run.user_id] = run

    ordered = sorted(
        best_by_user.values(),
        key=lambda run: (run.score or 0, run.updated_at or run.created_at, run.id),
        reverse=True,
    )
    entries: list[dict[str, Any]] = []
    for rank, run in enumerate(ordered, start=1):
        user = db.get(User, run.user_id)
        if user is None:
            continue
        entries.append(
            {
                "rank": rank,
                "display_name_masked": _masked_identity(user),
                "score": int(run.score or 0),
                "run_id": run.id,
                "achieved_at": (run.updated_at or run.created_at).isoformat(),
                "user_id": run.user_id,
            }
        )
    return entries


def _build_achievement_leaderboard_entries(db: Session) -> list[dict[str, Any]]:
    runs = list(db.execute(select(Run).where(Run.user_id.is_not(None))).scalars().all())
    unlocked_by_user: dict[int, set[str]] = {}
    last_seen_by_user: dict[int, datetime] = {}
    for run in runs:
        if run.user_id is None:
            continue
        unlocked_by_user.setdefault(run.user_id, set()).update(run.achievements or [])
        last_seen_by_user[run.user_id] = max(last_seen_by_user.get(run.user_id, run.created_at), run.updated_at or run.created_at)

    ordered_user_ids = sorted(
        unlocked_by_user,
        key=lambda user_id: (len(unlocked_by_user[user_id]), last_seen_by_user.get(user_id), user_id),
        reverse=True,
    )

    entries: list[dict[str, Any]] = []
    for rank, user_id in enumerate(ordered_user_ids, start=1):
        user = db.get(User, user_id)
        if user is None:
            continue
        entries.append(
            {
                "rank": rank,
                "display_name_masked": _masked_identity(user),
                "score": len(unlocked_by_user[user_id]),
                "run_id": None,
                "achieved_at": last_seen_by_user[user_id].isoformat() if user_id in last_seen_by_user else None,
                "user_id": user_id,
            }
        )
    return entries


def build_leaderboard_payload(db: Session, board: str, page: int, actor: Actor) -> dict[str, Any]:
    board = board.lower()
    now = _now_shanghai()
    period_start: date | None = None
    period_end: date | None = None

    if board == "weekly":
        window_start, window_end = _week_bounds_shanghai(now)
        period_start = window_start.date()
        period_end = window_end.date()
        entries = _build_score_leaderboard_entries(_scoreboard_runs(db, start=window_start, end=window_end), db)
    elif board == "monthly":
        entries = _build_score_leaderboard_entries(_scoreboard_runs(db), db)
    elif board == "achievements":
        entries = _build_achievement_leaderboard_entries(db)
    else:
        raise HTTPException(status_code=404, detail="未找到对应排行榜。")

    page_size = 20
    total_entries = len(entries)
    start_idx = max(page - 1, 0) * page_size
    paged_entries = entries[start_idx : start_idx + page_size]

    self_entry = None
    if actor.is_user:
        self_entry = next((entry for entry in entries if entry["user_id"] == actor.user_id), None)

    for entry in entries:
        entry.pop("user_id", None)
    if self_entry is not None:
        self_entry = dict(self_entry)
        self_entry.pop("user_id", None)

    return {
        "board": board,
        "page": page,
        "page_size": page_size,
        "total_entries": total_entries,
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "entries": paged_entries,
        "self_entry": self_entry,
    }


def get_active_guest_run(db: Session, guest_id: str) -> Run | None:
    stmt = select(Run).where(Run.guest_id == guest_id, Run.is_active_guest_run.is_(True))
    return db.execute(stmt).scalar_one_or_none()


def public_run_payload(db: Session, run: Run) -> dict[str, Any]:
    return _run_to_public(db, run)
