from __future__ import annotations

from dataclasses import replace
from secrets import randbits
from typing import Any

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from engine import GameEngine
from engine.content import option_by_id, personality_by_id
from engine.models import RunState
from server.app.config import settings
from server.app.models import Guest, Run, RunWeekLog, User
from server.app.presentation import (
    build_allocation_screen,
    build_collapse_screen,
    build_final_outcome_screen,
    build_finals_screen,
    build_report_screen,
    build_week_screen,
)
from server.app.security import decode_session, encode_session
from server.app.state_codec import apply_engine_state_to_run, run_to_engine_state


engine = GameEngine()
content = engine.content


class Actor:
    def __init__(self, user_id: int | None, guest_id: str | None):
        self.user_id = user_id
        self.guest_id = guest_id

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


def _fetch_run_week_logs(db: Session, run_id: str) -> list[RunWeekLog]:
    stmt = select(RunWeekLog).where(RunWeekLog.run_id == run_id)
    return list(db.execute(stmt).scalars().all())


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

    db.add(run)
    db.flush()

    payload = build_week_screen(content, run.id, state, list(state.presented_options))

    # Personality reveal is an intro-only step right after allocation. We return it once
    # (client shows as a modal) without changing the run state machine.
    reveal = content.intro.get("personality_reveal", {})
    p = personality_by_id(content, state.personality_start or "white_paper")
    template = str(reveal.get("template_cn", ""))
    reveal_cn = template.replace("[人格名称]", str(p.get("name_cn", ""))).replace(
        "[人格描述]", str((p.get("copy_cn") or {}).get("long", ""))
    )

    payload["personality_reveal"] = {
        "title_cn": reveal.get("title_cn"),
        "cta_cn": reveal.get("cta_cn"),
        "reveal_cn": reveal_cn,
        "personality": {
            "id": p.get("id"),
            "name_cn": p.get("name_cn"),
            "copy_cn": p.get("copy_cn"),
        },
    }
    return payload


def choose_option(db: Session, run: Run, option_id: str) -> dict[str, Any]:
    logs = _fetch_run_week_logs(db, run.id)
    state = run_to_engine_state(run, logs)
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


def list_runs_for_user(db: Session, user_id: int) -> list[Run]:
    stmt = select(Run).where(Run.user_id == user_id).order_by(Run.created_at.desc())
    return list(db.execute(stmt).scalars().all())


def get_active_guest_run(db: Session, guest_id: str) -> Run | None:
    stmt = select(Run).where(Run.guest_id == guest_id, Run.is_active_guest_run.is_(True))
    return db.execute(stmt).scalar_one_or_none()


def public_run_payload(db: Session, run: Run) -> dict[str, Any]:
    return _run_to_public(db, run)
