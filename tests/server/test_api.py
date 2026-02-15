from __future__ import annotations

from fastapi.testclient import TestClient

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


def test_guest_run_hidden_numbers_policy() -> None:
    with TestClient(app) as client:
        r = client.post("/api/guest/init")
        assert r.status_code == 200

        create = client.post("/api/runs")
        assert create.status_code == 200
        run_id = create.json()["run_id"]

        allocated = client.post(f"/api/runs/{run_id}/allocate", json={"attributes": _allocation()})
        assert allocated.status_code == 200

        payload = allocated.json()
        assert payload["screen"] == "week"
        assert len(payload["payload"]["options"]) == 3
        assert "attributes" not in payload["payload"]

        bad_choice = client.post(f"/api/runs/{run_id}/choose", json={"option_id": "w01_o99"})
        assert bad_choice.status_code == 400

        option_id = payload["payload"]["options"][0]["id"]
        chosen = client.post(f"/api/runs/{run_id}/choose", json={"option_id": option_id})
        assert chosen.status_code == 200
        body = chosen.json()

        if body["screen"] == "week":
            assert "attributes" not in body["payload"]
            assert "options" in body["payload"]


def test_final_returns_outcome_and_report_payload(monkeypatch) -> None:
    seed = 8888
    monkeypatch.setattr(service, "randbits", lambda _: seed)
    plan = _safe_week_choices(seed)

    with TestClient(app) as client:
        r = client.post("/api/guest/init")
        assert r.status_code == 200

        create = client.post("/api/runs")
        assert create.status_code == 200
        run_id = create.json()["run_id"]

        allocated = client.post(f"/api/runs/{run_id}/allocate", json={"attributes": _allocation()})
        assert allocated.status_code == 200

        screen = allocated.json()
        for choice in plan:
            assert screen["screen"] == "week"
            picked = client.post(f"/api/runs/{run_id}/choose", json={"option_id": choice})
            assert picked.status_code == 200
            screen = picked.json()
            if screen["screen"] != "week":
                break

        assert screen["screen"] == "finals"
        tactics = screen["payload"]["tactics"]
        assert isinstance(tactics, list) and len(tactics) == 6
        for tactic in tactics:
            assert "on_meet_apply" not in tactic
            assert "on_fail_apply" not in tactic

        final = client.post(f"/api/runs/{run_id}/final", json={"tactic_id": "w12_t06"})
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
