from __future__ import annotations

import time

from fastapi.testclient import TestClient


def test_demo_api_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("CUA_BOTS_DEMO", "1")
    monkeypatch.setenv("CUA_BOTS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUA_BOTS_HOST", "127.0.0.1")

    from cua_bots.server import create_app

    app = create_app()
    with TestClient(app) as client:
        health = client.get("/api/health").json()
        assert health["ok"] is True
        assert health["demo"] is True

        created = client.post("/api/bots", json={
            "name": "Ada",
            "avatar": {"color": "violet", "eyes": "star", "ears": "scalloped"},
            "harness": "hermes",
            "placement": "local",
        })
        assert created.status_code == 200
        assert created.json()["bots"][0]["id"] == "ada"

        # The intro is a scripted demo run; give the poll loop a moment.
        for _ in range(100):
            state = client.get("/api/state").json()
            if any("scripted demo" in message["text"] for message in state["messages"].get("ada", [])):
                break
            time.sleep(0.05)
        state = client.get("/api/state").json()
        assert state["bots"][0]["run_id"].startswith("demo-")

        assert client.post("/api/bots/ada/send", json={"text": "Buy a standing desk"}).status_code == 200
        for _ in range(100):
            state = client.get("/api/state").json()
            if state["approvals"]:
                break
            time.sleep(0.05)
        assert state["approvals"][0]["action"] == "Buy the standing desk"
        approval_id = state["approvals"][0]["id"]
        assert client.post(f"/api/approvals/{approval_id}", json={"approve": True}).status_code == 200
        for _ in range(100):
            state = client.get("/api/state").json()
            if any(m["kind"].get("type") == "result" for m in state["messages"]["ada"]):
                break
            time.sleep(0.05)
        assert any(m["kind"].get("type") == "result" for m in state["messages"]["ada"])

        assert client.put("/api/bots/ada/memory", json={"text": "# Memory\n"}).status_code == 200
        assert client.get("/api/bots/ada/memory").json()["text"] == "# Memory\n"
        assert client.put("/api/bots/ada/avatar", json={
            "color": "orange", "eyes": "happy", "ears": "round",
        }).json()["bots"][0]["avatar"]["color"] == "orange"

        assert client.post("/api/bots/ada/tasks", json={
            "title": "Morning briefing",
            "prompt": "Summarize mail",
            "schedule": {"kind": "daily", "hour": 9, "minute": 0},
        }).status_code == 200
        state = client.get("/api/state").json()
        assert any(task["schedule"] for task in state["tasks"]["ada"])
