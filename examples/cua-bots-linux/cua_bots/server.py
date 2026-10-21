"""HTTP/WebSocket API and static UI for the Linux Cua Bots port."""
from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
import secrets
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .engine import CuaEngine, ModelConfig
from .model_gateway import ModelGateway
from .models import (
    AvatarConfig, BotColor, EarShape, EyeStyle, Harness, Placement, TaskSchedule,
    TaskState, jsonable,
)
from .rules import CustomRule, RuleBehavior, ActionClass
from .scheduler import RoutineClock
from . import sidecar
from .store import BotStore
from .volume import LocalVolume, VolumeError, VolumeLayout

VERSION = "0.1.0"
WEB_DIR_ROOT = Path(os.environ.get(
    "CUA_BOTS_WEB_DIR",
    Path(__file__).resolve().parent.parent / "web",
))
WEB_DIR = WEB_DIR_ROOT / "dist" if (WEB_DIR_ROOT / "dist").exists() else WEB_DIR_ROOT
OLLAMA = os.environ.get("CUA_BOTS_OLLAMA", "http://127.0.0.1:11434").rstrip("/")
PORT = int(os.environ.get("CUA_BOTS_PORT", "8765"))
HOST = os.environ.get("CUA_BOTS_HOST", "127.0.0.1")
DATA_DIR = Path(os.environ.get(
    "CUA_BOTS_DATA_DIR",
    Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "cua-bots-linux",
))


def host_ip() -> str:
    override = os.environ.get("CUA_BOTS_HOST_IP")
    if override:
        return override
    try:
        out = subprocess.check_output(["ip", "-4", "route", "get", "1.1.1.1"], text=True, timeout=3)
        match = re.search(r"\bsrc (\d+\.\d+\.\d+\.\d+)", out)
        if match:
            return match.group(1)
    except Exception:
        pass
    return "host.docker.internal"


async def ollama_available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            response = await client.get(f"{OLLAMA}/api/tags")
            return response.status_code == 200
    except Exception:
        return False


async def build_model() -> ModelConfig:
    if os.environ.get("CUA_BOTS_DEMO") == "1":
        return ModelConfig(demo=True, label="Scripted demo")
    url = os.environ.get("CUA_BOTS_MODEL_URL")
    model = os.environ.get("CUA_BOTS_MODEL")
    if url:
        key_vars = [v.strip() for v in os.environ.get(
            "CUA_BOTS_MODEL_KEY_VARS", "ANTHROPIC_API_KEY,OPENAI_API_KEY").split(",") if v.strip()]
        return ModelConfig(base_url=url, model=model, key_vars=key_vars,
                           label=f"Custom · {model or 'default'}")
    provider_keys = [name for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY")
                     if os.environ.get(name)]
    if provider_keys and os.environ.get("CUA_BOTS_MODEL_PROVIDER") != "ollama":
        return ModelConfig(model=model, key_vars=provider_keys,
                           label=f"Provider · {', '.join(provider_keys)}")
    # Prefer a sidecar on the Docker bridge: on Linux, a container usually
    # cannot reach a host service bound to 127.0.0.1 (and host firewalls often
    # block the bridge gateway too). The sidecar runs the host's own Ollama
    # binary and model store, so inference stays local.
    model = model or "llama3.2:3b"
    remote_ollama = os.environ.get("CUA_BOTS_OLLAMA")
    if remote_ollama and "127.0.0.1" not in remote_ollama and "localhost" not in remote_ollama:
        return ModelConfig(base_url=remote_ollama.rstrip("/") + "/v1", model=model,
                           key_vars=["OPENAI_API_KEY"], label=f"Ollama · {remote_ollama}")
    sidecar_url = sidecar.ensure(model) if os.name == "posix" else None
    if sidecar_url:
        models = sidecar.list_models(sidecar_url)
        if models and model not in models:
            model = models[0]
        os.environ.setdefault("OPENAI_API_KEY", "ollama")
        return ModelConfig(base_url=sidecar_url, model=model, key_vars=["OPENAI_API_KEY"],
                           label=f"Ollama sidecar · {model}")
    if await ollama_available():
        token = os.environ.get("CUA_BOTS_MODEL_TOKEN") or secrets.token_hex(16)
        os.environ["CUA_BOTS_MODEL_TOKEN"] = token
        os.environ["OPENAI_API_KEY"] = token
        base = f"http://{host_ip()}:{PORT}/model/v1"
        return ModelConfig(base_url=base, model=model, key_vars=["OPENAI_API_KEY"],
                           label=f"Ollama · {model}")
    return ModelConfig(demo=True, label="Scripted demo")


class WSManager:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.clients.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.clients.discard(websocket)

    async def send(self, websocket: WebSocket, payload: dict[str, Any]) -> None:
        try:
            await websocket.send_json(payload)
        except Exception:
            self.disconnect(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        for websocket in list(self.clients):
            await self.send(websocket, payload)

    def broadcast_nowait(self, payload: dict[str, Any]) -> None:
        try:
            asyncio.create_task(self.broadcast(payload))
        except RuntimeError:
            pass


# -- Request bodies -------------------------------------------------------

class CreateBotBody(BaseModel):
    name: str
    avatar: dict[str, Any] = {}
    harness: str = "hermes"
    placement: str = "local"


class SendBody(BaseModel):
    text: str


class DecideBody(BaseModel):
    approve: bool


class AvatarBody(BaseModel):
    color: str
    eyes: str
    ears: str


class RenameBody(BaseModel):
    name: str


class RulesBody(BaseModel):
    rules: list[dict[str, Any]]


class MemoryBody(BaseModel):
    text: str


class ScheduleBody(BaseModel):
    title: str
    prompt: str
    schedule: dict[str, Any]


class TaskPatchBody(BaseModel):
    state: Optional[str] = None
    notify_on_completion: Optional[bool] = None
    title: Optional[str] = None
    prompt: Optional[str] = None


class InputBody(BaseModel):
    action: str
    x: Optional[float] = None
    y: Optional[float] = None
    x1: Optional[float] = None
    y1: Optional[float] = None
    x2: Optional[float] = None
    y2: Optional[float] = None
    dx: Optional[float] = None
    dy: Optional[float] = None
    text: Optional[str] = None
    key: Optional[str] = None
    keys: Optional[list[str]] = None


class ReadBody(BaseModel):
    id: Optional[str] = None
    bot_id: Optional[str] = None


def create_app() -> FastAPI:
    manager = WSManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        model = await build_model()
        engine: Optional[CuaEngine] = None
        engine_error: Optional[str] = None
        try:
            engine = CuaEngine(model)
        except Exception as exc:  # noqa: BLE001
            engine_error = f"Couldn't start the Cua runtime: {exc}"

        volume = LocalVolume(DATA_DIR / "Volume")
        store = BotStore(volume, DATA_DIR, engine)
        clock = RoutineClock(store, DATA_DIR / "routines.json")
        app.state.store = store
        app.state.clock = clock
        app.state.engine = engine
        app.state.engine_error = engine_error
        app.state.model = model
        app.state.gateway = ModelGateway(
            demo=not bool(model.base_url) and model.demo,
            ollama_url=OLLAMA,
            token=os.environ.get("CUA_BOTS_MODEL_TOKEN"),
            model=model.model or "llama3.2:3b",
        )

        def state_payload() -> dict[str, Any]:
            payload = store.snapshot()
            payload["clock"] = {"log": clock.log[:20]}
            payload["engine_error"] = engine_error
            payload["model"] = {
                "label": model.label,
                "demo": model.demo,
                "base_url": model.base_url,
                "model": model.model,
                "sidecar": sidecar.status(),
            }
            payload["version"] = VERSION
            return jsonable(payload)

        app.state.state_payload = state_payload
        store.on_change = lambda _snapshot: manager.broadcast_nowait({"type": "state", "state": state_payload()})
        store.on_toast = lambda notification: manager.broadcast_nowait({"type": "toast", "notification": notification})
        store.reconnect()
        clock.start()
        app.state.state_payload = state_payload

        try:
            yield
        finally:
            await clock.stop()

    app = FastAPI(title="Cua Bots (Linux)", version=VERSION, lifespan=lifespan)

    def store() -> BotStore:
        return app.state.store

    def engine() -> CuaEngine:
        value = app.state.engine
        if value is None:
            raise HTTPException(503, app.state.engine_error or "Cua is not available")
        return value

    def payload() -> dict[str, Any]:
        return app.state.state_payload()

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": app.state.engine is not None,
            "engine_error": app.state.engine_error,
            "model": app.state.model.label,
            "demo": app.state.model.demo,
            "version": VERSION,
        }

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        return payload()

    @app.post("/api/bots")
    async def create_bot(body: CreateBotBody) -> dict[str, Any]:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "A bot needs a name")
        try:
            harness = Harness(body.harness)
            placement = Placement(body.placement)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if placement is Placement.CLOUD:
            raise HTTPException(400, "Cua Cloud has ended. Choose This computer.")
        avatar = AvatarConfig.from_dict(body.avatar)
        await store().create_bot(name, avatar, harness, placement)
        return payload()

    @app.post("/api/bots/{bot_id}/send")
    async def send(bot_id: str, body: SendBody) -> dict[str, Any]:
        if not store().bot(bot_id):
            raise HTTPException(404, "No such bot")
        await store().send(bot_id, body.text)
        return payload()

    @app.post("/api/bots/{bot_id}/pause")
    async def pause(bot_id: str) -> dict[str, Any]:
        await store().pause(bot_id)
        return payload()

    @app.post("/api/bots/{bot_id}/resume")
    async def resume(bot_id: str) -> dict[str, Any]:
        await store().resume(bot_id)
        return payload()

    @app.post("/api/bots/{bot_id}/interrupt")
    async def interrupt(bot_id: str) -> dict[str, Any]:
        bot = store().bot(bot_id)
        if bot:
            try:
                await engine().interrupt(bot)
            except Exception:
                pass
        return payload()

    @app.post("/api/bots/{bot_id}/restart")
    async def restart(bot_id: str) -> dict[str, Any]:
        await store().restart(bot_id)
        return payload()

    @app.post("/api/bots/{bot_id}/reset")
    async def reset(bot_id: str) -> dict[str, Any]:
        await store().reset(bot_id)
        return payload()

    @app.put("/api/bots/{bot_id}/avatar")
    async def avatar(bot_id: str, body: AvatarBody) -> dict[str, Any]:
        try:
            config = AvatarConfig(BotColor(body.color), EyeStyle(body.eyes), EarShape(body.ears))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        store().update_avatar(bot_id, config)
        return payload()

    @app.put("/api/bots/{bot_id}/name")
    async def rename(bot_id: str, body: RenameBody) -> dict[str, Any]:
        store().rename(bot_id, body.name)
        return payload()

    @app.get("/api/bots/{bot_id}/rules")
    async def get_rules(bot_id: str) -> dict[str, Any]:
        return jsonable({"rules": store().rules_for(bot_id)})

    @app.put("/api/bots/{bot_id}/rules")
    async def set_rules(bot_id: str, body: RulesBody) -> dict[str, Any]:
        rules = [CustomRule.from_dict(item) for item in body.rules]
        store().set_rules(bot_id, rules)
        return payload()

    @app.get("/api/bots/{bot_id}/memory")
    async def get_memory(bot_id: str) -> dict[str, Any]:
        return {"text": store().memory(bot_id)}

    @app.put("/api/bots/{bot_id}/memory")
    async def set_memory(bot_id: str, body: MemoryBody) -> dict[str, Any]:
        try:
            store().volume.write_text(VolumeLayout.memory(bot_id), body.text)
        except VolumeError as exc:
            raise HTTPException(400, str(exc)) from exc
        return payload()

    @app.post("/api/bots/{bot_id}/inbox")
    async def inbox(bot_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
        data = await file.read()
        name = Path(file.filename or "file").name
        try:
            store().volume.write(VolumeLayout.inbox(bot_id) + name, data)
        except VolumeError as exc:
            raise HTTPException(400, str(exc)) from exc
        return payload()

    @app.get("/api/bots/{bot_id}/outputs")
    async def outputs(bot_id: str) -> dict[str, Any]:
        return {"files": store().outputs(bot_id)}

    @app.get("/api/output")
    async def output(path: str) -> FileResponse:
        root = store().volume.root
        target = (root / path.lstrip("/")).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise HTTPException(404, "No such output")
        media, _ = mimetypes.guess_type(target.name)
        return FileResponse(target, media_type=media or "application/octet-stream")

    @app.get("/api/bots/{bot_id}/screenshot")
    async def screenshot(bot_id: str) -> Response:
        bot = store().bot(bot_id)
        if not bot:
            raise HTTPException(404, "No such bot")
        try:
            data, width, height = await engine().screenshot(bot)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, str(exc)) from exc
        return Response(content=data, media_type="image/jpeg",
                        headers={"Cache-Control": "no-store", "X-Screen-Width": str(width),
                                 "X-Screen-Height": str(height)})

    @app.get("/api/bots/{bot_id}/pointer")
    async def pointer(bot_id: str) -> dict[str, Any]:
        bot = store().bot(bot_id)
        if not bot:
            raise HTTPException(404, "No such bot")
        point = await engine().pointer(bot)
        return {"x": point[0], "y": point[1]} if point else {"x": None, "y": None}

    @app.post("/api/bots/{bot_id}/input")
    async def input_action(bot_id: str, body: InputBody) -> dict[str, Any]:
        bot = store().bot(bot_id)
        if not bot:
            raise HTTPException(404, "No such bot")
        kwargs = body.model_dump(exclude_none=True, exclude={"action"})
        try:
            await engine().input(bot, body.action, **kwargs)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True}

    @app.post("/api/bots/{bot_id}/tasks")
    async def add_task(bot_id: str, body: ScheduleBody) -> dict[str, Any]:
        schedule = TaskSchedule.from_dict(body.schedule)
        if schedule is None:
            raise HTTPException(400, "Invalid schedule")
        store().schedule(bot_id, body.title, body.prompt or body.title, schedule)
        return payload()

    @app.patch("/api/tasks/{task_id}")
    async def patch_task(task_id: str, body: TaskPatchBody) -> dict[str, Any]:
        for bot in store().bots:
            task = next((t for t in store().tasks_for(bot.id) if t.id == task_id), None)
            if not task:
                continue
            if body.state:
                task.state = TaskState(body.state)
            if body.notify_on_completion is not None:
                task.notify_on_completion = body.notify_on_completion
            if body.title is not None:
                task.title = body.title
            if body.prompt is not None:
                task.prompt = body.prompt
            store().update_task(task)
            return payload()
        raise HTTPException(404, "No such task")

    @app.delete("/api/tasks/{task_id}")
    async def delete_task(task_id: str) -> dict[str, Any]:
        for bot in store().bots:
            if any(t.id == task_id for t in store().tasks_for(bot.id)):
                store().delete_task(bot.id, task_id)
                return payload()
        raise HTTPException(404, "No such task")

    @app.post("/api/tasks/{task_id}/fire")
    async def fire_task(task_id: str) -> dict[str, Any]:
        for bot in store().bots:
            if any(t.id == task_id for t in store().tasks_for(bot.id)):
                await store().fire(task_id, bot.id)
                return payload()
        raise HTTPException(404, "No such task")

    @app.post("/api/approvals/{approval_id}")
    async def decide(approval_id: str, body: DecideBody) -> dict[str, Any]:
        await store().decide(approval_id, body.approve)
        return payload()

    @app.post("/api/approvals/{approval_id}/signin")
    async def sign_in(approval_id: str) -> dict[str, Any]:
        await store().sign_in_manual(approval_id)
        return payload()

    @app.post("/api/notifications/read")
    async def read(body: ReadBody) -> dict[str, Any]:
        if body.id:
            store().mark_read(body.id)
        elif body.bot_id:
            store().mark_all_read(body.bot_id)
        return payload()

    @app.websocket("/ws")
    async def websocket(websocket: WebSocket) -> None:
        await manager.connect(websocket)
        await manager.send(websocket, {"type": "state", "state": payload()})
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)
        except Exception:
            manager.disconnect(websocket)

    # The gateway is created in lifespan; these routes read it at request time.
    @app.get("/model/v1/models")
    async def model_models(request: Request):
        return await app.state.gateway.models(request)

    @app.post("/model/v1/chat/completions")
    async def model_chat(request: Request):
        return await app.state.gateway.chat(request)

    if WEB_DIR.exists():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")

    return app


app = create_app()
