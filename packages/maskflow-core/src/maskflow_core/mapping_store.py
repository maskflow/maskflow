"""Optional persistence for a Mapping produced by mask_with_policy() --
masking itself stays pure/stateless (see masking.py's module docstring);
this is for callers who need the mapping to outlive one process/request
(e.g. a multi-turn conversation: mask now, unmask a response that arrives
later, possibly in a different process).

Three implementations behind one Protocol:
  - InMemoryMappingStore: process-local, TTL-expiring. Default -- nothing to
    configure, nothing to install.
  - EncryptedFileMappingStore: AES-GCM at rest, key from MASKFLOW_MAPPING_KEY
    (hex-encoded) or passed explicitly. Plaintext PII never touches disk
    unencrypted (CLAUDE.md rule 4). Requires the optional `cryptography`
    dependency -- install `maskflow-core[store]`.
  - RedisMappingStore: interface-only stub this round -- see its docstring.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Protocol

from .mapping import Mapping

_MAPPING_KEY_ENV = "MASKFLOW_MAPPING_KEY"


class MappingStore(Protocol):
    def save(self, session_id: str, mapping: Mapping) -> None: ...

    def load(self, session_id: str) -> Mapping | None: ...

    def delete(self, session_id: str) -> None: ...


class InMemoryMappingStore:
    """Process-local store. An entry expires `ttl_seconds` after `save()`;
    `load()`/`delete()` past expiry behave as if it were never saved."""

    def __init__(self, ttl_seconds: float = 3600) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[str, tuple[float, Mapping]] = {}

    def save(self, session_id: str, mapping: Mapping) -> None:
        self._entries[session_id] = (time.monotonic() + self._ttl, mapping)

    def load(self, session_id: str) -> Mapping | None:
        entry = self._entries.get(session_id)
        if entry is None:
            return None
        expires_at, mapping = entry
        if time.monotonic() >= expires_at:
            del self._entries[session_id]
            return None
        return mapping

    def delete(self, session_id: str) -> None:
        self._entries.pop(session_id, None)


def _resolve_file_key(key: bytes | None) -> bytes:
    if key is not None:
        return key
    env_value = os.environ.get(_MAPPING_KEY_ENV)
    if not env_value:
        raise ValueError(
            "EncryptedFileMappingStore needs a key: pass key=... or set "
            f"{_MAPPING_KEY_ENV} (hex-encoded, 32 bytes for AES-256-GCM)."
        )
    return bytes.fromhex(env_value)


class EncryptedFileMappingStore:
    """One AES-GCM-encrypted file per session under `directory`. Requires
    the optional `cryptography` dependency -- install `maskflow-core[store]`."""

    def __init__(self, directory: str | Path, key: bytes | None = None) -> None:
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as exc:
            raise ImportError(
                "EncryptedFileMappingStore needs the optional 'cryptography' "
                "dependency -- install with `pip install maskflow-core[store]`."
            ) from exc
        self._aesgcm = AESGCM(_resolve_file_key(key))
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        # session_id is caller-controlled; keep it to a filesystem-safe id
        # rather than trusting it as a path component.
        if not session_id or any(c in session_id for c in "/\\\0"):
            raise ValueError(f"Invalid session_id for file storage: {session_id!r}")
        return self._directory / f"{session_id}.maskflow"

    def save(self, session_id: str, mapping: Mapping) -> None:
        plaintext = json.dumps(mapping.to_json()).encode("utf-8")
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, None)
        self._path(session_id).write_bytes(nonce + ciphertext)

    def load(self, session_id: str) -> Mapping | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        blob = path.read_bytes()
        nonce, ciphertext = blob[:12], blob[12:]
        plaintext = self._aesgcm.decrypt(nonce, ciphertext, None)
        return Mapping.from_json(json.loads(plaintext.decode("utf-8")))

    def delete(self, session_id: str) -> None:
        self._path(session_id).unlink(missing_ok=True)


class RedisMappingStore:
    """MappingStore shape for a future Redis-backed store -- **not
    implemented yet**. The constructor accepts the connection parameters
    callers will eventually need, so code can be written against this class
    now; every method raises NotImplementedError until a real
    implementation (behind a `redis` optional dependency) ships."""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0) -> None:
        self.host = host
        self.port = port
        self.db = db

    def save(self, session_id: str, mapping: Mapping) -> None:
        raise NotImplementedError("RedisMappingStore is not implemented yet")

    def load(self, session_id: str) -> Mapping | None:
        raise NotImplementedError("RedisMappingStore is not implemented yet")

    def delete(self, session_id: str) -> None:
        raise NotImplementedError("RedisMappingStore is not implemented yet")
