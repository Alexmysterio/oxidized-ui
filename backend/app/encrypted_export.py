from __future__ import annotations

import io
import json
import os
import sqlite3
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .settings import settings
from .timeutil import utcnow

MAGIC = b"OXUI1"
ITERATIONS = 600_000


def _read_optional(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def build_bundle(db_path: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        # sqlite3 backup target must be a file; use a temporary file for portability
        import tempfile

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            target = Path(temp) / "database.sqlite3"
            with sqlite3.connect(db_path) as source, sqlite3.connect(target) as snapshot:
                source.backup(snapshot)
            archive.write(target, "database.sqlite3")
        config = _read_optional(settings.oxidized_config_dir / "config")
        if config is not None:
            archive.writestr("config.yaml", config)
        known_hosts = _read_optional(settings.oxidized_config_dir / ".ssh" / "known_hosts")
        if known_hosts is not None:
            archive.writestr("known_hosts", known_hosts)
        backups = settings.backup_dir
        if backups.exists():
            for item in sorted(backups.glob("*.yaml"))[-50:]:
                archive.write(item, f"ui-backups/{item.name}")
        for folder in ("branding", "avatars"):
            base = settings.data_dir / folder
            if base.is_dir():
                for item in sorted(base.iterdir()):
                    if item.is_file():
                        archive.write(item, f"{folder}/{item.name}")
        archive.writestr("fernet.key", settings.fernet_key)
        archive.writestr(
            "metadata.json",
            json.dumps({"format": 1, "created_at": utcnow().isoformat(), "app": "oxidized-ui"}),
        )
    return buffer.getvalue()


def encrypt(passphrase: str, payload: bytes) -> bytes:
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS).derive(
        passphrase.encode("utf-8")
    )
    ciphertext = AESGCM(key).encrypt(nonce, payload, MAGIC)
    return MAGIC + salt + nonce + ciphertext


def create_export(passphrase: str) -> bytes:
    db_path = settings.data_dir / "oxidized-ui.sqlite3"
    return encrypt(passphrase, build_bundle(db_path))


def decrypt(passphrase: str, payload: bytes) -> bytes:
    if not payload.startswith(MAGIC):
        raise ValueError("invalid bundle")
    salt = payload[len(MAGIC) : len(MAGIC) + 16]
    nonce = payload[len(MAGIC) + 16 : len(MAGIC) + 28]
    ciphertext = payload[len(MAGIC) + 28 :]
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS).derive(
        passphrase.encode("utf-8")
    )
    return AESGCM(key).decrypt(nonce, ciphertext, MAGIC)


def verify(passphrase: str, payload: bytes) -> dict[str, object]:
    import hashlib

    plain = decrypt(passphrase, payload)
    with zipfile.ZipFile(io.BytesIO(plain)) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise ValueError(f"corrupt entry: {bad}")
        names = archive.namelist()
        metadata = {}
        if "metadata.json" in names:
            metadata = json.loads(archive.read("metadata.json") or b"{}")
    return {
        "ok": True,
        "entries": len(names),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "created_at": metadata.get("created_at"),
        "has_database": "database.sqlite3" in names,
        "has_fernet_key": "fernet.key" in names,
        "has_metadata": "metadata.json" in names,
    }
