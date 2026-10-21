"""The small marker protocol a bot uses in its replies.

Ported from ``CuaBotsCore/Model/Directives.swift``: the app strips the markers
from the text and turns them into status, steps, approvals, notifications,
outputs and routines.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from .models import Bot, TaskSchedule
from .rules import CustomRule, RuleEngine


def parse(raw: str) -> dict[str, Any]:
    directives: list[dict[str, Any]] = []
    lines: list[str] = []
    for line in raw.split("\n"):
        text, found = strip(line)
        directives.extend(found)
        if found and not text.strip():
            continue
        lines.append(text)
    return {"text": tidy("\n".join(lines)), "directives": directives}


def strip(line: str) -> tuple[str, list[dict[str, Any]]]:
    directives: list[dict[str, Any]] = []
    text = ""
    rest = line
    while True:
        open_at = rest.find("[[")
        if open_at < 0:
            text += rest
            break
        text += rest[:open_at]
        close_at = rest.find("]]", open_at + 2)
        if close_at < 0:
            text += rest[open_at:]
            break
        body = rest[open_at + 2:close_at]
        directive = parse_directive(body)
        if directive is not None:
            directives.append(directive)
        else:
            text += rest[open_at:close_at + 2]
        rest = rest[close_at + 2:]
    return text, directives


def parse_directive(body: str) -> Optional[dict[str, Any]]:
    colon = body.find(":")
    if colon < 0:
        return None
    key = body[:colon].strip().lower()
    value = body[colon + 1:].strip()
    if key == "schedule":
        parts = [p.strip() for p in value.split("|", 2)]
        if len(parts) < 2:
            return None
        schedule = parse_schedule(parts[0])
        if schedule is None:
            return None
        return {"kind": "schedule", "schedule": schedule.to_dict(),
                "title": parts[1], "prompt": parts[2] if len(parts) > 2 else parts[1]}
    parts = [p.strip() for p in value.split("|", 1)]
    first = parts[0] if parts else ""
    second = parts[1] if len(parts) > 1 else ""
    if not first:
        return None
    if key == "status":
        return {"kind": "status", "value": first}
    if key == "step":
        return {"kind": "step", "value": first}
    if key in ("step-done", "stepdone", "done-step"):
        return {"kind": "step_done", "value": first}
    if key in ("ask", "approve"):
        return {"kind": "ask", "action": first, "detail": second}
    if key in ("handoff", "hand-off"):
        return {"kind": "handoff", "action": first}
    if key in ("login", "log-in", "signin"):
        return {"kind": "login", "site": first}
    if key == "notify":
        return {"kind": "notify", "title": first, "body": second}
    if key == "output":
        return {"kind": "output", "path": first}
    if key == "done":
        return {"kind": "done", "title": first}
    return None


def parse_schedule(spec: str) -> Optional[TaskSchedule]:
    words = spec.lower().split()
    if not words:
        return None

    def clock(value: str) -> Optional[tuple[int, int]]:
        parts = value.split(":")
        if len(parts) != 2:
            return None
        try:
            hour, minute = int(parts[0]), int(parts[1])
        except ValueError:
            return None
        if not (0 <= hour < 24 and 0 <= minute < 60):
            return None
        return hour, minute

    head = words[0]
    if head == "daily":
        if len(words) < 2 or clock(words[1]) is None:
            return None
        hour, minute = clock(words[1])
        return TaskSchedule("daily", hour=hour, minute=minute)
    if head == "weekly":
        days = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
        if len(words) < 3:
            return None
        day = next((i for i, name in enumerate(days) if words[1].startswith(name)), None)
        if day is None or clock(words[2]) is None:
            return None
        hour, minute = clock(words[2])
        return TaskSchedule("weekly", weekday=day + 1, hour=hour, minute=minute)
    if head == "every":
        if len(words) < 2:
            return None
        digits = re.sub(r"\D", "", words[1])
        if not digits:
            return None
        value = int(digits)
        if value <= 0:
            return None
        return TaskSchedule("every", minutes=value * 60 if words[1].endswith("h") else value)
    return None


def tidy(value: str) -> str:
    lines = [line.strip() for line in value.split("\n")]
    out: list[str] = []
    for line in lines:
        if not line and (not out or not out[-1]):
            continue
        out.append(line)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def render_instructions(bot: Bot, rules: list[CustomRule], memory_path: str = "memory/MEMORY.md") -> str:
    return f"""# You are {bot.name}

You are {bot.owner}'s bot: a persistent assistant that works on its own computer (this machine) and keeps working between conversations. Your handle is {bot.handle}. Be brief and concrete. Reply with the final answer only: do not narrate your reasoning or describe what you are about to do.

## Memory

Your memory lives in `{memory_path}` next to this file. Read it at the start of every conversation. When you learn something about {bot.owner}, their goals, preferences or standards, add one line to it. Never write passwords, tokens or keys into memory: sign-ins go through the user's Keyvault.

Put finished work in `outputs/`. Files the user hands you arrive in `inbox/`.

## Talking to the app

Put these markers on their own lines; the app shows them as status, steps, cards and notifications, and hides the markers:

- `[[status: <3 words>]]` what you are doing now ("Checking inbox")
- `[[step: <step>]]` a step you are starting, `[[step-done: <step>]]` when it is done
- `[[ask: <action> | <details>]]` before any action your rules say to ask about
- `[[handoff: <action>]]` when the user must do it themselves
- `[[login: <site>]]` when you need to be signed in to a site; wait for "Signed in"
- `[[output: outputs/<file>]]` for each file you finish
- `[[notify: <title> | <one line>]]` when something finished or needs the user
- `[[done: <task title>]]` when a task is complete
- `[[schedule: daily 09:00 | <title> | <what to do each time>]]` when asked to do something on a schedule (also `weekly mon 08:30`, `every 30m`); the app runs it for you

{RuleEngine.instructions(rules)}
"""
