import base64
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any


FORMAT = "automus-config-v1"
ITERATIONS = 200_000


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _secret(api_key: str, db_url: str) -> bytes:
    return f"Automus::{api_key}::{db_url.rstrip('/')}::atualizacao".encode("utf-8")


def _derive_key(api_key: str, db_url: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", _secret(api_key, db_url), salt, ITERATIONS, dklen=32)


def _xor_stream(data: bytes, key: bytes, nonce: bytes) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < len(data):
        block = hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(a ^ b for a, b in zip(data, out))


def encrypt_config(config: dict[str, Any], api_key: str, db_url: str) -> dict[str, Any]:
    import os

    payload = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    salt = os.urandom(16)
    nonce = os.urandom(16)
    key = _derive_key(api_key, db_url, salt)
    ciphertext = _xor_stream(payload, key, nonce)
    tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    return {
        "format": FORMAT,
        "kdf": "pbkdf2-sha256",
        "iterations": ITERATIONS,
        "salt": _b64e(salt),
        "nonce": _b64e(nonce),
        "ciphertext": _b64e(ciphertext),
        "tag": _b64e(tag),
    }


def decrypt_config(encrypted: dict[str, Any], api_key: str, db_url: str) -> dict[str, Any]:
    if encrypted.get("format") != FORMAT:
        raise RuntimeError("Formato de automus_config criptografado invalido.")
    salt = _b64d(str(encrypted.get("salt") or ""))
    nonce = _b64d(str(encrypted.get("nonce") or ""))
    ciphertext = _b64d(str(encrypted.get("ciphertext") or ""))
    expected_tag = _b64d(str(encrypted.get("tag") or ""))
    key = _derive_key(api_key, db_url, salt)
    actual_tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(actual_tag, expected_tag):
        raise RuntimeError("automus_config criptografado nao confere com este projeto.")
    payload = _xor_stream(ciphertext, key, nonce)
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("automus_config criptografado invalido.")
    return data


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise RuntimeError(f"JSON invalido em {path}")
    return data
