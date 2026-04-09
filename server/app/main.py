from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from server.app.db import Base, engine, get_db
from server.app.config import settings
from server.app.models import User
from server.app.schemas import (
    AllocateRequest,
    ArchiveResponse,
    ChooseRequest,
    CreateRunResponse,
    FinalRequest,
    HistoryPageResponse,
    LeaderboardResponse,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    RunsListResponse,
    RunListItem,
    ShareInviteResponse,
    ShareRedeemResponse,
    UserProfileRequest,
    UserProfileResponse,
)
from server.app.security import hash_password, verify_password
from server.app.service import (
    clear_session_cookie,
    create_run,
    ensure_guest,
    finish_run,
    build_archive_payload,
    build_history_page_payload,
    build_leaderboard_payload,
    create_share_invite,
    get_active_guest_run,
    get_run_for_actor,
    get_session_payload,
    get_play_quota_payload,
    list_runs_for_user,
    load_user_by_username,
    load_user_profile,
    public_run_payload,
    redeem_share_invite,
    require_actor,
    resolve_actor,
    resolve_final,
    set_session_cookie,
    allocate_run,
    choose_option,
    ack_personality_reveal,
    update_user_profile,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.is_production and settings.secret_key == "change-me-in-production":
        raise RuntimeError("生产环境必须配置 SECRET_KEY，禁止使用默认值。")
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="JianChuCheng API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/guest/init", response_model=MessageResponse)
def guest_init(request: Request, response: Response, db: Session = Depends(get_db)) -> MessageResponse:
    guest = ensure_guest(db, request, response)
    db.commit()
    return MessageResponse(message=f"游客会话已准备：{guest.id}")


@app.post("/api/auth/register", response_model=MessageResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> MessageResponse:
    existing = load_user_by_username(db, payload.username)
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(username=payload.username, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    return MessageResponse(message="注册成功")


@app.post("/api/auth/login", response_model=MessageResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> MessageResponse:
    user = load_user_by_username(db, payload.username)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    session_payload = get_session_payload(request)
    session_payload["user_id"] = user.id
    set_session_cookie(response, session_payload)
    db.commit()
    return MessageResponse(message="登录成功")


@app.get("/api/profile", response_model=UserProfileResponse)
def get_profile(request: Request, db: Session = Depends(get_db)) -> UserProfileResponse:
    actor = require_actor(request)
    if not actor.is_user:
        raise HTTPException(status_code=400, detail="仅登录用户可查看资料")
    user = load_user_profile(db, actor.user_id)
    return UserProfileResponse(
        username=user.username,
        display_name=user.display_name,
        phone_number=user.phone_number,
        external_user_id=user.external_user_id,
    )


@app.post("/api/profile", response_model=UserProfileResponse)
def save_profile(payload: UserProfileRequest, request: Request, db: Session = Depends(get_db)) -> UserProfileResponse:
    actor = require_actor(request)
    user = update_user_profile(
        db,
        actor,
        display_name=payload.display_name,
        phone_number=payload.phone_number,
        external_user_id=payload.external_user_id,
    )
    db.commit()
    return UserProfileResponse(
        username=user.username,
        display_name=user.display_name,
        phone_number=user.phone_number,
        external_user_id=user.external_user_id,
    )


@app.post("/api/auth/logout", response_model=MessageResponse)
def logout(response: Response) -> MessageResponse:
    clear_session_cookie(response)
    return MessageResponse(message="已退出登录")


@app.post("/api/runs", response_model=CreateRunResponse)
def create_new_run(request: Request, db: Session = Depends(get_db)) -> CreateRunResponse:
    actor = require_actor(request)
    run = create_run(db, actor)
    db.commit()
    return CreateRunResponse(run_id=run.id, status=run.status, week=run.week)


@app.post("/api/runs/{run_id}/allocate")
def allocate(run_id: str, payload: AllocateRequest, request: Request, db: Session = Depends(get_db)):
    actor = require_actor(request)
    run = get_run_for_actor(db, actor, run_id)
    response = allocate_run(db, run, payload.attributes)
    db.commit()
    return response


@app.get("/api/runs/active")
def get_active_run(request: Request, db: Session = Depends(get_db)):
    actor = resolve_actor(request)
    if not actor.is_guest:
        raise HTTPException(status_code=400, detail="该接口仅适用于游客续玩")

    run = get_active_guest_run(db, actor.guest_id)
    if run is None:
        return {"run": None}
    return public_run_payload(db, run)


@app.get("/api/runs", response_model=RunsListResponse)
def list_runs(request: Request, db: Session = Depends(get_db)) -> RunsListResponse:
    actor = resolve_actor(request)
    if not actor.is_user:
        raise HTTPException(status_code=400, detail="该接口仅适用于登录用户")

    runs = list_runs_for_user(db, actor.user_id)
    return RunsListResponse(
        runs=[
            RunListItem(
                run_id=run.id,
                status=run.status,
                week=run.week,
                created_at=run.created_at.isoformat(),
                updated_at=run.updated_at.isoformat() if run.updated_at else run.created_at.isoformat(),
            )
            for run in runs
        ]
    )


@app.get("/api/archive", response_model=ArchiveResponse)
def get_archive(request: Request, db: Session = Depends(get_db)) -> ArchiveResponse:
    actor = require_actor(request)
    return ArchiveResponse(**build_archive_payload(db, actor))


@app.get("/api/archive/history", response_model=HistoryPageResponse)
def get_archive_history(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
) -> HistoryPageResponse:
    actor = require_actor(request)
    return HistoryPageResponse(**build_history_page_payload(db, actor, page, page_size))


@app.get("/api/play-quota")
def get_play_quota(request: Request, db: Session = Depends(get_db)):
    actor = require_actor(request)
    return get_play_quota_payload(db, actor)


@app.post("/api/share/invites", response_model=ShareInviteResponse)
def create_share(request: Request, db: Session = Depends(get_db), run_id: str | None = Query(default=None)) -> ShareInviteResponse:
    actor = require_actor(request)
    payload = create_share_invite(db, actor, source_run_id=run_id)
    db.commit()
    return ShareInviteResponse(**payload)


@app.post("/api/share/invites/{invite_token}/redeem", response_model=ShareRedeemResponse)
def redeem_share(invite_token: str, request: Request, db: Session = Depends(get_db)) -> ShareRedeemResponse:
    actor = require_actor(request)
    payload = redeem_share_invite(db, actor, invite_token)
    db.commit()
    return ShareRedeemResponse(**payload)


@app.get("/api/leaderboards/{board}", response_model=LeaderboardResponse)
def get_leaderboard(board: str, request: Request, db: Session = Depends(get_db), page: int = Query(default=1, ge=1)) -> LeaderboardResponse:
    actor = require_actor(request)
    payload = build_leaderboard_payload(db, board, page, actor)
    return LeaderboardResponse(**payload)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, request: Request, db: Session = Depends(get_db)):
    actor = require_actor(request)
    run = get_run_for_actor(db, actor, run_id)
    db.commit()
    return public_run_payload(db, run)


@app.post("/api/runs/{run_id}/choose")
def choose(run_id: str, payload: ChooseRequest, request: Request, db: Session = Depends(get_db)):
    actor = require_actor(request)
    run = get_run_for_actor(db, actor, run_id)
    response = choose_option(db, run, payload.option_id)
    db.commit()
    return response


@app.post("/api/runs/{run_id}/personality/ack")
def personality_ack(run_id: str, request: Request, db: Session = Depends(get_db)):
    actor = require_actor(request)
    run = get_run_for_actor(db, actor, run_id)
    response = ack_personality_reveal(db, run)
    db.commit()
    return response


@app.post("/api/runs/{run_id}/final")
def final(run_id: str, payload: FinalRequest, request: Request, db: Session = Depends(get_db)):
    actor = require_actor(request)
    run = get_run_for_actor(db, actor, run_id)
    response = resolve_final(db, run, payload.tactic_id)
    db.commit()
    return response


@app.post("/api/runs/{run_id}/finish")
def finish(run_id: str, request: Request, db: Session = Depends(get_db)):
    actor = require_actor(request)
    run = get_run_for_actor(db, actor, run_id)
    response = finish_run(db, run)
    db.commit()
    return response
