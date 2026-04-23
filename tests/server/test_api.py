from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select

from engine import GameEngine
from server.app.main import app
from server.app import service
from server.app.config import settings
from server.app.db import SessionLocal
from server.app.models import Run, User
from server.app.security import hash_password


def _allocation() -> dict[str, int]:
    return {
        "stamina": 42,
        "skill": 46,
        "mind": 40,
        "academics": 40,
        "social": 41,
        "finance": 41,
    }


def _collapse_allocation() -> dict[str, int]:
    return {
        "stamina": 25,
        "skill": 60,
        "mind": 60,
        "academics": 35,
        "social": 35,
        "finance": 35,
    }


def _safe_week_choices(seed: int) -> list[str]:
    engine = GameEngine()
    state = engine.new_run_state(seed=seed)
    state = engine.allocate(state, _allocation())

    choices: list[str] = []
    while state.status == "in_progress" and state.week <= 11:
        candidates = []
        for option_id in state.presented_options:
            candidate = engine.apply_choice(state, option_id)
            collapsed = 1 if candidate.status == "collapsed" else 0
            min_attr = min(candidate.attributes.values())
            candidates.append((collapsed, -min_attr, option_id, candidate))
        candidates.sort()
        choice = candidates[0][2]
        state = candidates[0][3]
        choices.append(choice)

    return choices


def _collapse_seed_and_choices() -> tuple[int, list[str]]:
    engine = GameEngine()
    for seed in range(1, 500):
        state = engine.new_run_state(seed=seed)
        state = engine.allocate(state, _collapse_allocation())
        choices: list[str] = []
        while state.status == "in_progress" and state.week <= 11:
            candidates = []
            for option_id in state.presented_options:
                candidate = engine.apply_choice(state, option_id)
                collapsed = 0 if candidate.status == "collapsed" else 1
                min_attr = min(candidate.attributes.values())
                candidates.append((collapsed, min_attr, option_id, candidate))
            candidates.sort()
            state = candidates[0][3]
            choices.append(candidates[0][2])
            if state.status == "collapsed":
                return seed, choices
    raise AssertionError("No collapse path found in search range")


async def _with_api_client(fn):
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await fn(client)


def test_guest_run_hidden_numbers_policy() -> None:
    async def scenario(client: httpx.AsyncClient):
        r = await client.post("/api/guest/init")
        assert r.status_code == 200

        create = await client.post("/api/runs")
        assert create.status_code == 200
        run_id = create.json()["run_id"]

        allocated = await client.post(f"/api/runs/{run_id}/allocate", json={"attributes": _allocation()})
        assert allocated.status_code == 200

        payload = allocated.json()
        assert payload["screen"] == "personality_reveal"
        assert "reveal_cn" in payload["payload"]

        # Must ack personality reveal before choosing week 1.
        must_ack = await client.post(f"/api/runs/{run_id}/choose", json={"option_id": "w01_o01"})
        assert must_ack.status_code == 400

        ack = await client.post(f"/api/runs/{run_id}/personality/ack")
        assert ack.status_code == 200
        payload = ack.json()
        assert payload["screen"] == "week"
        assert len(payload["payload"]["options"]) == 3
        assert "attributes" not in payload["payload"]

        bad_choice = await client.post(f"/api/runs/{run_id}/choose", json={"option_id": "w01_o99"})
        assert bad_choice.status_code == 400

        option_id = payload["payload"]["options"][0]["id"]
        chosen = await client.post(f"/api/runs/{run_id}/choose", json={"option_id": option_id})
        assert chosen.status_code == 200
        body = chosen.json()

        if body["screen"] == "week":
            assert "attributes" not in body["payload"]
            assert "options" in body["payload"]

    asyncio.run(_with_api_client(scenario))


def test_final_returns_outcome_and_report_payload(monkeypatch) -> None:
    seed = 8888
    monkeypatch.setattr(service, "randbits", lambda _: seed)
    plan = _safe_week_choices(seed)

    async def scenario(client: httpx.AsyncClient):
        r = await client.post("/api/guest/init")
        assert r.status_code == 200

        create = await client.post("/api/runs")
        assert create.status_code == 200
        run_id = create.json()["run_id"]

        allocated = await client.post(f"/api/runs/{run_id}/allocate", json={"attributes": _allocation()})
        assert allocated.status_code == 200

        screen = allocated.json()
        assert screen["screen"] == "personality_reveal"
        ack = await client.post(f"/api/runs/{run_id}/personality/ack")
        assert ack.status_code == 200
        screen = ack.json()
        for choice in plan:
            assert screen["screen"] == "week"
            picked = await client.post(f"/api/runs/{run_id}/choose", json={"option_id": choice})
            assert picked.status_code == 200
            screen = picked.json()
            if screen["screen"] != "week":
                break

        assert screen["screen"] == "finals"
        tactics = screen["payload"]["tactics"]
        assert isinstance(tactics, list) and len(tactics) == 6
        for tactic in tactics:
            assert "requirements" not in tactic
            assert "on_meet_apply" not in tactic
            assert "on_fail_apply" not in tactic

        final = await client.post(f"/api/runs/{run_id}/final", json={"tactic_id": "w12_t06"})
        assert final.status_code == 200
        body = final.json()
        assert body["screen"] == "final_outcome"
        result = body["payload"]["result"]
        assert "win_rate" not in result
        assert "roll_int" not in result
        assert "applied_deltas" not in result
        assert "attributes" not in body["payload"]
        assert body["payload"]["final_story_cn"]
        assert "最后一剑" in body["payload"]["final_story_cn"]
        assert "report_payload" in body
        assert body["report_payload"]["screen"] == "report"

        archive = await client.get("/api/archive")
        assert archive.status_code == 200
        achievement_ids = set(body["report_payload"]["payload"]["achievement_ids"])
        archive_ids = {record["achievement_id"] for record in archive.json()["achievement_records"]}
        assert achievement_ids.issubset(archive_ids)

    asyncio.run(_with_api_client(scenario))


def test_guest_can_start_fresh_run_after_finishing_current_one(monkeypatch) -> None:
    seed = 8888
    monkeypatch.setattr(service, "randbits", lambda _: seed)
    plan = _safe_week_choices(seed)

    async def scenario(client: httpx.AsyncClient):
        r = await client.post("/api/guest/init")
        assert r.status_code == 200

        create = await client.post("/api/runs")
        assert create.status_code == 200
        first_run_id = create.json()["run_id"]

        allocated = await client.post(f"/api/runs/{first_run_id}/allocate", json={"attributes": _allocation()})
        assert allocated.status_code == 200
        ack = await client.post(f"/api/runs/{first_run_id}/personality/ack")
        assert ack.status_code == 200

        screen = ack.json()
        for choice in plan:
            picked = await client.post(f"/api/runs/{first_run_id}/choose", json={"option_id": choice})
            assert picked.status_code == 200
            screen = picked.json()
            if screen["screen"] != "week":
                break

        assert screen["screen"] == "finals"
        final = await client.post(f"/api/runs/{first_run_id}/final", json={"tactic_id": "w12_t06"})
        assert final.status_code == 200
        body = final.json()
        assert body["screen"] == "final_outcome"

        active_before = await client.get("/api/runs/active")
        assert active_before.status_code == 200
        assert active_before.json()["run_id"] == first_run_id

        create_second = await client.post("/api/runs")
        assert create_second.status_code == 200
        second_run_id = create_second.json()["run_id"]
        assert second_run_id != first_run_id

        active_after = await client.get("/api/runs/active")
        assert active_after.status_code == 200
        assert active_after.json()["run_id"] == second_run_id
        assert active_after.json()["screen"] == "allocation"

    asyncio.run(_with_api_client(scenario))


def test_archive_orders_runs_by_last_play_time(monkeypatch) -> None:
    first_seed = 10101
    second_seed = 20202
    seeds = iter([first_seed, second_seed])
    monkeypatch.setattr(service, "randbits", lambda _: next(seeds))

    async def scenario(client: httpx.AsyncClient):
        init = await client.post("/api/guest/init")
        assert init.status_code == 200

        first_create = await client.post("/api/runs")
        assert first_create.status_code == 200
        first_run_id = first_create.json()["run_id"]

        allocated = await client.post(f"/api/runs/{first_run_id}/allocate", json={"attributes": _allocation()})
        assert allocated.status_code == 200

        second_create = await client.post("/api/runs")
        assert second_create.status_code == 200
        second_run_id = second_create.json()["run_id"]

        initial_archive = await client.get("/api/archive")
        assert initial_archive.status_code == 200
        initial_runs = initial_archive.json()["runs"]
        assert initial_runs[0]["run_id"] == second_run_id

        ack = await client.post(f"/api/runs/{first_run_id}/personality/ack")
        assert ack.status_code == 200

        updated_archive = await client.get("/api/archive")
        assert updated_archive.status_code == 200
        updated_runs = updated_archive.json()["runs"]
        assert updated_runs[0]["run_id"] == first_run_id

    asyncio.run(_with_api_client(scenario))


def test_collapse_screen_includes_personality_meta(monkeypatch) -> None:
    seed, choices = _collapse_seed_and_choices()
    monkeypatch.setattr(service, "randbits", lambda _: seed)

    async def scenario(client: httpx.AsyncClient):
        init = await client.post("/api/guest/init")
        assert init.status_code == 200

        create = await client.post("/api/runs")
        assert create.status_code == 200
        run_id = create.json()["run_id"]

        allocated = await client.post(f"/api/runs/{run_id}/allocate", json={"attributes": _collapse_allocation()})
        assert allocated.status_code == 200

        ack = await client.post(f"/api/runs/{run_id}/personality/ack")
        assert ack.status_code == 200

        body = ack.json()
        for choice in choices:
            collapsed = await client.post(f"/api/runs/{run_id}/choose", json={"option_id": choice})
            assert collapsed.status_code == 200
            body = collapsed.json()
            if body["screen"] == "collapse":
                break

        assert body["screen"] == "collapse"
        assert body["payload"]["personality_start_meta"]["name_cn"]

    asyncio.run(_with_api_client(scenario))


def test_archive_history_records_include_report_summary_fields(monkeypatch) -> None:
    win_seed = 8888
    collapse_seed, collapse_choices = _collapse_seed_and_choices()
    seeds = iter([win_seed, collapse_seed])
    monkeypatch.setattr(service, "randbits", lambda _: next(seeds))
    plan = _safe_week_choices(win_seed)

    async def scenario(client: httpx.AsyncClient):
        init = await client.post("/api/guest/init")
        assert init.status_code == 200

        win_create = await client.post("/api/runs")
        assert win_create.status_code == 200
        win_run_id = win_create.json()["run_id"]

        allocated = await client.post(f"/api/runs/{win_run_id}/allocate", json={"attributes": _allocation()})
        assert allocated.status_code == 200
        ack = await client.post(f"/api/runs/{win_run_id}/personality/ack")
        assert ack.status_code == 200
        screen = ack.json()

        for choice in plan:
            picked = await client.post(f"/api/runs/{win_run_id}/choose", json={"option_id": choice})
            assert picked.status_code == 200
            screen = picked.json()
            if screen["screen"] != "week":
                break

        assert screen["screen"] == "finals"
        final = await client.post(f"/api/runs/{win_run_id}/final", json={"tactic_id": "w12_t06"})
        assert final.status_code == 200

        collapse_create = await client.post("/api/runs")
        assert collapse_create.status_code == 200
        collapse_run_id = collapse_create.json()["run_id"]

        collapse_alloc = await client.post(f"/api/runs/{collapse_run_id}/allocate", json={"attributes": _collapse_allocation()})
        assert collapse_alloc.status_code == 200
        collapse_ack = await client.post(f"/api/runs/{collapse_run_id}/personality/ack")
        assert collapse_ack.status_code == 200
        body = collapse_ack.json()

        for choice in collapse_choices:
            collapsed = await client.post(f"/api/runs/{collapse_run_id}/choose", json={"option_id": choice})
            assert collapsed.status_code == 200
            body = collapsed.json()
            if body["screen"] == "collapse":
                break

        assert body["screen"] == "collapse"
        finish = await client.post(f"/api/runs/{collapse_run_id}/finish")
        assert finish.status_code == 200

        archive = await client.get("/api/archive")
        assert archive.status_code == 200
        history = archive.json()["history_records"]

        win_record = next(item for item in history if item["run_id"] == win_run_id)
        assert win_record["attributes_end"]["skill"] >= 0
        assert win_record["personality_start_meta"]["name_cn"]
        assert win_record["personality_end_meta"]["name_cn"]
        assert win_record["collapse_ending_name_cn"] is None

        collapse_record = next(item for item in history if item["run_id"] == collapse_run_id)
        assert collapse_record["status"] == "collapsed"
        assert collapse_record["collapse_ending_name_cn"]
        assert collapse_record["attributes_end"]["skill"] >= 0
        assert collapse_record["personality_start_meta"]["name_cn"]
        assert collapse_record["personality_end_meta"]["name_cn"]

    asyncio.run(_with_api_client(scenario))


def test_history_page_endpoint_paginates_results() -> None:
    username = f"history_user_{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)

    async def scenario(client: httpx.AsyncClient):
        register = await client.post("/api/auth/register", json={"username": username, "password": "secret123"})
        assert register.status_code == 200

        login = await client.post("/api/auth/login", json={"username": username, "password": "secret123"})
        assert login.status_code == 200

        with SessionLocal() as db:
            user = db.execute(select(User).where(User.username == username)).scalar_one()
            for idx in range(12):
                stamp = now - timedelta(minutes=idx)
                run = Run(
                    ruleset_version=settings.ruleset_version,
                    seed=50_000 + idx,
                    status="finished",
                    week=12,
                    owner_type="user",
                    user_id=user.id,
                    guest_id=None,
                    is_active_guest_run=False,
                    attributes={"stamina": 40 + idx, "skill": 35 + idx, "mind": 38 + idx, "academics": 45, "social": 42, "finance": 41},
                    min_attributes={"stamina": 30, "skill": 30, "mind": 30, "academics": 30, "social": 30, "finance": 30},
                    attributes_start={"stamina": 35, "skill": 30, "mind": 33, "academics": 40, "social": 37, "finance": 36},
                    personality_start="white_paper",
                    personality_end="white_paper",
                    personality_reveal_ack=True,
                    warning_attrs=[],
                    final_tactic_id="w12_t06",
                    final_requirements_met=True,
                    final_win_rate=0.75,
                    final_roll_int=77,
                    final_result="胜利",
                    final_tier="normal",
                    final_applied_deltas={"skill": 2, "mind": 1},
                    score=500 - idx,
                    grade_id="G1",
                    grade_label="稳定成长",
                    achievements=["ach_core_01"],
                    report={
                        "report_sections": {
                            "trajectory_summary_cn": "测试轨迹",
                            "coach_note_cn": "测试教练评语",
                            "teammate_note_cn": "测试队友评语",
                            "final_moment_cn": "测试最后一剑",
                        }
                    },
                    created_at=stamp,
                    updated_at=stamp,
                )
                db.add(run)
            db.commit()

        first = await client.get("/api/archive/history?page=1&page_size=10")
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["page"] == 1
        assert first_body["page_size"] == 10
        assert first_body["total"] == 12
        assert first_body["total_pages"] == 2
        assert len(first_body["items"]) == 10
        assert first_body["items"][0]["personality_start_meta"]["name_cn"]
        assert first_body["items"][0]["attributes_end"]["skill"] >= 35

        second = await client.get("/api/archive/history?page=2&page_size=10")
        assert second.status_code == 200
        second_body = second.json()
        assert second_body["page"] == 2
        assert len(second_body["items"]) == 2

    asyncio.run(_with_api_client(scenario))


def test_daily_play_quota_limits_new_runs() -> None:
    async def scenario(client: httpx.AsyncClient):
        init = await client.post("/api/guest/init")
        assert init.status_code == 200

        first = await client.post("/api/runs")
        assert first.status_code == 200

        second = await client.post("/api/runs")
        assert second.status_code == 200

        third = await client.post("/api/runs")
        assert third.status_code == 429

        archive = await client.get("/api/archive")
        assert archive.status_code == 200
        quota = archive.json()["play_quota"]
        assert quota["remaining_today"] == 0
        assert quota["base_used"] == 2

    asyncio.run(_with_api_client(scenario))


def test_share_redeem_grants_bonus_to_inviter() -> None:
    async def scenario(_client: httpx.AsyncClient):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as owner:
            owner_init = await owner.post("/api/guest/init")
            assert owner_init.status_code == 200

            invite = await owner.post("/api/share/invites")
            assert invite.status_code == 200
            token = invite.json()["invite_token"]
            duplicate_invite = await owner.post("/api/share/invites")
            assert duplicate_invite.status_code == 200
            assert duplicate_invite.json()["invite_token"] == token

            before = await owner.get("/api/archive")
            assert before.status_code == 200
            assert before.json()["play_quota"]["bonus_earned"] == 0

            async with httpx.AsyncClient(transport=transport, base_url="http://test") as scanner:
                scanner_init = await scanner.post("/api/guest/init")
                assert scanner_init.status_code == 200

                redeemed = await scanner.post(f"/api/share/invites/{token}/redeem")
                assert redeemed.status_code == 200
                assert redeemed.json()["granted_bonus"] is True
                assert redeemed.json()["play_quota"]["bonus_earned"] == 0

            after = await owner.get("/api/archive")
            assert after.status_code == 200
            quota = after.json()["play_quota"]
            assert quota["bonus_earned"] == 1
            assert quota["remaining_today"] == 3

    asyncio.run(_with_api_client(scenario))


def test_profile_and_leaderboard_flow(monkeypatch) -> None:
    seed = 8888
    monkeypatch.setattr(service, "randbits", lambda _: seed)
    plan = _safe_week_choices(seed)
    username = f"leader_user_{uuid.uuid4().hex[:8]}"

    async def scenario(client: httpx.AsyncClient):
        register = await client.post("/api/auth/register", json={"username": username, "password": "secret123"})
        assert register.status_code == 200

        login = await client.post("/api/auth/login", json={"username": username, "password": "secret123"})
        assert login.status_code == 200

        profile = await client.post(
            "/api/profile",
            json={
                "display_name": "侯俊毅",
                "phone_number": "13416005659",
                "external_user_id": f"mini-user-{uuid.uuid4().hex[:8]}",
            },
        )
        assert profile.status_code == 200

        create = await client.post("/api/runs")
        assert create.status_code == 200
        run_id = create.json()["run_id"]

        allocated = await client.post(f"/api/runs/{run_id}/allocate", json={"attributes": _allocation()})
        assert allocated.status_code == 200
        ack = await client.post(f"/api/runs/{run_id}/personality/ack")
        assert ack.status_code == 200

        screen = ack.json()
        for choice in plan:
            picked = await client.post(f"/api/runs/{run_id}/choose", json={"option_id": choice})
            assert picked.status_code == 200
            screen = picked.json()
            if screen["screen"] != "week":
                break

        assert screen["screen"] == "finals"
        final = await client.post(f"/api/runs/{run_id}/final", json={"tactic_id": "w12_t06"})
        assert final.status_code == 200
        report_payload = final.json()["report_payload"]["payload"]
        assert report_payload["achievement_percentile_text"].startswith("当前参赛者已经战胜")

        archive = await client.get("/api/archive")
        assert archive.status_code == 200
        body = archive.json()
        assert any(item["unlocked"] is True for item in body["achievement_catalog"])
        assert any(item["unlocked"] is False for item in body["achievement_catalog"])

        leaderboard = await client.get("/api/leaderboards/weekly?page=1")
        assert leaderboard.status_code == 200
        leaderboard_body = leaderboard.json()
        entries = leaderboard_body["entries"]
        assert entries
        assert leaderboard_body["self_entry"] is not None
        assert leaderboard_body["self_entry"]["display_name_masked"].startswith("侯**134****5659")

        achievement_board = await client.get("/api/leaderboards/achievements?page=1")
        assert achievement_board.status_code == 200
        assert achievement_board.json()["self_entry"] is not None

    asyncio.run(_with_api_client(scenario))


def test_leaderboard_uses_friday_beijing_week_and_monthly_is_total(monkeypatch) -> None:
    reference_now = datetime(2026, 4, 17, 12, 0, tzinfo=service.SHANGHAI_TZ)
    monkeypatch.setattr(service, "_now_shanghai", lambda: reference_now)
    viewer_username = f"viewer_{uuid.uuid4().hex[:8]}"
    old_username = f"old_board_{uuid.uuid4().hex[:8]}"
    recent_username = f"recent_board_{uuid.uuid4().hex[:8]}"
    early_tie_username = f"early_tie_{uuid.uuid4().hex[:8]}"
    late_tie_username = f"late_tie_{uuid.uuid4().hex[:8]}"
    achievement_tie_ids = [f"ach_tie_{idx}" for idx in range(30)]

    async def scenario(client: httpx.AsyncClient):
        register = await client.post("/api/auth/register", json={"username": viewer_username, "password": "secret123"})
        assert register.status_code == 200

        login = await client.post("/api/auth/login", json={"username": viewer_username, "password": "secret123"})
        assert login.status_code == 200

        with SessionLocal() as db:
            old_user = User(
                username=old_username,
                password_hash=hash_password("secret123"),
                display_name="旧榜用户",
                phone_number="13900000001",
                external_user_id=f"seed-{uuid.uuid4().hex[:10]}",
            )
            recent_user = User(
                username=recent_username,
                password_hash=hash_password("secret123"),
                display_name="周榜用户",
                phone_number="13900000002",
                external_user_id=f"seed-{uuid.uuid4().hex[:10]}",
            )
            early_tie_user = User(
                username=early_tie_username,
                password_hash=hash_password("secret123"),
                display_name="早平分",
                phone_number="13900000003",
                external_user_id=f"seed-{uuid.uuid4().hex[:10]}",
            )
            late_tie_user = User(
                username=late_tie_username,
                password_hash=hash_password("secret123"),
                display_name="晚平分",
                phone_number="13900000004",
                external_user_id=f"seed-{uuid.uuid4().hex[:10]}",
            )
            db.add(old_user)
            db.add(recent_user)
            db.add(early_tie_user)
            db.add(late_tie_user)
            db.flush()

            old_stamp = datetime(2026, 4, 16, 23, 59, tzinfo=service.SHANGHAI_TZ).astimezone(UTC)
            recent_stamp = datetime(2026, 4, 17, 0, 1, tzinfo=service.SHANGHAI_TZ).astimezone(UTC)
            early_tie_stamp = datetime(2026, 4, 17, 0, 2, tzinfo=service.SHANGHAI_TZ).astimezone(UTC)
            late_tie_stamp = datetime(2026, 4, 17, 0, 3, tzinfo=service.SHANGHAI_TZ).astimezone(UTC)

            db.add(
                Run(
                    ruleset_version=settings.ruleset_version,
                    seed=81_001,
                    status="finished",
                    week=12,
                    owner_type="user",
                    user_id=old_user.id,
                    guest_id=None,
                    is_active_guest_run=False,
                    attributes={"stamina": 70, "skill": 80, "mind": 68, "academics": 60, "social": 55, "finance": 52},
                    min_attributes={"stamina": 30, "skill": 30, "mind": 30, "academics": 30, "social": 30, "finance": 30},
                    attributes_start={"stamina": 42, "skill": 46, "mind": 40, "academics": 40, "social": 41, "finance": 41},
                    personality_start="white_paper",
                    personality_end="white_paper",
                    personality_reveal_ack=True,
                    warning_attrs=[],
                    final_tactic_id="w12_t06",
                    final_requirements_met=True,
                    final_win_rate=0.8,
                    final_roll_int=90,
                    final_result="胜利",
                    final_tier="fancy",
                    final_applied_deltas={"skill": 4, "mind": 2},
                    score=1901,
                    grade_id="G1",
                    grade_label="榜首测试",
                    achievements=achievement_tie_ids,
                    report={"report_sections": {"trajectory_summary_cn": "x", "coach_note_cn": "x", "teammate_note_cn": "x", "final_moment_cn": "x"}},
                    created_at=old_stamp,
                    updated_at=old_stamp,
                )
            )
            db.add(
                Run(
                    ruleset_version=settings.ruleset_version,
                    seed=81_002,
                    status="finished",
                    week=12,
                    owner_type="user",
                    user_id=recent_user.id,
                    guest_id=None,
                    is_active_guest_run=False,
                    attributes={"stamina": 62, "skill": 65, "mind": 61, "academics": 58, "social": 54, "finance": 50},
                    min_attributes={"stamina": 30, "skill": 30, "mind": 30, "academics": 30, "social": 30, "finance": 30},
                    attributes_start={"stamina": 42, "skill": 46, "mind": 40, "academics": 40, "social": 41, "finance": 41},
                    personality_start="white_paper",
                    personality_end="white_paper",
                    personality_reveal_ack=True,
                    warning_attrs=[],
                    final_tactic_id="w12_t06",
                    final_requirements_met=True,
                    final_win_rate=0.75,
                    final_roll_int=82,
                    final_result="胜利",
                    final_tier="normal",
                    final_applied_deltas={"skill": 3, "mind": 2},
                    score=1702,
                    grade_id="G1",
                    grade_label="周榜测试",
                    achievements=achievement_tie_ids,
                    report={"report_sections": {"trajectory_summary_cn": "x", "coach_note_cn": "x", "teammate_note_cn": "x", "final_moment_cn": "x"}},
                    created_at=recent_stamp,
                    updated_at=recent_stamp,
                )
            )
            for user, stamp in ((early_tie_user, early_tie_stamp), (late_tie_user, late_tie_stamp)):
                db.add(
                    Run(
                        ruleset_version=settings.ruleset_version,
                        seed=81_003 + user.id,
                        status="finished",
                        week=12,
                        owner_type="user",
                        user_id=user.id,
                        guest_id=None,
                        is_active_guest_run=False,
                        attributes={"stamina": 62, "skill": 65, "mind": 61, "academics": 58, "social": 54, "finance": 50},
                        min_attributes={"stamina": 30, "skill": 30, "mind": 30, "academics": 30, "social": 30, "finance": 30},
                        attributes_start={"stamina": 42, "skill": 46, "mind": 40, "academics": 40, "social": 41, "finance": 41},
                        personality_start="white_paper",
                        personality_end="white_paper",
                        personality_reveal_ack=True,
                        warning_attrs=[],
                        final_tactic_id="w12_t06",
                        final_requirements_met=True,
                        final_win_rate=0.75,
                        final_roll_int=82,
                        final_result="胜利",
                        final_tier="normal",
                        final_applied_deltas={"skill": 3, "mind": 2},
                        score=1800,
                        grade_id="G1",
                        grade_label="平分测试",
                        achievements=["ach_core_01"],
                        report={"report_sections": {"trajectory_summary_cn": "x", "coach_note_cn": "x", "teammate_note_cn": "x", "final_moment_cn": "x"}},
                        created_at=stamp,
                        updated_at=stamp,
                    )
                )
            db.commit()

        weekly = await client.get("/api/leaderboards/weekly?page=1")
        assert weekly.status_code == 200
        weekly_body = weekly.json()
        assert weekly_body["period_start"] == "2026-04-17"
        assert weekly_body["period_end"] == "2026-04-24"
        weekly_scores = [entry["score"] for entry in weekly_body["entries"]]
        assert 1702 in weekly_scores
        assert 1901 not in weekly_scores
        weekly_names = [entry["display_name_masked"] for entry in weekly_body["entries"]]
        early_tie_idx = next(i for i, name in enumerate(weekly_names) if name.startswith("早**"))
        late_tie_idx = next(i for i, name in enumerate(weekly_names) if name.startswith("晚**"))
        assert early_tie_idx < late_tie_idx

        monthly = await client.get("/api/leaderboards/monthly?page=1")
        assert monthly.status_code == 200
        monthly_body = monthly.json()
        assert monthly_body["period_start"] is None
        assert monthly_body["period_end"] is None
        monthly_scores = [entry["score"] for entry in monthly_body["entries"]]
        assert 1901 in monthly_scores
        assert 1702 in monthly_scores
        assert monthly_scores.index(1901) < monthly_scores.index(1702)

        achievement_board = await client.get("/api/leaderboards/achievements?page=1")
        assert achievement_board.status_code == 200
        achievement_names = [entry["display_name_masked"] for entry in achievement_board.json()["entries"]]
        old_idx = next(i for i, name in enumerate(achievement_names) if name.startswith("旧**"))
        recent_idx = next(i for i, name in enumerate(achievement_names) if name.startswith("周**"))
        assert old_idx < recent_idx

    asyncio.run(_with_api_client(scenario))
