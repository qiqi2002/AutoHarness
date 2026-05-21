"""Minimal OpenAI-compatible chat client used by demos."""

from __future__ import annotations

import json
import os
import re
import ssl
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ChatConfig:
    api_key: str
    base_url: str = "https://api.minimaxi.com/v1/"
    model: str = "MiniMax-M2.7-highspeed"
    timeout_seconds: int = 60
    insecure_tls: bool = False

    @classmethod
    def from_env(cls) -> "ChatConfig":
        api_key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("MODEL_API_KEY")
        if not api_key:
            raise RuntimeError("MINIMAX_API_KEY or MODEL_API_KEY is required")
        return cls(
            api_key=api_key,
            base_url=os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1/"),
            model=os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7-highspeed"),
            insecure_tls=os.environ.get("AUTOHARNESS_LLM_INSECURE_TLS") == "1",
        )


class ChatClient:
    def __init__(self, config: ChatConfig) -> None:
        self.config = config

    def complete_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        content = self.complete(messages)
        return extract_json_object(strip_think_blocks(content))

    def complete(self, messages: list[dict[str, str]]) -> str:
        base_url = self.config.base_url.rstrip("/")
        body = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0,
        }
        request = Request(
            f"{base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds, context=self._ssl_context()) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"chat completion failed: HTTP {exc.code}: {detail}") from exc
        return payload["choices"][0]["message"]["content"]

    def _ssl_context(self) -> ssl.SSLContext:
        if self.config.insecure_tls:
            return ssl._create_unverified_context()
        try:
            import certifi
        except ModuleNotFoundError:
            return ssl.create_default_context()
        return ssl.create_default_context(cafile=certifi.where())


def strip_think_blocks(value: str) -> str:
    return re.sub(r"<think>.*?</think>", "", value, flags=re.DOTALL).strip()


def extract_json_object(value: str) -> dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", value, flags=re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))

    start = value.find("{")
    end = value.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("model response did not contain a JSON object")
    return json.loads(value[start : end + 1])
