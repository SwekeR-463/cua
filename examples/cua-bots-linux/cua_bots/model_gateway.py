"""OpenAI-compatible gateway for a model running on the host.

The bot's harness runs *inside* its Space (a Docker container), so
``127.0.0.1:11434`` is not the host.  This router listens on the same port as
the app, binds on all interfaces, and forwards to Ollama on loopback.  It can
also answer with a scripted completion when no model is available.

The URL handed to ``agent_start`` is ``http://<host-ip>:<port>/model/v1``.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse


class ModelGateway:
    def __init__(self, demo: bool = False, ollama_url: str = "http://127.0.0.1:11434",
                 token: Optional[str] = None, model: str = "llama3.2:3b"):
        self.demo = demo
        self.ollama_url = ollama_url.rstrip("/")
        self.token = token
        self.model = model
        self.router = APIRouter()
        self.router.add_api_route("/v1/models", self.models, methods=["GET"])
        self.router.add_api_route("/v1/chat/completions", self.chat, methods=["POST"])

    def _authorized(self, request: Request) -> bool:
        if not self.token:
            return True
        header = request.headers.get("authorization", "")
        return header == f"Bearer {self.token}" or header == self.token

    async def models(self, request: Request) -> JSONResponse:
        if not self._authorized(request):
            return JSONResponse({"error": {"message": "unauthorized"}}, status_code=401)
        return JSONResponse({"object": "list", "data": [
            {"id": self.model, "object": "model", "owned_by": "local"},
        ]})

    async def chat(self, request: Request):
        if not self._authorized(request):
            return JSONResponse({"error": {"message": "unauthorized"}}, status_code=401)
        body = await request.body()
        try:
            payload = json.loads(body or b"{}")
        except json.JSONDecodeError:
            return JSONResponse({"error": {"message": "invalid JSON"}}, status_code=400)
        if self.demo:
            return JSONResponse(self._scripted(payload))
        try:
            return await self._proxy(body)
        except Exception:
            return JSONResponse(self._scripted(payload))

    async def _proxy(self, body: bytes):
        client = httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10.0))
        request = client.build_request(
            "POST", f"{self.ollama_url}/v1/chat/completions", content=body,
            headers={"content-type": "application/json"},
        )
        response = await client.send(request, stream=True)
        if response.status_code >= 400:
            await response.aclose()
            await client.aclose()
            return JSONResponse({"error": {"message": f"model returned {response.status_code}"}},
                                status_code=502)

        async def stream():
            try:
                async for chunk in response.aiter_raw():
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        return StreamingResponse(stream(), status_code=response.status_code,
                                 media_type=response.headers.get("content-type", "application/json"))

    def _scripted(self, payload: dict[str, Any]) -> dict[str, Any]:
        messages = payload.get("messages") or []
        last = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                last = str(message.get("content") or "")
                break
        text = (
            "[[status: Ready]]\n"
            f"I heard: {last[:240]}\n"
            "Connect Ollama or a provider key to give me a real model.\n"
        )
        return {
            "id": "chatcmpl-demo",
            "object": "chat.completion",
            "created": 0,
            "model": payload.get("model") or self.model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
