"""Data model for the Linux port of Cua Bots.

This mirrors ``examples/cua-bots-macos/Sources/CuaBotsCore/Model`` closely so
the two apps keep the same behaviour and the same Volume layout.
"""
from __future__ import annotations

import getpass
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional


# --------------------------------------------------------------------------
# Time helpers
# --------------------------------------------------------------------------

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.astimezone()
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def from_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def new_id() -> str:
    return uuid.uuid4().hex


# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------

class Harness(str, Enum):
    HERMES = "hermes"
    OPENCLAW = "openclaw"
    CODEX = "openai-codex"
    CLAUDE_CODE = "claude-code"

    @property
    def display_name(self) -> str:
        return {
            Harness.HERMES: "Hermes",
            Harness.OPENCLAW: "OpenClaw",
            Harness.CODEX: "Codex",
            Harness.CLAUDE_CODE: "Claude Code",
        }[self]

    @property
    def blurb(self) -> str:
        return {
            Harness.HERMES: "A persistent assistant with its own memory",
            Harness.OPENCLAW: "A persistent assistant with standing orders",
            Harness.CODEX: "A coding agent",
            Harness.CLAUDE_CODE: "A coding agent",
        }[self]

    @property
    def instructions_file(self) -> str:
        return {
            Harness.CLAUDE_CODE: "CLAUDE.md",
            Harness.HERMES: "SOUL.md",
            Harness.OPENCLAW: "AGENTS.md",
            Harness.CODEX: "AGENTS.md",
        }[self]

    @property
    def key_vars(self) -> list[str]:
        if self is Harness.CLAUDE_CODE:
            return ["ANTHROPIC_API_KEY"]
        if self is Harness.CODEX:
            return ["OPENAI_API_KEY"]
        return ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"]

    @property
    def wire(self) -> str:
        if self is Harness.CLAUDE_CODE:
            return "anthropic"
        if self is Harness.CODEX:
            return "openai-responses"
        return "openai-chat"


class Placement(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"

    @property
    def display_name(self) -> str:
        return "This computer" if self is Placement.LOCAL else "Cua Cloud"


class BotColor(str, Enum):
    CLOUD = "cloud"
    VIOLET = "violet"
    ORANGE = "orange"
    SKY = "sky"
    GRAPHITE = "graphite"
    SLATE = "slate"

    @property
    def display_name(self) -> str:
        return self.value.capitalize()

    @property
    def face(self) -> str:
        return {
            BotColor.CLOUD: "#E3E7EC",
            BotColor.VIOLET: "#8B5CF6",
            BotColor.ORANGE: "#FF7A2F",
            BotColor.SKY: "#61BCFF",
            BotColor.GRAPHITE: "#262A31",
            BotColor.SLATE: "#8E98A3",
        }[self]

    @property
    def nose(self) -> str:
        return {
            BotColor.CLOUD: "#7D8793",
            BotColor.VIOLET: "#5B2FC9",
            BotColor.ORANGE: "#C24E10",
            BotColor.SKY: "#2A7FC4",
            BotColor.GRAPHITE: "#4B525E",
            BotColor.SLATE: "#5B6571",
        }[self]

    @property
    def eye(self) -> str:
        return "#F3F6FA" if self is BotColor.GRAPHITE else "#0B0E13"

    @property
    def accent(self) -> str:
        if self is BotColor.CLOUD:
            return "#61BCFF"
        if self is BotColor.GRAPHITE:
            return "#8E98A3"
        return self.face

    @staticmethod
    def default_for(name: str) -> "BotColor":
        palette = [BotColor.VIOLET, BotColor.ORANGE, BotColor.SKY,
                   BotColor.CLOUD, BotColor.SLATE, BotColor.GRAPHITE]
        total = sum(ord(ch) for ch in name)
        return palette[total % len(palette)]


class EyeStyle(str, Enum):
    STAR = "star"
    ROUND = "round"
    HAPPY = "happy"
    CALM = "calm"
    PLUS = "plus"
    DELIGHT = "delight"

    @property
    def display_name(self) -> str:
        return self.value.capitalize()


class EarShape(str, Enum):
    SCALLOPED = "scalloped"
    ROUND = "round"
    SMALL = "small"

    @property
    def display_name(self) -> str:
        return self.value.capitalize()


class BotMood(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    WORKING = "working"
    NEEDS_APPROVAL = "needsApproval"
    DONE = "done"
    PAUSED = "paused"
    ERROR = "error"

    @property
    def animated(self) -> bool:
        return self in (BotMood.IDLE, BotMood.THINKING, BotMood.WORKING)


class MessageRole(str, Enum):
    USER = "user"
    BOT = "bot"
    SYSTEM = "system"


class TaskState(str, Enum):
    IN_PROGRESS = "inProgress"
    SCHEDULED = "scheduled"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def title(self) -> str:
        return {
            TaskState.IN_PROGRESS: "In progress",
            TaskState.SCHEDULED: "Scheduled",
            TaskState.PAUSED: "Paused",
            TaskState.COMPLETED: "Completed",
            TaskState.FAILED: "Needs a look",
        }[self]


class ApprovalState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    HANDED_OFF = "handedOff"


# --------------------------------------------------------------------------
# Avatar
# --------------------------------------------------------------------------

@dataclass
class AvatarConfig:
    color: BotColor = BotColor.SKY
    eyes: EyeStyle = EyeStyle.STAR
    ears: EarShape = EarShape.SCALLOPED

    @staticmethod
    def default_for(name: str) -> "AvatarConfig":
        return AvatarConfig(color=BotColor.default_for(name))

    def to_dict(self) -> dict[str, Any]:
        return {"color": self.color.value, "eyes": self.eyes.value, "ears": self.ears.value}

    @staticmethod
    def from_dict(data: Optional[dict[str, Any]]) -> "AvatarConfig":
        data = data or {}
        try:
            color = BotColor(data.get("color", "sky"))
        except ValueError:
            color = BotColor.SKY
        try:
            eyes = EyeStyle(data.get("eyes", "star"))
        except ValueError:
            eyes = EyeStyle.STAR
        try:
            ears = EarShape(data.get("ears", "scalloped"))
        except ValueError:
            ears = EarShape.SCALLOPED
        return AvatarConfig(color, eyes, ears)


# --------------------------------------------------------------------------
# Bot
# --------------------------------------------------------------------------

_AGENT_NAME_RE = re.compile(r"[^a-z0-9._-]")


def agent_name(name: str) -> str:
    mapped = _AGENT_NAME_RE.sub("-", name.lower())
    while "--" in mapped:
        mapped = mapped.replace("--", "-")
    mapped = mapped.strip("-._")
    return (mapped or "bot")[:63]


@dataclass
class Bot:
    id: str
    name: str
    owner: str
    avatar: AvatarConfig
    harness: Harness = Harness.HERMES
    placement: Placement = Placement.LOCAL
    space_id: Optional[str] = None
    run_id: Optional[str] = None
    created_at: datetime = field(default_factory=utcnow)
    is_paused: bool = False
    status: str = "Getting set up"
    mood: BotMood = BotMood.IDLE
    host_access: dict[str, Any] = field(default_factory=lambda: {"state": "off"})

    @staticmethod
    def new(name: str, avatar: Optional[AvatarConfig] = None,
            harness: Harness = Harness.HERMES,
            placement: Placement = Placement.LOCAL) -> "Bot":
        return Bot(
            id=agent_name(name),
            name=name,
            owner=os.environ.get("CUA_BOTS_OWNER") or getpass.getuser(),
            avatar=avatar or AvatarConfig.default_for(name),
            harness=harness,
            placement=placement,
        )

    @property
    def handle(self) -> str:
        return f"@{agent_name(self.owner)}-{self.id}"

    @property
    def computer_title(self) -> str:
        return f"{self.name}' computer" if self.name.endswith("s") else f"{self.name}'s computer"

    @property
    def space_name(self) -> str:
        return f"bot-{self.id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "owner": self.owner,
            "avatar": self.avatar.to_dict(),
            "harness": self.harness.value,
            "placement": self.placement.value,
            "space_id": self.space_id,
            "run_id": self.run_id,
            "created_at": iso(self.created_at),
            "is_paused": self.is_paused,
            "status": self.status,
            "mood": self.mood.value,
            "host_access": self.host_access,
            "handle": self.handle,
            "computer_title": self.computer_title,
            "space_name": self.space_name,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Bot":
        return Bot(
            id=data["id"],
            name=data["name"],
            owner=data.get("owner", getpass.getuser()),
            avatar=AvatarConfig.from_dict(data.get("avatar")),
            harness=Harness(data.get("harness", "hermes")),
            placement=Placement(data.get("placement", "local")),
            space_id=data.get("space_id"),
            run_id=data.get("run_id"),
            created_at=from_iso(data.get("created_at")) or utcnow(),
            is_paused=bool(data.get("is_paused")),
            status=data.get("status", "Ready"),
            mood=BotMood(data.get("mood", "idle")),
            host_access=data.get("host_access") or {"state": "off"},
        )


# --------------------------------------------------------------------------
# Conversation
# --------------------------------------------------------------------------

@dataclass
class ChatMessage:
    bot_id: str
    role: MessageRole
    text: str
    kind: dict[str, Any] = field(default_factory=lambda: {"type": "text"})
    id: str = field(default_factory=new_id)
    date: datetime = field(default_factory=utcnow)
    read_at: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "role": self.role.value,
            "text": self.text,
            "kind": self.kind,
            "date": iso(self.date),
            "read_at": iso(self.read_at),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ChatMessage":
        return ChatMessage(
            bot_id=data["bot_id"],
            role=MessageRole(data["role"]),
            text=data.get("text", ""),
            kind=data.get("kind") or {"type": "text"},
            id=data.get("id") or new_id(),
            date=from_iso(data.get("date")) or utcnow(),
            read_at=from_iso(data.get("read_at")),
        )


# --------------------------------------------------------------------------
# Tasks and schedules
# --------------------------------------------------------------------------

def _local_now() -> datetime:
    return datetime.now().astimezone()


@dataclass
class TaskSchedule:
    kind: str  # every | daily | weekly
    minutes: int = 0
    hour: int = 0
    minute: int = 0
    weekday: int = 0  # 1 = Sunday, matching Calendar

    @property
    def label(self) -> str:
        if self.kind == "every":
            return f"Every {self.minutes // 60} h" if self.minutes % 60 == 0 else f"Every {self.minutes} min"
        if self.kind == "daily":
            return "Daily"
        names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        return f"Weekly on {names[(self.weekday - 1) % 7]}"

    def next_fire(self, after: Optional[datetime] = None) -> datetime:
        now = (after or _local_now()).astimezone()
        if self.kind == "every":
            return now + timedelta(minutes=max(self.minutes, 1))
        target = now.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)
        if self.kind == "daily":
            if target <= now:
                target += timedelta(days=1)
            return target
        # weekly: Python weekday() is Monday=0; our weekday is Sunday=1.
        wanted = (self.weekday - 1) % 7  # Sunday=0
        current = (now.weekday() + 1) % 7  # Sunday=0
        delta = (wanted - current) % 7
        target += timedelta(days=delta)
        if target <= now:
            target += timedelta(days=7)
        return target

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind}
        if self.kind == "every":
            out["minutes"] = self.minutes
        else:
            out["hour"] = self.hour
            out["minute"] = self.minute
        if self.kind == "weekly":
            out["weekday"] = self.weekday
        return out

    @staticmethod
    def from_dict(data: Optional[dict[str, Any]]) -> Optional["TaskSchedule"]:
        if not data:
            return None
        kind = data.get("kind")
        if kind == "every":
            return TaskSchedule("every", minutes=max(int(data.get("minutes", 30)), 1))
        if kind == "daily":
            return TaskSchedule("daily", hour=int(data.get("hour", 9)), minute=int(data.get("minute", 0)))
        if kind == "weekly":
            return TaskSchedule("weekly", hour=int(data.get("hour", 9)), minute=int(data.get("minute", 0)),
                                weekday=max(1, min(7, int(data.get("weekday", 2)))))
        return None


@dataclass
class TaskStep:
    title: str
    done: bool = False
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "done": self.done}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "TaskStep":
        return TaskStep(title=data.get("title", ""), done=bool(data.get("done")),
                        id=data.get("id") or new_id())


@dataclass
class BotTask:
    bot_id: str
    title: str
    prompt: str
    symbol: str = "circle.dashed"
    state: TaskState = TaskState.IN_PROGRESS
    schedule: Optional[TaskSchedule] = None
    next_run: Optional[datetime] = None
    last_run: Optional[datetime] = None
    notify_on_completion: bool = True
    steps: list[TaskStep] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utcnow)
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        if self.next_run is None and self.schedule is not None:
            self.next_run = self.schedule.next_fire(self.created_at)

    def subtitle(self, now: Optional[datetime] = None) -> str:
        now = now or _local_now()
        parts: list[str] = []
        if self.next_run:
            parts.append(_relative(self.next_run, now))
        if self.schedule:
            parts.append(self.schedule.label)
        elif self.state is TaskState.IN_PROGRESS:
            done = sum(1 for s in self.steps if s.done)
            parts.append(f"{done} of {len(self.steps)} steps" if self.steps else "Working")
        elif self.state is TaskState.COMPLETED and self.last_run:
            parts.append(_relative(self.last_run, now))
        return " · ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "title": self.title,
            "prompt": self.prompt,
            "symbol": self.symbol,
            "state": self.state.value,
            "schedule": self.schedule.to_dict() if self.schedule else None,
            "next_run": iso(self.next_run),
            "last_run": iso(self.last_run),
            "notify_on_completion": self.notify_on_completion,
            "steps": [s.to_dict() for s in self.steps],
            "outputs": self.outputs,
            "created_at": iso(self.created_at),
            "subtitle": self.subtitle(),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "BotTask":
        task = BotTask(
            bot_id=data["bot_id"],
            title=data.get("title", ""),
            prompt=data.get("prompt", ""),
            symbol=data.get("symbol", "circle.dashed"),
            state=TaskState(data.get("state", "inProgress")),
            schedule=TaskSchedule.from_dict(data.get("schedule")),
            next_run=from_iso(data.get("next_run")),
            last_run=from_iso(data.get("last_run")),
            notify_on_completion=bool(data.get("notify_on_completion", True)),
            steps=[TaskStep.from_dict(s) for s in data.get("steps", [])],
            outputs=data.get("outputs", []),
            created_at=from_iso(data.get("created_at")) or utcnow(),
            id=data.get("id") or new_id(),
        )
        return task


def _relative(date: datetime, now: datetime) -> str:
    date = date.astimezone()
    now = now.astimezone()
    time = date.strftime("%-I:%M %p")
    if date.date() == now.date():
        return f"Today {time}"
    if (date.date() - now.date()).days == 1:
        return f"Tomorrow {time}"
    if (now.date() - date.date()).days == 1:
        return f"Yesterday {time}"
    return date.strftime("%b %-d, %-I:%M %p")


# --------------------------------------------------------------------------
# Approvals and notifications
# --------------------------------------------------------------------------

@dataclass
class ApprovalRequest:
    bot_id: str
    action: str
    detail: str = ""
    source: dict[str, Any] = field(default_factory=lambda: {"kind": "rule", "rule_id": None})
    state: ApprovalState = ApprovalState.PENDING
    created_at: datetime = field(default_factory=utcnow)
    decided_at: Optional[datetime] = None
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "action": self.action,
            "detail": self.detail,
            "source": self.source,
            "state": self.state.value,
            "created_at": iso(self.created_at),
            "decided_at": iso(self.decided_at),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ApprovalRequest":
        return ApprovalRequest(
            bot_id=data["bot_id"],
            action=data.get("action", ""),
            detail=data.get("detail", ""),
            source=data.get("source") or {"kind": "rule", "rule_id": None},
            state=ApprovalState(data.get("state", "pending")),
            created_at=from_iso(data.get("created_at")) or utcnow(),
            decided_at=from_iso(data.get("decided_at")),
            id=data.get("id") or new_id(),
        )


@dataclass
class BotNotification:
    bot_id: str
    kind: str  # result | approval | update | problem
    title: str
    body: str = ""
    date: datetime = field(default_factory=utcnow)
    read: bool = False
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "date": iso(self.date),
            "read": self.read,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "BotNotification":
        return BotNotification(
            bot_id=data["bot_id"],
            kind=data.get("kind", "update"),
            title=data.get("title", ""),
            body=data.get("body", ""),
            date=from_iso(data.get("date")) or utcnow(),
            read=bool(data.get("read")),
            id=data.get("id") or new_id(),
        )


# --------------------------------------------------------------------------
# JSON helper
# --------------------------------------------------------------------------

def jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return iso(value)
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if hasattr(value, "to_dict"):
        return jsonable(value.to_dict())
    return value
