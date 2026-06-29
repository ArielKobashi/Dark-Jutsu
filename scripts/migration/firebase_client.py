from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class FirebaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class FirebaseConfig:
    api_key: str
    database_url: str
    email: str = ""
    password: str = ""
    id_token: str = ""


class FirebaseClient:
    def __init__(self, config: FirebaseConfig):
        self.config = config
        self._id_token = config.id_token

    def login(self) -> str:
        if self._id_token:
            return self._id_token
        if not self.config.api_key or not self.config.email or not self.config.password:
            raise FirebaseError("Informe FIREBASE_API_KEY, FIREBASE_EMAIL e FIREBASE_PASSWORD ou FIREBASE_ID_TOKEN.")
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={self.config.api_key}"
        data = self._request(
            url,
            method="POST",
            payload={
                "email": self.config.email,
                "password": self.config.password,
                "returnSecureToken": True,
            },
            authenticated=False,
        )
        token = data.get("idToken")
        if not token:
            raise FirebaseError("Login Firebase nao retornou idToken.")
        self._id_token = str(token)
        return self._id_token

    def get_path(self, path: str) -> Any:
        token = self.login()
        safe_path = "/".join(urllib.parse.quote(part, safe="") for part in path.strip("/").split("/") if part)
        base = self.config.database_url.rstrip("/")
        url = f"{base}/{safe_path}.json?auth={urllib.parse.quote(token)}"
        return self._request(url, method="GET", authenticated=True)

    def _request(self, url: str, method: str, payload: dict[str, Any] | None = None, authenticated: bool = True) -> Any:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            auth_hint = " autenticado" if authenticated else ""
            raise FirebaseError(f"Firebase HTTP {exc.code}{auth_hint}: {text}") from exc
