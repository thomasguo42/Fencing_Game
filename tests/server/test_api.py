from __future__ import annotations

import asyncio
import uuid

import httpx

from engine import GameEngine
from server.app.main import app
from server.app import service


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

            before = await owner.get("/api/archive")
            assert before.status_code == 200
            assert before.json()["play_quota"]["bonus_earned"] == 0

            async with httpx.AsyncClient(transport=transport, base_url="http://test") as scanner:
                scanner_init = await scanner.post("/api/guest/init")
                assert scanner_init.status_code == 200

                redeemed = await scanner.post(f"/api/share/invites/{token}/redeem")
                assert redeemed.status_code == 200
                assert redeemed.json()["granted_bonus"] is True

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

        archive = await client.get("/api/archive")
        assert archive.status_code == 200
        body = archive.json()
        assert any(item["unlocked"] is True for item in body["achievement_catalog"])
        assert any(item["unlocked"] is False for item in body["achievement_catalog"])

        leaderboard = await client.get("/api/leaderboards/weekly?page=1")
        assert leaderboard.status_code == 200
        entries = leaderboard.json()["entries"]
        assert entries
        assert entries[0]["display_name_masked"].startswith("侯**134****5659")

        achievement_board = await client.get("/api/leaderboards/achievements?page=1")
        assert achievement_board.status_code == 200
        assert achievement_board.json()["self_entry"] is not None

    asyncio.run(_with_api_client(scenario))
