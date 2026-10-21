"""The Cua engine: one Space per bot, an agent run in it, a Volume home.

Uses the published Python ``cua`` Spaces SDK (the same Rust runtime the Swift
app links).  The surface mirrors ``CuaBotsCua/CuaEngine.swift``.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import cua

from .models import Bot, Harness
from .volume import LocalVolume, VolumeLayout


class EngineError(Exception):
    pass


@dataclass
class EngineUpdate:
    kind: str  # assistant | tool | setup | turn_ended | failed
    turn: int = 0
    text: str = ""
    title: str = ""


@dataclass
class ModelConfig:
    """Where the harness gets its model.

    ``base_url`` is the backend's local gateway when the app runs Ollama (or a
    scripted model); otherwise it is None and the harness talks to its own
    provider with a key forwarded from the host.
    """

    base_url: Optional[str] = None
    model: Optional[str] = None
    key_vars: list[str] = field(default_factory=list)
    demo: bool = False
    label: str = ""

    def vars_for(self, harness: Harness) -> list[str]:
        if self.key_vars:
            return list(self.key_vars)
        return list(harness.key_vars)


class CuaEngine:
    def __init__(self, model: Optional[ModelConfig] = None):
        self.cua = cua.embedded()
        self.model = model or ModelConfig()
        self._turn_text: dict[tuple[str, int], str] = {}
        self._demo_runs: dict[str, dict[str, Any]] = {}

    # -- Spaces -----------------------------------------------------------

    async def provision(self, bot: Bot, progress: Callable[[str, str], None]) -> str:
        # ``reuse=True`` in the SDK reuses *any* existing local Space (it
        # ignored the name in testing), which would make every bot share one
        # computer. Reuse only an exact name match, otherwise create one.
        try:
            existing = next((space for space in await self.cua.spaces().list()
                             if space.name == bot.space_name), None)
            if existing:
                progress("creating", f"Reusing {bot.space_name}")
                return existing.id
        except Exception:
            pass
        progress("creating", f"Creating {bot.space_name} on this computer")
        options = cua.SpaceCreateOptions(
            name=bot.space_name,
            on="local",
            kind="container",
            wait=True,
            reuse=False,
        )
        result = await self.cua.spaces().create(options)
        if result.space is None:
            raise EngineError(f"the Space is still being created ({result.pending_id or 'pending'})")
        return result.space.id

    async def space(self, bot: Bot) -> Any:
        if not bot.space_id:
            raise EngineError(f"{bot.name} has no computer yet.")
        return await self.cua.spaces().space(bot.space_id)

    async def home(self, bot: Bot, space: Any) -> str:
        guest = await space.home()
        return f"{guest}/bots/{bot.id}"

    # -- Runs -------------------------------------------------------------

    async def start(self, bot: Bot, volume: LocalVolume, prompt: str) -> str:
        if self.model.demo:
            return self.start_demo(bot, prompt)
        space = await self.space(bot)
        home = await self.home(bot, space)
        await self.hydrate(bot, volume, space, home)
        key_vars = self.model.vars_for(bot.harness)
        options = cua.SpaceAgentOptions(
            cwd=home,
            model=self.model.model,
            base_url=self.model.base_url,
            env_from_host=key_vars,
            exit_when_idle=False,
        )
        report = await space.agent_start(
            agent=bot.harness.value,
            prompt=prompt,
            show=False,
            options=options,
        )
        return report.run_id

    async def send(self, bot: Bot, text: str) -> None:
        if not bot.run_id:
            raise EngineError(f"{bot.name} isn't running.")
        if bot.run_id.startswith("demo-"):
            self.demo_send(bot, bot.run_id, text)
            return
        space = await self.space(bot)
        report = await space.agent_message(bot.run_id, text, False)
        if not report.ok:
            raise EngineError(report.reason or "the agent refused the message")

    async def poll(self, bot: Bot, cursor: int) -> tuple[list[EngineUpdate], int]:
        if not bot.run_id:
            return [], cursor
        if bot.run_id.startswith("demo-"):
            return self.demo_events(bot.run_id, cursor)
        space = await self.space(bot)
        raw = await space.agent_events(bot.run_id, cursor, 500)
        page = json.loads(raw) if raw else {}
        events = page.get("events") or []
        updates: list[EngineUpdate] = []
        for event in events:
            kind = event.get("kind", "")
            turn = int(event.get("turn") or 0)
            if kind == "message":
                key = (bot.run_id, turn)
                text = self._turn_text.get(key, "") + (event.get("text") or "")
                self._turn_text[key] = text
                updates.append(EngineUpdate("assistant", turn, text=text))
            elif kind == "tool_call":
                updates.append(EngineUpdate("tool", turn, title=event.get("tool_title") or "Working"))
            elif kind == "install":
                updates.append(EngineUpdate("setup", turn, text=event.get("text") or "Installing the agent"))
            elif kind == "turn_ended":
                self._turn_text.pop((bot.run_id, turn), None)
                updates.append(EngineUpdate("turn_ended", turn))
            elif kind == "error":
                updates.append(EngineUpdate("failed", turn, text=event.get("text") or "The agent reported an error"))
            elif kind == "exited":
                updates.append(EngineUpdate("failed", turn,
                                            text=f"The agent stopped: {event.get('text') or 'exited'}"))
        next_cursor = int(page.get("cursor") or cursor)
        return updates, next_cursor

    async def stop(self, bot: Bot) -> None:
        if not bot.run_id or bot.run_id.startswith("demo-"):
            return
        try:
            space = await self.space(bot)
            await space.agent_stop(bot.run_id)
        except Exception:
            pass

    async def interrupt(self, bot: Bot) -> None:
        if not bot.run_id or bot.run_id.startswith("demo-"):
            return
        space = await self.space(bot)
        await space.agent_interrupt(bot.run_id)

    async def pause(self, bot: Bot) -> None:
        await self.interrupt(bot)

    async def resume(self, bot: Bot) -> None:
        return

    async def reset(self, bot: Bot) -> None:
        if bot.run_id and bot.run_id.startswith("demo-"):
            self._demo_runs.pop(bot.run_id, None)
            return
        try:
            if bot.run_id:
                space = await self.space(bot)
                await space.agent_stop(bot.run_id)
        except Exception:
            pass
        if bot.space_id:
            try:
                await self.cua.spaces().delete(bot.space_id)
            except Exception:
                pass

    # -- Volume home ------------------------------------------------------

    async def hydrate(self, bot: Bot, volume: LocalVolume, space: Any, home: str) -> None:
        prefix = VolumeLayout.home(bot.id)
        for entry in volume.walk(prefix):
            data = volume.read(entry.path)
            if data is None:
                continue
            rel = entry.path[len(prefix):]
            if rel.startswith("identity/"):
                continue
            await space.write(f"{home}/{rel}", data)
        await space.bash(f"mkdir -p '{home}/outputs' '{home}/inbox' '{home}/memory'", 10_000)

    async def push(self, bot: Bot, volume: LocalVolume) -> None:
        space = await self.space(bot)
        home = await self.home(bot, space)
        prefix = VolumeLayout.home(bot.id)
        paths = [
            VolumeLayout.instructions(bot.id, bot.harness),
            VolumeLayout.rules(bot.id),
        ]
        paths.extend(entry.path for entry in volume.walk(VolumeLayout.inbox(bot.id)))
        for path in paths:
            data = volume.read(path)
            if data is None:
                continue
            rel = path[len(prefix):]
            await space.write(f"{home}/{rel}", data)

    async def checkpoint(self, bot: Bot, volume: LocalVolume) -> None:
        space = await self.space(bot)
        home = await self.home(bot, space)
        listing = await space.bash(
            f"cd '{home}' 2>/dev/null && find memory outputs -type f -size -8M 2>/dev/null | head -200",
            15_000,
        )
        for rel in (listing.stdout or "").split("\n"):
            rel = rel.strip()
            if not rel:
                continue
            with tempfile.TemporaryDirectory(prefix="cua-bots-") as temp:
                dest = Path(temp) / Path(rel).parent
                dest.mkdir(parents=True, exist_ok=True)
                try:
                    await space.download(f"{home}/{rel}", str(dest))
                except Exception:
                    continue
                local = dest / Path(rel).name
                if local.exists():
                    try:
                        volume.write(VolumeLayout.home(bot.id) + rel, local.read_bytes())
                    except Exception:
                        # The Volume refuses secrets; the file stays in the Space.
                        pass

    # -- Live screen and input -------------------------------------------

    async def screenshot(self, bot: Bot, max_dimension: int = 1280, quality: int = 70) -> tuple[bytes, int, int]:
        space = await self.space(bot)
        shot = await space.screenshot(cua.ScreenshotOptions(
            format=cua.ImageFormat.JPEG, quality=quality, max_dimension=max_dimension))
        return shot.image, shot.width, shot.height

    async def pointer(self, bot: Bot) -> Optional[tuple[float, float]]:
        try:
            space = await self.space(bot)
            point = await space.spacesd().cursor_position()
            return float(point.x), float(point.y)
        except Exception:
            return None

    async def input(self, bot: Bot, action: str, **kwargs: Any) -> None:
        space = await self.space(bot)
        client = space.spacesd()
        if action == "click":
            await client.click(float(kwargs["x"]), float(kwargs["y"]))
        elif action == "double_click":
            await client.double_click(float(kwargs["x"]), float(kwargs["y"]))
        elif action == "move":
            await client.move_to(float(kwargs["x"]), float(kwargs["y"]))
        elif action == "scroll":
            await client.scroll(float(kwargs.get("dx", 0)), float(kwargs.get("dy", 0)))
        elif action == "drag":
            await client.drag(float(kwargs["x1"]), float(kwargs["y1"]),
                              float(kwargs["x2"]), float(kwargs["y2"]))
        elif action == "type":
            await client.type_text(str(kwargs.get("text", "")))
        elif action == "key":
            await client.press(str(kwargs.get("key", "")))
        elif action == "hotkey":
            await client.hotkey([str(k) for k in kwargs.get("keys", [])])
        else:
            raise EngineError(f"unknown input action {action!r}")

    # -- Demo mode --------------------------------------------------------

    def start_demo(self, bot: Bot, prompt: str) -> str:
        """A scripted agent used when no model is configured.

        It exercises the whole store/UI path (status, steps, approvals,
        schedules, outputs) without a harness.  The real engine is used as
        soon as a model endpoint or provider key is available.
        """
        run_id = f"demo-{bot.id}-{len(self._demo_runs) + 1}"
        self._demo_runs[run_id] = {"bot_id": bot.id, "prompt": prompt, "cursor": 0,
                                   "events": self._demo_events(bot, prompt)}
        return run_id

    def demo_events(self, run_id: str, cursor: int) -> tuple[list[EngineUpdate], int]:
        run = self._demo_runs.get(run_id)
        if not run:
            return [], cursor
        events = run["events"]
        batch = events[cursor:]
        run["cursor"] = len(events)
        return [EngineUpdate(**event) for event in batch], len(events)

    def demo_send(self, bot: Bot, run_id: str, text: str) -> None:
        run = self._demo_runs.get(run_id)
        if run is None:
            return
        run["events"].extend(self._demo_events(bot, text))

    def _demo_events(self, bot: Bot, prompt: str, followup: bool = False) -> list[dict[str, Any]]:
        low = prompt.lower()
        events: list[dict[str, Any]] = []
        if low.startswith("approved:"):
            events = [
                {"kind": "assistant", "turn": 1, "text": "[[status: Ready]]\nThanks. This demo runs a scripted model, so nothing was bought. A real model would go ahead now.\n"},
                {"kind": "assistant", "turn": 1, "text": "[[done: Buy the standing desk]]\n"},
                {"kind": "turn_ended", "turn": 1},
            ]
        elif low.startswith("denied:"):
            events = [
                {"kind": "assistant", "turn": 1, "text": "[[status: Ready]]\nOkay, I won't. I'll leave it for you.\n"},
                {"kind": "turn_ended", "turn": 1},
            ]
        elif low.startswith("signed in"):
            events = [
                {"kind": "assistant", "turn": 1, "text": "[[status: Ready]]\nI'm signed in. Your notifications are open on my computer.\n"},
                {"kind": "turn_ended", "turn": 1},
            ]
        elif "buy" in low or "order" in low or "purchase" in low:
            events = [
                {"kind": "assistant", "turn": 1, "text": "[[status: Waiting for you]]\nBuying something needs your approval under your rules.\n"},
                {"kind": "assistant", "turn": 1, "text": "[[ask: Buy the standing desk | From the shop with the card saved there.]]\n"},
                {"kind": "turn_ended", "turn": 1},
            ]
        elif "standing desk" in low or "research" in low:
            events = [
                {"kind": "assistant", "turn": 1, "text": "[[status: Researching]]\n"},
                {"kind": "assistant", "turn": 1, "text": "[[step: Open the sources]]\n"},
                {"kind": "tool", "turn": 1, "title": "Open the sources"},
                {"kind": "assistant", "turn": 1, "text": "[[step-done: Open the sources]]\n[[step: Write it up]]\n"},
                {"kind": "assistant", "turn": 1, "text": "[[step-done: Write it up]]\n[[output: outputs/standing-desks.md]]\n[[status: Ready]]\n"},
                {"kind": "assistant", "turn": 1, "text": "[[done: Research standing desks]]\n"},
                {"kind": "assistant", "turn": 1, "text": "Your research is ready. I wrote a short summary in outputs/standing-desks.md.\n"},
                {"kind": "turn_ended", "turn": 1},
            ]
        elif "every morning" in low or "schedule" in low or "daily" in low:
            events = [
                {"kind": "assistant", "turn": 1, "text": "I'll check every morning at 9 and tell you what changed.\n"},
                {"kind": "assistant", "turn": 1, "text": "[[schedule: daily 09:00 | Morning briefing | Summarize what changed on news.ycombinator.com since yesterday]]\n"},
                {"kind": "turn_ended", "turn": 1},
            ]
        elif "login" in low or "sign in" in low or "github" in low:
            events = [
                {"kind": "assistant", "turn": 1, "text": "[[status: Waiting for you]]\nI need to be signed in to github.com to read your notifications.\n"},
                {"kind": "assistant", "turn": 1, "text": "[[login: github.com]]\n"},
                {"kind": "turn_ended", "turn": 1},
            ]
        else:
            events = [
                {"kind": "assistant", "turn": 1, "text": "[[status: Thinking]]\n"},
                {"kind": "assistant", "turn": 1, "text": "[[step: Look around]]\n"},
                {"kind": "assistant", "turn": 1, "text": "[[step-done: Look around]]\n[[status: Ready]]\n"},
                {"kind": "assistant", "turn": 1, "text": (
                    f"Hi, I'm {bot.name}. I have my own computer, and I keep working while you're away. "
                    "This run is a scripted demo because no model is configured; connect Ollama or a provider key "
                    "to let me reason for real.\n"
                )},
                {"kind": "turn_ended", "turn": 1},
            ]
        if followup:
            events = [
                {"kind": "assistant", "turn": 2, "text": "[[status: Ready]]\n"},
                {"kind": "assistant", "turn": 2, "text": f"Got it: {prompt}\n"},
                {"kind": "turn_ended", "turn": 2},
            ]
        return events
