from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from cua_bots.directives import parse, parse_schedule, render_instructions
from cua_bots.engine import CuaEngine, ModelConfig
from cua_bots.models import (
    AvatarConfig, Bot, BotColor, BotMood, Harness, Placement, TaskSchedule,
    agent_name,
)
from cua_bots.rules import ActionClass, CustomRule, RuleBehavior, RuleEngine, default_rules
from cua_bots.store import BotStore
from cua_bots.volume import LocalVolume, VolumeInvalid, VolumeLayout, VolumeSecret


def test_agent_name_and_bot_fields():
    assert agent_name("Ada Lovelace") == "ada-lovelace"
    assert agent_name("  --Hello, World!!  ") == "hello-world"
    assert agent_name("") == "bot"
    bot = Bot.new("Ada")
    assert bot.id == "ada"
    assert bot.space_name == "bot-ada"
    assert bot.computer_title == "Ada's computer"
    assert bot.handle.startswith("@")
    assert bot.avatar.color in list(BotColor)
    assert Bot.new("Chris").computer_title == "Chris' computer"


def test_harnesses():
    assert len(list(Harness)) == 9
    assert Harness.OPENCODE.value == "opencode"
    assert Harness.GEMINI_CLI.instructions_file == "AGENTS.md"
    assert Harness.CLAUDE_CODE.instructions_file == "CLAUDE.md"
    assert Harness.HERMES.instructions_file == "SOUL.md"
    assert Harness.CODEX.wire == "openai-responses"
    assert Harness.GEMINI_CLI.wire == "gemini"
    assert Harness.PI.wire == "openai-chat"
    assert "GEMINI_API_KEY" in Harness.GEMINI_CLI.key_vars


def test_directive_parser():
    raw = "\n".join([
        "Hi there.",
        "[[status: Checking inbox]]",
        "[[step: Open the sources]]",
        "[[step-done: Open the sources]]",
        "[[ask: Buy the desk | $400, delivered Friday]]",
        "[[handoff: Change the bank password]]",
        "[[login: github.com]]",
        "[[notify: Research ready | Three sources]]",
        "[[output: outputs/summary.md]]",
        "[[done: Research standing desks]]",
        "[[schedule: daily 09:00 | Morning briefing | Summarize overnight mail]]",
        "",
    ])
    parsed = parse(raw)
    assert parsed["text"] == "Hi there."
    kinds = [item["kind"] for item in parsed["directives"]]
    assert kinds == ["status", "step", "step_done", "ask", "handoff", "login",
                     "notify", "output", "done", "schedule"]
    schedule = parsed["directives"][-1]
    assert schedule["schedule"] == {"kind": "daily", "hour": 9, "minute": 0}
    assert schedule["title"] == "Morning briefing"
    assert parse("[[unknown: x]]")["text"] == "[[unknown: x]]"


def test_schedule_parser():
    daily = parse_schedule("daily 09:30")
    assert daily and daily.kind == "daily" and daily.hour == 9 and daily.minute == 30
    weekly = parse_schedule("weekly mon 08:05")
    assert weekly and weekly.kind == "weekly" and weekly.weekday == 2
    every = parse_schedule("every 2h")
    assert every and every.minutes == 120
    assert parse_schedule("every 30m").minutes == 30
    assert parse_schedule("nonsense") is None
    assert parse_schedule("daily 25:00") is None


def test_task_schedule_next_fire():
    now = datetime.now().astimezone().replace(hour=8, minute=0, second=0, microsecond=0)
    daily = TaskSchedule("daily", hour=9, minute=0)
    assert daily.next_fire(now) == now.replace(hour=9, minute=0)
    later = now.replace(hour=10)
    assert daily.next_fire(later) == now.replace(hour=9) + timedelta(days=1)
    every = TaskSchedule("every", minutes=30)
    assert every.next_fire(now) == now + timedelta(minutes=30)


def test_rules_engine():
    rules = default_rules()
    purchase = RuleEngine.decide("Buy a standing desk", rules)
    assert purchase.action_class is ActionClass.PURCHASE
    assert purchase.behavior is RuleBehavior.ASK_FIRST
    credentials = RuleEngine.decide("Change my bank password", rules)
    assert credentials.action_class is ActionClass.CREDENTIALS
    assert credentials.behavior is RuleBehavior.HAND_OFF
    assert credentials.rule and credentials.rule.locked
    install = RuleEngine.decide("Install a package with apt", rules)
    assert install.behavior is RuleBehavior.WITHOUT_ASKING
    read = RuleEngine.decide("Read the docs and summarize", rules)
    assert read.behavior is RuleBehavior.WITHOUT_ASKING
    pre = CustomRule("Share the surprise party plan", RuleBehavior.IF_PRE_APPROVED)
    assert RuleEngine.decide("Share the surprise party plan", [pre]).behavior is RuleBehavior.ASK_FIRST
    assert RuleEngine.decide("Share the surprise party plan", [pre], pre_approved=True).behavior is RuleBehavior.WITHOUT_ASKING
    yaml = RuleEngine.yaml(rules)
    assert "builtin.credentials" not in yaml  # ids are not written
    assert "behavior: hand-off" in yaml
    instructions = RuleEngine.instructions(rules)
    assert "Change a password or move money" in instructions


def test_instructions_render():
    bot = Bot.new("Ada")
    text = render_instructions(bot, default_rules())
    assert "# You are Ada" in text
    assert "[[status:" in text
    assert "Change a password or move money" in text


def test_volume(tmp_path):
    volume = LocalVolume(tmp_path / "Volume")
    volume.write_text(VolumeLayout.memory("ada"), "# Memory\n")
    assert volume.read_text(VolumeLayout.memory("ada")) == "# Memory\n"
    volume.write_text(VolumeLayout.inbox("ada") + "file.txt", "hello")
    assert [entry.name for entry in volume.walk(VolumeLayout.inbox("ada"))] == ["file.txt"]
    with pytest.raises(VolumeSecret):
        volume.write_text(VolumeLayout.memory("ada"), "key=sk-" + "a" * 30)
    with pytest.raises(VolumeInvalid):
        volume.write("../escape.txt", b"no")
    assert volume.ls(VolumeLayout.outputs("ada")) == []


async def test_store_demo_flow(tmp_path):
    volume = LocalVolume(tmp_path / "Volume")
    engine = CuaEngine(ModelConfig(demo=True, label="test"))
    store = BotStore(volume, tmp_path / "data", engine)
    bot = await store.create_bot("Ada", AvatarConfig(), Harness.HERMES, Placement.LOCAL)
    assert bot.id == "ada"
    for _ in range(40):
        await store.poll_once(bot.id)
        await asyncio.sleep(0.02)
        if any("scripted demo" in message.text for message in store.messages_for(bot.id)):
            break
    assert store.bot("ada").run_id.startswith("demo-")
    assert any("scripted demo" in message.text for message in store.messages_for("ada"))
    assert store.rules_for("ada")[0].locked

    await store.send("ada", "Research standing desks and write me a short summary")
    for _ in range(60):
        await store.poll_once("ada")
        await asyncio.sleep(0.02)
        if any(message.kind.get("type") == "result" for message in store.messages_for("ada")):
            break
    assert any(message.kind.get("type") == "result" for message in store.messages_for("ada"))
    assert volume.read(VolumeLayout.outputs("ada") + "standing-desks.md") is not None


async def test_store_approval_schedule_and_reset(tmp_path):
    volume = LocalVolume(tmp_path / "Volume")
    engine = CuaEngine(ModelConfig(demo=True, label="test"))
    store = BotStore(volume, tmp_path / "data", engine)
    await store.create_bot("Ada", AvatarConfig(), Harness.HERMES, Placement.LOCAL)
    for _ in range(20):
        await store.poll_once("ada")
        await asyncio.sleep(0.02)

    store.finish_turn("ada", "\n".join([
        "[[ask: Buy a desk | $400]]",
        "[[schedule: daily 09:00 | Morning | Summarize mail]]",
    ]))
    assert len(store.pending_approvals("ada")) == 1
    assert len(store.tasks_for("ada")) >= 1
    approval = store.pending_approvals("ada")[0]
    await store.decide(approval.id, True)
    assert store.approval(approval.id).state.value == "approved"

    scheduled = [task for task in store.tasks_for("ada") if task.schedule]
    assert len(scheduled) == 1
    assert scheduled[0].schedule.kind == "daily"
    assert scheduled[0].next_run is not None

    await store.pause("ada")
    assert store.bot("ada").is_paused
    await store.resume("ada")
    assert not store.bot("ada").is_paused

    await store.reset("ada")
    assert store.bot("ada") is None
    assert store.messages_for("ada") == []
