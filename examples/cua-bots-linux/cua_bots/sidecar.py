"""A local Ollama sidecar on the Docker bridge.

The bot's harness runs inside a Space (a Docker container).  On many Linux
hosts Docker's bridge cannot reach services bound to the host's loopback, so a
host Ollama is unreachable from inside the Space.  This helper runs the host's
own Ollama binary and model store in a sibling container on the same bridge;
the Space can reach that container directly, and no model traffic leaves the
machine.

It is deliberately best-effort: when Docker, the Ollama binary or the model
store is missing, the caller falls back to a host endpoint or scripted mode.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

NAME = "cua-bots-ollama"
IMAGE = os.environ.get("CUA_BOTS_SIDECAR_IMAGE", "ghcr.io/trycua/linux:24.04")


def _docker(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], text=True, capture_output=True, check=check, timeout=60)


def _container_ip(name: str) -> Optional[str]:
    result = _docker("inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", name)
    ip = result.stdout.strip()
    return ip or None


def _running(name: str) -> bool:
    result = _docker("inspect", "-f", "{{.State.Running}}", name)
    return result.returncode == 0 and result.stdout.strip() == "true"


def _ollama_binary() -> Optional[str]:
    override = os.environ.get("CUA_BOTS_OLLAMA_BIN")
    if override and Path(override).is_file():
        return override
    found = shutil.which("ollama")
    if found:
        return found
    for candidate in ("/usr/local/bin/ollama", "/usr/bin/ollama"):
        if Path(candidate).is_file():
            return candidate
    return None


def _model_store() -> Optional[Path]:
    override = os.environ.get("CUA_BOTS_OLLAMA_MODELS") or os.environ.get("OLLAMA_MODELS")
    candidates = [override] if override else []
    candidates += [
        str(Path.home() / ".ollama" / "models"),
        "/usr/share/ollama/.ollama/models",
        "/var/lib/ollama/.ollama/models",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
    return None


def available() -> bool:
    return bool(_ollama_binary() and _model_store() and shutil.which("docker"))


def ensure(model: str) -> Optional[str]:
    """Start (or reuse) the sidecar and return its OpenAI base URL."""
    if os.environ.get("CUA_BOTS_OLLAMA_SIDECAR", "1") == "0":
        return None
    binary = _ollama_binary()
    models = _model_store()
    if not binary or not models or not shutil.which("docker"):
        return None

    if _running(NAME):
        ip = _container_ip(NAME)
        if ip:
            return f"http://{ip}:11434/v1"

    # A stopped container is stale; recreate it so the mounts are current.
    _docker("rm", "-f", NAME)
    libs = Path("/usr/local/lib/ollama")
    gpu = os.environ.get("CUA_BOTS_SIDECAR_GPU", "auto")
    use_gpu = gpu != "0" and libs.is_dir() and shutil.which("nvidia-smi") is not None

    def command(with_gpu: bool) -> list[str]:
        args = [
            "docker", "run", "-d", "--name", NAME,
            "--label", "cua-bots.sidecar=ollama",
            "--network", "bridge",
            "--memory", os.environ.get("CUA_BOTS_SIDECAR_MEMORY", "6g"),
            "--cpus", os.environ.get("CUA_BOTS_SIDECAR_CPUS", "4"),
        ]
        if with_gpu:
            args += ["--gpus", "all", "-v", f"{libs}:/usr/local/lib/ollama:ro"]
        args += [
            "--entrypoint", "/usr/local/bin/ollama",
            "-e", "OLLAMA_HOST=0.0.0.0:11434",
            "-e", "OLLAMA_MODELS=/models",
            "-e", "OLLAMA_CONTEXT_LENGTH=65536",
            "-e", "OLLAMA_NUM_PARALLEL=1",
        "-e", "OLLAMA_KV_CACHE_TYPE=q8_0",
        "-e", "OLLAMA_FLASH_ATTENTION=1",
            "-e", "OLLAMA_KEEP_ALIVE=10m",
            "-e", "HOME=/tmp",
            "-v", f"{binary}:/usr/local/bin/ollama:ro",
            "-v", f"{models}:/models:ro",
            IMAGE, "serve",
        ]
        return args

    result = subprocess.run(command(use_gpu), text=True, capture_output=True, timeout=180)
    if result.returncode != 0 and use_gpu:
        _docker("rm", "-f", NAME)
        result = subprocess.run(command(False), text=True, capture_output=True, timeout=180)
    if result.returncode != 0:
        return None
    deadline = time.time() + 30
    while time.time() < deadline:
        ip = _container_ip(NAME)
        if ip:
            try:
                import urllib.request
                with urllib.request.urlopen(f"http://{ip}:11434/api/tags", timeout=1) as response:
                    if response.status == 200:
                        return f"http://{ip}:11434/v1"
            except Exception:
                pass
        time.sleep(1)
    return None


def list_models(url: str) -> list[str]:
    try:
        import urllib.request
        base = url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        with urllib.request.urlopen(f"{base}/api/tags", timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
        return [item.get("name") for item in data.get("models", []) if item.get("name")]
    except Exception:
        return []


def status() -> dict:
    ip = _container_ip(NAME) if _running(NAME) else None
    return {"available": available(), "running": bool(ip), "url": f"http://{ip}:11434/v1" if ip else None}
