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


class UserProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    phone_number: str | None = Field(default=None, max_length=32)
    external_user_id: str | None = Field(default=None, max_length=128)


class UserProfileResponse(BaseModel):
    username: str
    display_name: str | None
    phone_number: str | None
    external_user_id: str | None


class PersonalityMeta(BaseModel):
    id: str | None = None
    name_cn: str | None = None
    copy_cn: dict[str, Any] | None = None


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
    score: int | None = None
    grade_label: str | None = None
    final_result: str | None = None


class RunsListResponse(BaseModel):
    runs: list[RunListItem]


class HistoryRecord(BaseModel):
    run_id: str
    status: str
    week: int
    played_at: str
    score: int | None = None
    grade_label: str | None = None
    final_result: str | None = None
    attributes_end: dict[str, int] | None = None
    personality_start_meta: PersonalityMeta | None = None
    personality_end_meta: PersonalityMeta | None = None
    collapse_ending_name_cn: str | None = None


class AchievementRecord(BaseModel):
    achievement_id: str
    name_cn: str
    desc_cn: str
    run_id: str
    status: str
    week: int
    earned_at: str


class AchievementCatalogItem(BaseModel):
    achievement_id: str
    name_cn: str
    desc_cn: str
    unlocked: bool


class PlayQuotaResponse(BaseModel):
    remaining_today: int
    base_limit: int
    base_used: int
    bonus_limit: int
    bonus_earned: int
    total_limit: int
    can_start_game: bool


class ArchiveResponse(BaseModel):
    runs: list[RunListItem]
    history_records: list[HistoryRecord]
    achievement_records: list[AchievementRecord]
    achievement_catalog: list[AchievementCatalogItem]
    play_quota: PlayQuotaResponse


class HistoryPageResponse(BaseModel):
    items: list[HistoryRecord]
    page: int
    page_size: int
    total: int
    total_pages: int


class ShareInviteResponse(BaseModel):
    invite_token: str
    share_url: str
    page_path: str
    qr_data_url: str
    bonus_limit: int


class ShareRedeemResponse(BaseModel):
    ok: bool = True
    granted_bonus: bool
    message: str
    play_quota: PlayQuotaResponse


class LeaderboardEntry(BaseModel):
    rank: int
    display_name_masked: str
    score: int
    run_id: str | None = None
    achieved_at: str | None = None


class LeaderboardResponse(BaseModel):
    board: str
    page: int
    page_size: int
    total_entries: int
    period_start: str | None = None
    period_end: str | None = None
    entries: list[LeaderboardEntry]
    self_entry: LeaderboardEntry | None = None
