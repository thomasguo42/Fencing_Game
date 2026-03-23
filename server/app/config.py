from __future__ import annotations

import os
from pathlib import Path


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _split_csv(value: str | None, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    out = [v.strip() for v in value.split(",") if v.strip()]
    return out or list(default)


class Settings:
    def __init__(self) -> None:
        self.app_name: str = "JianChuCheng API"
        self.ruleset_version: str = "v3.3.0"
        self.app_env: str = os.getenv("APP_ENV", "development").lower()
        self.project_root: Path = Path(__file__).resolve().parents[2]

        self.database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{(self.project_root / 'game.db').as_posix()}")
        self.secret_key: str = os.getenv("SECRET_KEY", "change-me-in-production")

        self.session_cookie: str = os.getenv("SESSION_COOKIE", "game_session")
        self.cookie_secure: bool = _as_bool(os.getenv("COOKIE_SECURE"), default=False)
        self.cookie_samesite: str = os.getenv("COOKIE_SAMESITE", "lax").lower()
        self.cookie_domain: str | None = os.getenv("COOKIE_DOMAIN")
        self.session_max_age_seconds: int = int(os.getenv("SESSION_MAX_AGE_SECONDS", str(60 * 60 * 24 * 30)))
        self.public_web_base_url: str = os.getenv("PUBLIC_WEB_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
        self.share_page_path: str = os.getenv("SHARE_PAGE_PATH", "/package_Game/pages/init/inti")
        self.daily_play_base_limit: int = int(os.getenv("DAILY_PLAY_BASE_LIMIT", "2"))
        self.daily_share_bonus_limit: int = int(os.getenv("DAILY_SHARE_BONUS_LIMIT", "3"))

        self.auto_create_tables: bool = _as_bool(
            os.getenv("AUTO_CREATE_TABLES"),
            default=False,
        )

        self.cors_origins: list[str] = _split_csv(
            os.getenv("CORS_ORIGINS"),
            [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:8080",
                "http://127.0.0.1:8080",
            ],
        )
        if "*" in self.cors_origins:
            raise ValueError("启用凭证跨域时，CORS_ORIGINS 不能包含 '*'。请显式配置域名列表。")

        if self.cookie_samesite not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE 必须是 lax/strict/none")

        # Browser rule: SameSite=None cookies must also be Secure.
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("当 COOKIE_SAMESITE=none 时，必须设置 COOKIE_SECURE=true")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()
