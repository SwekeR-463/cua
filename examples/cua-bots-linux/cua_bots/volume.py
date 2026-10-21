"""The Cua Volume layout, backed by a folder on Linux.

Same paths, same refusal to put secrets under ``agents/`` as
``CuaBotsCore/Volume/Volume.swift``.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .models import Harness, iso, from_iso


class VolumeError(Exception):
    pass


class VolumeInvalid(VolumeError):
    pass


class VolumeSecret(VolumeError):
    def __init__(self, path: str, line: int):
        super().__init__(
            f"{path} line {line} looks like a secret. Secrets belong in the Keyvault, not the Volume."
        )
        self.path = path
        self.line = line


class VolumeLayout:
    PUBLIC = "public/"

    @staticmethod
    def home(agent: str) -> str:
        return f"agents/{agent}/"

    @staticmethod
    def identity(agent: str) -> str:
        return f"agents/{agent}/identity/bot.json"

    @staticmethod
    def memory(agent: str) -> str:
        return f"agents/{agent}/memory/MEMORY.md"

    @staticmethod
    def rules(agent: str) -> str:
        return f"agents/{agent}/rules.yaml"

    @staticmethod
    def tasks(agent: str) -> str:
        return f"agents/{agent}/tasks.json"

    @staticmethod
    def outputs(agent: str) -> str:
        return f"agents/{agent}/outputs/"

    @staticmethod
    def inbox(agent: str) -> str:
        return f"agents/{agent}/inbox/"

    @staticmethod
    def instructions(agent: str, harness: Harness) -> str:
        return f"agents/{agent}/{harness.instructions_file}"

    @staticmethod
    def space(space_id: str) -> str:
        mapped = "".join(c if (c.isascii() and (c.isalnum() or c in "._-")) else "-"
                         for c in space_id.strip())
        name = mapped.strip("-")
        return f"spaces/{name or 'space'}/"


@dataclass
class VolumeEntry:
    path: str
    name: str
    is_folder: bool
    size: int = 0
    modified: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.path,
            "path": self.path,
            "name": self.name,
            "is_folder": self.is_folder,
            "size": self.size,
            "modified": iso(self.modified),
        }


_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"xox[abpr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{24,}"),
]


class SecretScanner:
    @staticmethod
    def first_hit(data: bytes) -> Optional[int]:
        text = data.decode("utf-8", "replace")
        for index, line in enumerate(text.split("\n"), start=1):
            if any(pattern.search(line) for pattern in _PATTERNS):
                return index
        return None


class LocalVolume:
    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _url(self, path: str) -> Path:
        key = path[1:] if path.startswith("/") else path
        parts = [p for p in key.split("/") if p not in ("", ".")]
        if any(p == ".." for p in parts):
            raise VolumeInvalid(f"Invalid Volume path: {path}")
        return self.root.joinpath(*parts) if parts else self.root

    def ls(self, path: str) -> list[VolumeEntry]:
        directory = self._url(path)
        if not directory.is_dir():
            return []
        prefix = path if (not path or path.endswith("/")) else path + "/"
        out: list[VolumeEntry] = []
        for child in sorted(directory.iterdir(), key=lambda p: p.name):
            if child.name.startswith("."):
                continue
            try:
                stat = child.stat()
                modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                out.append(VolumeEntry(
                    path=f"{prefix}{child.name}{'/' if child.is_dir() else ''}",
                    name=child.name,
                    is_folder=child.is_dir(),
                    size=0 if child.is_dir() else stat.st_size,
                    modified=modified,
                ))
            except OSError:
                continue
        return out

    def walk(self, path: str) -> list[VolumeEntry]:
        found: list[VolumeEntry] = []
        for entry in self.ls(path):
            if entry.is_folder:
                found.extend(self.walk(entry.path))
            else:
                found.append(entry)
        return found

    def read(self, path: str) -> Optional[bytes]:
        try:
            return self._url(path).read_bytes()
        except (OSError, VolumeInvalid):
            return None

    def write(self, path: str, data: bytes) -> None:
        if path.startswith("agents/"):
            hit = SecretScanner.first_hit(data)
            if hit is not None:
                raise VolumeSecret(path, hit)
        target = self._url(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=".cua-bots-", dir=str(target.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(temp, target)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def delete(self, path: str) -> None:
        target = self._url(path)
        if target.is_dir():
            import shutil
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

    def read_text(self, path: str) -> Optional[str]:
        data = self.read(path)
        return data.decode("utf-8", "replace") if data is not None else None

    def write_text(self, path: str, text: str) -> None:
        self.write(path, text.encode("utf-8"))

    def read_json(self, path: str) -> Any:
        data = self.read(path)
        if data is None:
            return None
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return None

    def write_json(self, path: str, value: Any) -> None:
        self.write_text(path, json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))
