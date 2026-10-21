"""App state: bots, conversations, work, approvals and notifications.

Mirrors ``CuaBotsCore/Store/BotStore.swift``, with asyncio in place of
Combine/Swift concurrency.  The Volume stays the source of truth for a bot's
identity; ``state.json`` carries conversations and notifications.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from .directives import parse as parse_directives
from .directives import render_instructions
from .engine import CuaEngine, EngineUpdate
from .models import (
    ApprovalRequest, ApprovalState, AvatarConfig, Bot, BotMood, BotNotification,
    BotTask, ChatMessage, Harness, MessageRole, Placement, TaskSchedule, TaskState,
    TaskStep, agent_name, iso, jsonable, new_id, utcnow,
)
from .rules import CustomRule, RuleEngine, default_rules
from .volume import LocalVolume, VolumeLayout


class BotStore:
    def __init__(
        self,
        volume: LocalVolume,
        data_directory: Path | str,
        engine: Optional[CuaEngine] = None,
        on_change: Optional[Callable[[dict[str, Any]], None]] = None,
        on_toast: Optional[Callable[[dict[str, Any]], None]] = None,
    ):
        self.volume = volume
        self.data_directory = Path(data_directory).expanduser()
        self.data_directory.mkdir(parents=True, exist_ok=True)
        self.engine = engine
        self.on_change = on_change
        self.on_toast = on_toast

        self.bots: list[Bot] = []
        self.messages: dict[str, list[ChatMessage]] = {}
        self.tasks: dict[str, list[BotTask]] = {}
        self.rules: dict[str, list[CustomRule]] = {}
        self.approvals: list[ApprovalRequest] = []
        self.notifications: list[BotNotification] = []
        self.setup_phase: dict[str, str] = {}
        self.last_error: Optional[str] = None
        self.busy: set[str] = set()

        self._cursors: dict[str, int] = {}
        self._turn_text: dict[str, tuple[int, str]] = {}
        self._pollers: dict[str, asyncio.Task] = {}
        self._current_task: dict[str, str] = {}
        self._lock = asyncio.Lock()

        self.load()

    # -- Reading ----------------------------------------------------------

    def bot(self, bot_id: str) -> Optional[Bot]:
        return next((b for b in self.bots if b.id == bot_id), None)

    def messages_for(self, bot_id: str) -> list[ChatMessage]:
        return self.messages.get(bot_id, [])

    def tasks_for(self, bot_id: str) -> list[BotTask]:
        return self.tasks.get(bot_id, [])

    def rules_for(self, bot_id: str) -> list[CustomRule]:
        return self.rules.get(bot_id) or default_rules()

    def pending_approvals(self, bot_id: Optional[str] = None) -> list[ApprovalRequest]:
        return [a for a in self.approvals if a.state is ApprovalState.PENDING
                and (bot_id is None or a.bot_id == bot_id)]

    def approval(self, approval_id: str) -> Optional[ApprovalRequest]:
        return next((a for a in self.approvals if a.id == approval_id), None)

    def is_busy(self, bot_id: str) -> bool:
        return bot_id in self.busy

    def memory(self, bot_id: str) -> str:
        return self.volume.read_text(VolumeLayout.memory(bot_id)) or ""

    def outputs(self, bot_id: str) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self.volume.walk(VolumeLayout.outputs(bot_id))]

    def unread_count(self) -> int:
        return sum(1 for n in self.notifications if not n.read)

    def last_active(self, bot_id: str) -> Optional[datetime]:
        for message in reversed(self.messages_for(bot_id)):
            if message.role is MessageRole.BOT:
                return message.date
        return None

    # -- Snapshot ---------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        return jsonable({
            "bots": self.bots,
            "messages": self.messages,
            "tasks": self.tasks,
            "rules": self.rules,
            "approvals": self.approvals,
            "notifications": self.notifications,
            "setup_phase": self.setup_phase,
            "busy": sorted(self.busy),
            "last_error": self.last_error,
        })

    def emit(self) -> None:
        if self.on_change:
            self.on_change(self.snapshot())

    def toast(self, notification: BotNotification) -> None:
        if self.on_toast:
            self.on_toast(jsonable(notification))

    # -- Creating ---------------------------------------------------------

    async def create_bot(self, name: str, avatar: AvatarConfig, harness: Harness,
                         placement: Placement) -> Bot:
        name = name.strip()
        bot = Bot.new(name, avatar=avatar, harness=harness, placement=placement)
        base = bot.id
        counter = 2
        while self.bot(bot.id):
            bot.id = agent_name(f"{base}-{counter}")
            counter += 1
        self.bots.append(bot)
        self.rules[bot.id] = default_rules()
        self.write_home(bot)
        self.append(ChatMessage(bot_id=bot.id, role=MessageRole.BOT,
                                text=f"Hi, I'm {bot.name}. I'm setting up my computer; "
                                     "I'll say hello when I'm ready."))
        self.save()
        self.emit()
        asyncio.create_task(self.bring_up(bot.id, self.intro_prompt(bot)))
        return self.bot(bot.id) or bot

    @staticmethod
    def intro_prompt(bot: Bot) -> str:
        return (
            f"You were just created. Introduce yourself to {bot.owner} in two short sentences as "
            f"{bot.name}: say you have your own computer, you'll keep working when they're away, and "
            "you'll check in when something needs their approval. Then start your memory file with "
            "one line about today."
        )

    async def bring_up(self, bot_id: str, first_prompt: str) -> None:
        bot = self.bot(bot_id)
        if not bot:
            return
        if not self.engine:
            self.fail(bot_id, "Cua isn't available. Start Docker and the Cua runtime, then restart the app.")
            return
        try:
            self.update(bot_id, lambda b: (setattr(b, "status", "Setting up"),
                                           setattr(b, "mood", BotMood.WORKING)))
            if not bot.space_id and not self.engine.model.demo:
                space_id = await self.engine.provision(
                    bot, lambda _phase, text: self.set_setup(bot_id, text))
                self.update(bot_id, lambda b: setattr(b, "space_id", space_id))
                bot = self.bot(bot_id) or bot
            self.set_setup(bot_id, f"Starting {bot.harness.display_name}")
            run_id = await self.engine.start(bot, self.volume, first_prompt)
            self.update(bot_id, lambda b: (setattr(b, "run_id", run_id),
                                           setattr(b, "status", "Thinking"),
                                           setattr(b, "mood", BotMood.THINKING)))
            self.set_setup(bot_id, None)
            self.busy.add(bot_id)
            self.start_polling(bot_id)
        except Exception as exc:  # noqa: BLE001 - surfaced in the conversation
            self.set_setup(bot_id, None)
            self.fail(bot_id, f"Couldn't set up {bot.name}'s computer: {exc}")
        self.save()
        self.emit()

    def set_setup(self, bot_id: str, text: Optional[str]) -> None:
        if text:
            self.setup_phase[bot_id] = text
        else:
            self.setup_phase.pop(bot_id, None)
        self.emit()

    def reconnect(self) -> None:
        for bot in self.bots:
            if bot.run_id and not bot.is_paused:
                self.start_polling(bot.id)

    # -- Customizing ------------------------------------------------------

    def update_avatar(self, bot_id: str, avatar: AvatarConfig) -> None:
        self.update(bot_id, lambda b: setattr(b, "avatar", avatar))
        if bot := self.bot(bot_id):
            self.write_home(bot)
        self.save()
        self.emit()

    def rename(self, bot_id: str, name: str) -> None:
        name = name.strip()
        if not name:
            return
        self.update(bot_id, lambda b: setattr(b, "name", name))
        if bot := self.bot(bot_id):
            self.write_home(bot)
        self.save()
        self.emit()

    def set_rules(self, bot_id: str, rules: list[CustomRule]) -> None:
        locked = [r for r in default_rules() if r.locked]
        self.rules[bot_id] = locked + [r for r in rules if not r.locked]
        if bot := self.bot(bot_id):
            self.write_home(bot)
        self.emit()

    def set_host_access(self, bot_id: str, access: dict[str, Any]) -> None:
        self.update(bot_id, lambda b: setattr(b, "host_access", access))
        self.save()
        self.emit()

    # -- Talking ----------------------------------------------------------

    async def send(self, bot_id: str, text: str) -> None:
        text = text.strip()
        bot = self.bot(bot_id)
        if not text or not bot:
            return
        self.append(ChatMessage(bot_id=bot_id, role=MessageRole.USER, text=text))
        self.emit()
        if bot.is_paused:
            self.append(ChatMessage(bot_id=bot_id, role=MessageRole.SYSTEM,
                                    text=f"{bot.name} is paused. Resume to continue.",
                                    kind={"type": "notice"}))
            self.emit()
            return
        await self.deliver(bot_id, text)

    async def deliver(self, bot_id: str, text: str) -> None:
        bot = self.bot(bot_id)
        if not bot:
            return
        if not self.engine:
            self.fail(bot_id, "Cua isn't available. Start Docker and the Cua runtime, then restart the app.")
            return
        try:
            if not bot.run_id:
                asyncio.create_task(self.bring_up(bot_id, text))
                return
            if self._is_demo(bot.run_id):
                self.engine.demo_send(bot, bot.run_id, text)
            else:
                await self.engine.push(bot, self.volume)
                await self.engine.send(bot, text)
            self.busy.add(bot_id)
            self.update(bot_id, lambda b: (setattr(b, "mood", BotMood.THINKING),
                                           setattr(b, "status", "Thinking")))
            self.start_polling(bot_id)
        except Exception as exc:  # noqa: BLE001
            self.fail(bot_id, f"Couldn't reach {bot.name}: {exc}")
        self.save()
        self.emit()

    # -- Approvals --------------------------------------------------------

    async def decide(self, approval_id: str, approve: bool) -> None:
        approval = self.approval(approval_id)
        if not approval or approval.state is not ApprovalState.PENDING:
            return
        approval.decided_at = utcnow()
        bot_id = approval.bot_id
        if not approve:
            approval.state = ApprovalState.DENIED
            self.refresh_mood(bot_id)
            self.emit()
            await self.deliver(bot_id, f"Denied: {approval.action}. Don't do it; tell me what you'll do instead.")
            self.save()
            return
        source = approval.source or {}
        if source.get("kind") == "login":
            site = source.get("site", "the site")
            approval.state = ApprovalState.APPROVED
            self.refresh_mood(bot_id)
            self.emit()
            await self.deliver(bot_id, f"Signed in to {site} (you took over the computer). Continue.")
        elif source.get("kind") == "handoff":
            approval.state = ApprovalState.HANDED_OFF
            self.refresh_mood(bot_id)
            self.emit()
            await self.deliver(bot_id, f"I did it myself: {approval.action}. Carry on from there.")
        else:
            approval.state = ApprovalState.APPROVED
            self.refresh_mood(bot_id)
            self.emit()
            await self.deliver(bot_id, f"Approved: {approval.action}. Go ahead, only this once.")
        self.save()
        self.emit()

    async def sign_in_manual(self, approval_id: str) -> None:
        """The user signed in by taking over the computer."""
        approval = self.approval(approval_id)
        if not approval:
            return
        approval.state = ApprovalState.APPROVED
        approval.decided_at = utcnow()
        site = (approval.source or {}).get("site", "the site")
        self.refresh_mood(approval.bot_id)
        self.emit()
        await self.deliver(approval.bot_id, f"Signed in to {site} (you took over the computer). Continue.")
        self.save()
        self.emit()

    # -- Pause, resume, reset --------------------------------------------

    async def restart(self, bot_id: str) -> None:
        """Stop the current run and start a fresh one in the same Space."""
        bot = self.bot(bot_id)
        if not bot:
            return
        poller = self._pollers.pop(bot_id, None)
        if poller:
            poller.cancel()
        if self.engine:
            try:
                await self.engine.stop(bot)
            except Exception:
                pass
        self.busy.discard(bot_id)
        self._cursors[bot_id] = 0
        self._turn_text.pop(bot_id, None)
        self.update(bot_id, lambda b: (setattr(b, "run_id", None),
                                       setattr(b, "status", "Setting up"),
                                       setattr(b, "mood", BotMood.WORKING)))
        self.save()
        self.emit()
        await self.bring_up(bot_id, "You were restarted. Say hello and continue where you left off.")

    async def pause(self, bot_id: str) -> None:
        bot = self.bot(bot_id)
        if not bot or bot.is_paused:
            return
        self.update(bot_id, lambda b: (setattr(b, "is_paused", True),
                                       setattr(b, "mood", BotMood.PAUSED),
                                       setattr(b, "status", "Paused")))
        poller = self._pollers.pop(bot_id, None)
        if poller:
            poller.cancel()
        self.busy.discard(bot_id)
        for task in self.tasks_for(bot_id):
            if task.schedule and task.state is TaskState.SCHEDULED:
                task.state = TaskState.PAUSED
        self.persist_tasks(bot_id)
        if self.engine:
            try:
                await self.engine.pause(bot)
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
        self.save()
        self.emit()

    async def resume(self, bot_id: str) -> None:
        bot = self.bot(bot_id)
        if not bot or not bot.is_paused:
            return
        if self.engine:
            try:
                await self.engine.resume(bot)
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
        self.update(bot_id, lambda b: (setattr(b, "is_paused", False),
                                       setattr(b, "mood", BotMood.IDLE),
                                       setattr(b, "status", "Ready")))
        for task in self.tasks_for(bot_id):
            if task.state is TaskState.PAUSED:
                task.state = TaskState.SCHEDULED
        self.persist_tasks(bot_id)
        self.start_polling(bot_id)
        self.save()
        self.emit()

    async def reset(self, bot_id: str) -> None:
        bot = self.bot(bot_id)
        if not bot:
            return
        poller = self._pollers.pop(bot_id, None)
        if poller:
            poller.cancel()
        if self.engine:
            try:
                await self.engine.reset(bot)
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
        self.volume.delete(VolumeLayout.home(bot_id))
        self.bots = [b for b in self.bots if b.id != bot_id]
        self.messages.pop(bot_id, None)
        self.tasks.pop(bot_id, None)
        self.rules.pop(bot_id, None)
        self.approvals = [a for a in self.approvals if a.bot_id != bot_id]
        self.notifications = [n for n in self.notifications if n.bot_id != bot_id]
        self.busy.discard(bot_id)
        self.save()
        self.emit()

    # -- Scheduled work ---------------------------------------------------

    def schedule(self, bot_id: str, title: str, prompt: str, schedule: TaskSchedule,
                 symbol: str = "clock", notify: bool = True) -> BotTask:
        bot = self.bot(bot_id)
        task = BotTask(
            bot_id=bot_id, title=title, prompt=prompt, symbol=symbol,
            state=TaskState.PAUSED if bot and bot.is_paused else TaskState.SCHEDULED,
            schedule=schedule, notify_on_completion=notify,
        )
        self.tasks.setdefault(bot_id, []).append(task)
        self.persist_tasks(bot_id)
        self.emit()
        return task

    def update_task(self, task: BotTask) -> None:
        tasks = self.tasks.setdefault(task.bot_id, [])
        for index, existing in enumerate(tasks):
            if existing.id == task.id:
                tasks[index] = task
                break
        self.persist_tasks(task.bot_id)
        self.emit()

    def delete_task(self, bot_id: str, task_id: str) -> None:
        self.tasks[bot_id] = [t for t in self.tasks_for(bot_id) if t.id != task_id]
        self.persist_tasks(bot_id)
        self.emit()

    async def fire(self, task_id: str, bot_id: str) -> bool:
        bot = self.bot(bot_id)
        task = next((t for t in self.tasks_for(bot_id) if t.id == task_id), None)
        if not bot or bot.is_paused or bot_id in self.busy or not task:
            return False
        now = utcnow()
        task.last_run = now
        task.next_run = task.schedule.next_fire(now) if task.schedule else None
        self._current_task[bot_id] = task_id
        self.append(ChatMessage(bot_id=bot_id, role=MessageRole.SYSTEM,
                                text=f"Scheduled: {task.title}", kind={"type": "notice"}))
        self.persist_tasks(bot_id)
        self.emit()
        await self.deliver(bot_id, f"[routine] {task.title}: {task.prompt}")
        return True

    # -- Notifications ----------------------------------------------------

    def mark_read(self, notification_id: str) -> None:
        for notification in self.notifications:
            if notification.id == notification_id:
                notification.read = True
        self.save()
        self.emit()

    def mark_all_read(self, bot_id: str) -> None:
        now = utcnow()
        for notification in self.notifications:
            if notification.bot_id == bot_id:
                notification.read = True
        for message in self.messages_for(bot_id):
            if message.read_at is None:
                message.read_at = now
        self.save()
        self.emit()

    # -- Run loop ---------------------------------------------------------

    def _is_demo(self, run_id: Optional[str]) -> bool:
        return bool(run_id and run_id.startswith("demo-"))

    def start_polling(self, bot_id: str) -> None:
        if bot_id in self._pollers:
            return
        self._pollers[bot_id] = asyncio.create_task(self._poll_loop(bot_id))

    async def _poll_loop(self, bot_id: str) -> None:
        try:
            while True:
                idle = await self.poll_once(bot_id)
                await asyncio.sleep(2.5 if idle else 0.7)
        except asyncio.CancelledError:
            return

    async def poll_once(self, bot_id: str) -> bool:
        bot = self.bot(bot_id)
        if not self.engine or not bot or not bot.run_id:
            return True
        try:
            if self._is_demo(bot.run_id):
                updates, cursor = self.engine.demo_events(bot.run_id, self._cursors.get(bot_id, 0))
            else:
                updates, cursor = await self.engine.poll(bot, self._cursors.get(bot_id, 0))
            self._cursors[bot_id] = cursor
            for update in updates:
                self.handle(bot_id, update)
        except Exception:
            # A poll that fails once is not news; the next one retries.
            pass
        return bot_id not in self.busy

    def handle(self, bot_id: str, update: EngineUpdate) -> None:
        if update.kind == "assistant":
            previous_turn, previous_text = self._turn_text.get(bot_id, (update.turn, ""))
            if previous_turn != update.turn:
                previous_text = ""
            text = update.text if update.text.startswith(previous_text) else previous_text + update.text
            self._turn_text[bot_id] = (update.turn, text)
            for directive in parse_directives(text)["directives"]:
                if directive["kind"] == "status":
                    self.update(bot_id, lambda b: setattr(b, "status", directive["value"]))
            self.emit()
        elif update.kind == "tool":
            title = (update.title or "").strip()
            if title:
                self.update(bot_id, lambda b: (setattr(b, "status", title[:40]),
                                               setattr(b, "mood", BotMood.WORKING)))
            self.emit()
        elif update.kind == "setup":
            self.set_setup(bot_id, update.text)
        elif update.kind == "turn_ended":
            self.busy.discard(bot_id)
            turn, text = self._turn_text.get(bot_id, (update.turn, ""))
            self._turn_text.pop(bot_id, None)
            self.finish_turn(bot_id, text if turn == update.turn else "")
            if bot := self.bot(bot_id):
                if self.engine and not self._is_demo(bot.run_id):
                    asyncio.create_task(self._checkpoint(bot))
            self.emit()
        elif update.kind == "failed":
            self.busy.discard(bot_id)
            self.fail(bot_id, update.text or "The agent reported an error")
            self.emit()

    async def _checkpoint(self, bot: Bot) -> None:
        if not self.engine:
            return
        try:
            await self.engine.checkpoint(bot, self.volume)
        except Exception:
            pass

    def finish_turn(self, bot_id: str, raw: str) -> None:
        bot = self.bot(bot_id)
        if not bot:
            return
        parsed = parse_directives(raw)
        status: Optional[str] = None
        outputs: list[str] = []
        done_title: Optional[str] = None
        cards: list[ChatMessage] = []

        for directive in parsed["directives"]:
            kind = directive["kind"]
            if kind == "status":
                status = directive["value"]
            elif kind == "step":
                self.touch_task(bot_id, directive["value"],
                                lambda task, value=directive["value"]: task.steps.append(TaskStep(value))
                                if not any(s.title == value for s in task.steps) else None)
            elif kind == "step_done":
                def mark_done(task: BotTask, value: str = directive["value"]) -> None:
                    for step in task.steps:
                        if step.title == value:
                            step.done = True
                            break
                    else:
                        task.steps.append(TaskStep(value, done=True))
                self.touch_task(bot_id, directive["value"], mark_done)
            elif kind == "ask":
                action, detail = directive["action"], directive["detail"]
                decision = RuleEngine.decide(action, self.rules_for(bot_id))
                source = ({"kind": "handoff"} if decision.behavior.value == "hand-off"
                          else {"kind": "rule", "rule_id": decision.rule.id if decision.rule else None})
                approval = ApprovalRequest(bot_id=bot_id, action=action, detail=detail, source=source)
                self.approvals.append(approval)
                cards.append(ChatMessage(bot_id=bot_id, role=MessageRole.BOT, text=action,
                                         kind={"type": "approval", "id": approval.id}))
                self.notify(bot, "approval", f"{bot.name} needs your approval", action)
            elif kind == "handoff":
                action = directive["action"]
                approval = ApprovalRequest(bot_id=bot_id, action=action,
                                           source={"kind": "handoff"})
                self.approvals.append(approval)
                cards.append(ChatMessage(bot_id=bot_id, role=MessageRole.BOT, text=action,
                                         kind={"type": "approval", "id": approval.id}))
                self.notify(bot, "approval", f"{bot.name} needs you to take over", action)
            elif kind == "login":
                site = directive["site"]
                approval = ApprovalRequest(
                    bot_id=bot_id, action=f"Sign in to {site}",
                    detail=f"Take over {bot.name}'s computer and sign in yourself. {bot.name} never sees the password.",
                    source={"kind": "login", "site": site},
                )
                self.approvals.append(approval)
                cards.append(ChatMessage(bot_id=bot_id, role=MessageRole.BOT, text=site,
                                         kind={"type": "login", "site": site, "approval_id": approval.id}))
                self.notify(bot, "approval", f"{bot.name} needs to sign in", site)
            elif kind == "notify":
                self.notify(bot, "result", directive["title"], directive["body"])
            elif kind == "output":
                path = directive["path"]
                key = path if path.startswith("agents/") else VolumeLayout.home(bot_id) + path
                outputs.append(key)
                if self.engine and self.engine.model.demo and self.volume.read(key) is None:
                    self.volume.write_text(key, f"# {bot.name}'s output\n\nScripted demo output for {key}.\n")
            elif kind == "done":
                done_title = directive["title"]
            elif kind == "schedule":
                schedule = TaskSchedule.from_dict(directive["schedule"])
                if schedule:
                    task = self.schedule(bot_id, directive["title"], directive["prompt"], schedule)
                    next_run = task.next_run.strftime("%b %-d, %-I:%M %p") if task.next_run else ""
                    self.append(ChatMessage(
                        bot_id=bot_id, role=MessageRole.SYSTEM,
                        text=f"Scheduled {task.title} · {schedule.label}" + (f", next {next_run}" if next_run else ""),
                        kind={"type": "notice"},
                    ))

        if parsed["text"]:
            self.append(ChatMessage(bot_id=bot_id, role=MessageRole.BOT, text=parsed["text"]))
        if outputs or done_title:
            def add_outputs(task: BotTask) -> None:
                for path in outputs:
                    if path not in task.outputs:
                        task.outputs.append(path)
            self.touch_task(bot_id, done_title, add_outputs)
            if done_title:
                current_id = self._current_task.get(bot_id)
                for task in self.tasks_for(bot_id):
                    if task.id == current_id:
                        task.title = done_title
                self.complete_task(bot_id)
                self.append(ChatMessage(bot_id=bot_id, role=MessageRole.BOT, text=done_title,
                                        kind={"type": "result", "title": done_title, "outputs": outputs}))
        for card in cards:
            self.append(card)
        self.update(bot_id, lambda b: setattr(
            b, "status",
            status or ("Ready" if not self.pending_approvals(bot_id) else "Waiting for you")))
        self.refresh_mood(bot_id, just_finished=done_title is not None)
        self.save()
        self.emit()

    def refresh_mood(self, bot_id: str, just_finished: bool = False) -> None:
        bot = self.bot(bot_id)
        if not bot:
            return
        if bot.is_paused:
            mood = BotMood.PAUSED
        elif self.pending_approvals(bot_id):
            mood = BotMood.NEEDS_APPROVAL
        elif bot_id in self.busy:
            mood = BotMood.THINKING
        elif just_finished:
            mood = BotMood.DONE
        else:
            mood = BotMood.IDLE
        self.update(bot_id, lambda b: setattr(b, "mood", mood))

    def notify(self, bot: Bot, kind: str, title: str, body: str) -> None:
        notification = BotNotification(bot_id=bot.id, kind=kind, title=title, body=body)
        self.notifications.insert(0, notification)
        self.toast(notification)

    def fail(self, bot_id: str, reason: str) -> None:
        self.update(bot_id, lambda b: (setattr(b, "mood", BotMood.ERROR),
                                       setattr(b, "status", "Needs a look")))
        self.append(ChatMessage(bot_id=bot_id, role=MessageRole.SYSTEM, text=reason,
                                kind={"type": "notice"}))
        if bot := self.bot(bot_id):
            self.notify(bot, "problem", f"{bot.name} hit a problem", reason)
        current = self._current_task.get(bot_id)
        if current:
            for task in self.tasks_for(bot_id):
                if task.id == current and not task.schedule:
                    task.state = TaskState.FAILED
            self.persist_tasks(bot_id)
        self.save()
        self.emit()

    # -- Tasks from the conversation -------------------------------------

    def touch_task(self, bot_id: str, title: Optional[str],
                   change: Callable[[BotTask], None]) -> None:
        tasks = self.tasks.setdefault(bot_id, [])
        current_id = self._current_task.get(bot_id)
        existing = next((t for t in tasks if t.id == current_id), None) if current_id else None
        if existing:
            change(existing)
        else:
            last_ask = next((m.text for m in reversed(self.messages_for(bot_id))
                             if m.role is MessageRole.USER), "Task")
            task = BotTask(bot_id=bot_id, title=title or self.title_from(last_ask),
                           prompt=last_ask, symbol="circle.dashed")
            change(task)
            tasks.insert(0, task)
            self._current_task[bot_id] = task.id
        self.persist_tasks(bot_id)

    def complete_task(self, bot_id: str) -> None:
        task_id = self._current_task.get(bot_id)
        if not task_id:
            return
        for task in self.tasks_for(bot_id):
            if task.id == task_id:
                task.last_run = utcnow()
                if not task.schedule:
                    task.state = TaskState.COMPLETED
                    task.symbol = "checkmark.circle"
                    for step in task.steps:
                        step.done = True
        self._current_task.pop(bot_id, None)
        self.persist_tasks(bot_id)

    @staticmethod
    def title_from(text: str) -> str:
        words = text.replace("\n", " ").split()
        head = " ".join(words[:7])
        return head + "…" if len(words) > 7 else head

    def persist_tasks(self, bot_id: str) -> None:
        self.volume.write_json(VolumeLayout.tasks(bot_id),
                               [task.to_dict() for task in self.tasks_for(bot_id)])

    # -- Persistence ------------------------------------------------------

    def write_home(self, bot: Bot) -> None:
        rules = self.rules_for(bot.id)
        self.volume.write_json(VolumeLayout.identity(bot.id), bot.to_dict())
        self.volume.write_json(f"agents/{bot.id}/identity/rules.json",
                               [rule.to_dict() for rule in rules])
        self.volume.write_text(VolumeLayout.rules(bot.id), RuleEngine.yaml(rules))
        self.volume.write_text(VolumeLayout.instructions(bot.id, bot.harness),
                               render_instructions(bot, rules))
        if self.volume.read(VolumeLayout.memory(bot.id)) is None:
            self.volume.write_text(VolumeLayout.memory(bot.id), f"# What {bot.name} remembers\n")

    @property
    def state_path(self) -> Path:
        return self.data_directory / "state.json"

    def save(self) -> None:
        payload = {
            "messages": {key: [m.to_dict() for m in value] for key, value in self.messages.items()},
            "approvals": [a.to_dict() for a in self.approvals],
            "notifications": [n.to_dict() for n in self.notifications],
            "bots": [b.to_dict() for b in self.bots],
        }
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        os.replace(temp, self.state_path)
        for bot in self.bots:
            self.write_home(bot)

    def load(self) -> None:
        runtime: dict[str, Bot] = {}
        if self.state_path.exists():
            try:
                saved = json.loads(self.state_path.read_text())
                for key, value in (saved.get("messages") or {}).items():
                    self.messages[key] = [ChatMessage.from_dict(m) for m in value]
                self.approvals = [ApprovalRequest.from_dict(a) for a in saved.get("approvals", [])]
                self.notifications = [BotNotification.from_dict(n) for n in saved.get("notifications", [])]
                for item in saved.get("bots", []):
                    bot = Bot.from_dict(item)
                    runtime[bot.id] = bot
            except Exception:
                pass
        homes = self.volume.ls("agents/")
        bots: list[Bot] = []
        for entry in homes:
            if not entry.is_folder:
                continue
            bot_id = entry.name
            data = self.volume.read_json(VolumeLayout.identity(bot_id))
            if not isinstance(data, dict):
                continue
            try:
                bot = Bot.from_dict(data)
            except Exception:
                continue
            if live := runtime.get(bot.id):
                bot.run_id = live.run_id or bot.run_id
                bot.space_id = live.space_id or bot.space_id
            bots.append(bot)
        self.bots = sorted(bots, key=lambda b: b.created_at)
        for bot in self.bots:
            rules = self.volume.read_json(f"agents/{bot.id}/identity/rules.json")
            self.rules[bot.id] = ([CustomRule.from_dict(r) for r in rules]
                                  if isinstance(rules, list) else default_rules())
            tasks = self.volume.read_json(VolumeLayout.tasks(bot.id))
            self.tasks[bot.id] = ([BotTask.from_dict(t) for t in tasks]
                                  if isinstance(tasks, list) else [])
            # Rewrite the generated home files so an app update refreshes the
            # instructions and rules the harness reads. Memory is untouched.
            self.write_home(bot)

    # -- Mutation helpers -------------------------------------------------

    def update(self, bot_id: str, change: Callable[[Bot], Any]) -> None:
        for bot in self.bots:
            if bot.id == bot_id:
                change(bot)
                return

    def append(self, message: ChatMessage) -> None:
        self.messages.setdefault(message.bot_id, []).append(message)
