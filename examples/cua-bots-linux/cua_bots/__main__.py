from __future__ import annotations

import os

import uvicorn

from .server import app


def main() -> None:
    uvicorn.run(
        app,
        host=os.environ.get("CUA_BOTS_HOST", "127.0.0.1"),
        port=int(os.environ.get("CUA_BOTS_PORT", "8765")),
        log_level=os.environ.get("CUA_BOTS_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
