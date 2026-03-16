from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    ok: bool = True
    message: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateRunResponse(BaseModel):
    run_id: str
    status: str
    week: int


class AllocateRequest(BaseModel):
    attributes: dict[str, int]


class ChooseRequest(BaseModel):
    option_id: str


class FinalRequest(BaseModel):
    tactic_id: str


class PublicRunPayload(BaseModel):
    run_id: str
    status: str
    week: int
    screen: str
    payload: dict[str, Any]


class RunListItem(BaseModel):
    run_id: str
    status: str
    week: int
    created_at: str
    updated_at: str


class RunsListResponse(BaseModel):
    runs: list[RunListItem]


class AchievementRecord(BaseModel):
    achievement_id: str
    name_cn: str
    desc_cn: str
    run_id: str
    status: str
    week: int
    earned_at: str


class ArchiveResponse(BaseModel):
    runs: list[RunListItem]
    achievement_records: list[AchievementRecord]
