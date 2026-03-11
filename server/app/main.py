from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from server.app.db import Base, engine, get_db
from server.app.config import settings
from server.app.models import User
from server.app.schemas import (
    AllocateRequest,
    ChooseRequest,
    CreateRunResponse,
    FinalRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    RunsListResponse,
    RunListItem,
)
from server.app.security import hash_password, verify_password
from server.app.service import (
    clear_session_cookie,
    create_run,
    ensure_guest,
    finish_run,
    get_active_guest_run,
    get_run_for_actor,
    get_session_payload,
    list_runs_for_user,
    load_user_by_username,
    public_run_payload,
    require_actor,
    resolve_actor,
    resolve_final,
    set_session_cookie,
    allocate_run,
    choose_option,
    ack_personality_reveal,
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
