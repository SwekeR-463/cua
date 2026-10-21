"""Custom rules: the four behaviours, action classes and the rule engine.

Ported line-for-line from ``CuaBotsCore/Model/Rules.swift``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .models import new_id


class RuleBehavior(str, Enum):
    WITHOUT_ASKING = "allow"
    IF_PRE_APPROVED = "pre-approved"
    ASK_FIRST = "ask"
    HAND_OFF = "hand-off"

    @property
    def title(self) -> str:
        return {
            RuleBehavior.WITHOUT_ASKING: "Take action without asking",
            RuleBehavior.IF_PRE_APPROVED: "Take action when you say so",
            RuleBehavior.ASK_FIRST: "Ask before taking action",
            RuleBehavior.HAND_OFF: "Hand off to you",
        }[self]

    @property
    def short(self) -> str:
        return {
            RuleBehavior.WITHOUT_ASKING: "Allowed",
            RuleBehavior.IF_PRE_APPROVED: "When you say so",
            RuleBehavior.ASK_FIRST: "Asks first",
            RuleBehavior.HAND_OFF: "Hands off",
        }[self]


class ActionClass(str, Enum):
    PURCHASE = "purchase"
    DELETE = "delete"
    COMMUNICATE = "communicate"
    CREDENTIALS = "credentials"
    SIGN_IN = "signIn"
    INSTALL = "install"
    READ_ONLY = "readOnly"
    OTHER = "other"

    @property
    def keywords(self) -> list[str]:
        return {
            ActionClass.CREDENTIALS: ["password", "transfer money", "wire", "bank transfer", "2fa", "passcode"],
            ActionClass.PURCHASE: ["buy", "purchase", "order", "checkout", "pay ", "payment", "book "],
            ActionClass.DELETE: ["delete", "remove", "erase", "wipe", "drop "],
            ActionClass.COMMUNICATE: ["send", "email", "message", "post ", "reply", "invite", "text ", "slack"],
            ActionClass.SIGN_IN: ["sign in", "log in", "login", "log me in", "signin"],
            ActionClass.INSTALL: ["install", "brew ", "apt ", "download and run"],
            ActionClass.READ_ONLY: ["read", "look up", "search", "summarize", "check", "review"],
            ActionClass.OTHER: [],
        }[self]

    @staticmethod
    def classify(action: str) -> "ActionClass":
        text = " " + action.lower() + " "
        for cls in [ActionClass.CREDENTIALS, ActionClass.PURCHASE, ActionClass.DELETE,
                    ActionClass.COMMUNICATE, ActionClass.SIGN_IN, ActionClass.INSTALL,
                    ActionClass.READ_ONLY]:
            if any(keyword in text for keyword in cls.keywords):
                return cls
        return ActionClass.OTHER


@dataclass
class CustomRule:
    action: str
    behavior: RuleBehavior
    action_class: Optional[ActionClass] = None
    locked: bool = False
    is_built_in: bool = False
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "behavior": self.behavior.value,
            "action_class": self.action_class.value if self.action_class else None,
            "locked": self.locked,
            "is_built_in": self.is_built_in,
            "title": self.behavior.title,
            "short": self.behavior.short,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "CustomRule":
        raw_class = data.get("action_class")
        return CustomRule(
            action=data.get("action", ""),
            behavior=RuleBehavior(data.get("behavior", "allow")),
            action_class=ActionClass(raw_class) if raw_class else None,
            locked=bool(data.get("locked")),
            is_built_in=bool(data.get("is_built_in")),
            id=data.get("id") or new_id(),
        )


def default_rules() -> list[CustomRule]:
    return [
        CustomRule("Change a password or move money", RuleBehavior.HAND_OFF,
                   ActionClass.CREDENTIALS, locked=True, is_built_in=True, id="builtin.credentials"),
        CustomRule("Make a purchase", RuleBehavior.ASK_FIRST,
                   ActionClass.PURCHASE, is_built_in=True, id="builtin.purchase"),
        CustomRule("Permanently delete data", RuleBehavior.ASK_FIRST,
                   ActionClass.DELETE, is_built_in=True, id="builtin.delete"),
        CustomRule("Send a message or email to someone", RuleBehavior.ASK_FIRST,
                   ActionClass.COMMUNICATE, is_built_in=True, id="builtin.communicate"),
        CustomRule("Sign in to a site with a saved password", RuleBehavior.ASK_FIRST,
                   ActionClass.SIGN_IN, is_built_in=True, id="builtin.signin"),
        CustomRule("Install software on its computer", RuleBehavior.WITHOUT_ASKING,
                   ActionClass.INSTALL, is_built_in=True, id="builtin.install"),
        CustomRule("Read and research in the apps you connect", RuleBehavior.WITHOUT_ASKING,
                   ActionClass.READ_ONLY, is_built_in=True, id="builtin.read"),
    ]


@dataclass
class RuleDecision:
    behavior: RuleBehavior
    rule: Optional[CustomRule]
    action_class: ActionClass


_STOP_WORDS = {"when", "with", "that", "this", "your", "from", "into", "about"}


class RuleEngine:
    @staticmethod
    def decide(action: str, rules: list[CustomRule], pre_approved: bool = False) -> RuleDecision:
        cls = ActionClass.classify(action)
        lower = action.lower()
        locked = next((r for r in rules if r.locked and r.action_class is cls), None)
        if locked:
            return RuleDecision(locked.behavior, locked, cls)

        def matches(rule: CustomRule) -> bool:
            words = [w for w in re.split(r"[^a-z0-9]+", rule.action.lower())
                     if len(w) > 3 and w not in _STOP_WORDS]
            return bool(words) and all(w in lower for w in words)

        custom = next((r for r in rules if not r.is_built_in and not r.locked and matches(r)), None)
        rule = custom or next((r for r in rules if r.action_class is cls), None)
        behavior = rule.behavior if rule else RuleBehavior.WITHOUT_ASKING
        if behavior is RuleBehavior.IF_PRE_APPROVED:
            behavior = RuleBehavior.WITHOUT_ASKING if pre_approved else RuleBehavior.ASK_FIRST
        return RuleDecision(behavior, rule, cls)

    @staticmethod
    def yaml(rules: list[CustomRule]) -> str:
        out = "# Custom rules for this bot. Written by the Cua Bots app.\n"
        out += "# behavior: allow | pre-approved | ask | hand-off\nrules:\n"
        for rule in rules:
            out += f"  - action: {RuleEngine._quote(rule.action)}\n"
            out += f"    behavior: {rule.behavior.value}\n"
            if rule.action_class:
                out += f"    class: {rule.action_class.value}\n"
            if rule.locked:
                out += "    locked: true\n"
        return out

    @staticmethod
    def instructions(rules: list[CustomRule]) -> str:
        out = "## Rules for acting on the user's behalf\n\n"
        out += ("Before an action, find its rule. If it says **ask**, stop and write "
                "`[[ask: <the action> | <why and exact details>]]`, then wait for the user's "
                "\"Approved\" or \"Denied\". If it says **hand-off**, write `[[handoff: <the action>]]` "
                "and wait: the user does it themselves. **pre-approved** means allowed only when the user "
                "asked for exactly this in their own message; otherwise ask. Approving one action is not "
                "ongoing permission.\n\n")
        for rule in rules:
            suffix = " (cannot be changed)" if rule.locked else ""
            out += f"- {rule.action}: **{rule.behavior.value}**{suffix}\n"
        return out

    @staticmethod
    def _quote(value: str) -> str:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
