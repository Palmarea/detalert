"""Cliente mínimo de la API de mensajes de Anthropic, solo con la librería estándar (sin `pip install anthropic`).

Imita lo que usa reviewer.py: client.messages.create(...) -> objeto con .content (bloques con .type, .name, .input, .id).
Lee ANTHROPIC_API_KEY y, opcional, ANTHROPIC_BASE_URL (para apuntar a un servidor compatible).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class _Obj(dict):
    """dict con acceso por atributo; sigue siendo serializable a JSON."""
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


class _Messages:
    def __init__(self, parent: "HttpClient"):
        self._p = parent

    def create(self, **body) -> _Obj:
        req = urllib.request.Request(
            self._p.base_url + "/v1/messages",
            data=json.dumps(body, default=str).encode(),
            headers={"x-api-key": self._p.api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._p.timeout) as r:
                data = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"API {e.code}: {e.read().decode()[:500]}") from None
        data["content"] = [_Obj(b) for b in data.get("content", [])]
        return _Obj(data)


class HttpClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout: int = 120):
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]
        self.base_url = (base_url or os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")).rstrip("/")
        self.timeout = timeout
        self.messages = _Messages(self)