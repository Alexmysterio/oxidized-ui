#!/usr/bin/env python3
"""Restore an encrypted Oxidized UI .oxui export.

Stop the container first. The script restores the database, config and
known_hosts, and prints the FERNET_KEY that must be put in .env.
"""
from __future__ import annotations

import argparse
import getpass
import io
import shutil
import sys
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MAGIC = b"OXUI1"
ITERATIONS = 600_000


def decrypt(passphrase: str, payload: bytes) -> bytes:
    if not payload.startswith(MAGIC) or len(payload) < 44:
        raise ValueError("not an Oxidized UI .oxui file")
    salt = payload[5:21]
    nonce = payload[21:33]
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS).derive(
        passphrase.encode("utf-8")
    )
    return AESGCM(key).decrypt(nonce, payload[33:], MAGIC)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--config-dir", type=Path, default=Path("data/config"))
    parser.add_argument("--yes", action="store_true", help="overwrite current data")
    args = parser.parse_args()
    passphrase = getpass.getpass("Passphrase: ")
    raw = decrypt(passphrase, args.archive.read_bytes())
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = set(archive.namelist())
        for name in names:
            target = (args.data_dir / name).resolve()
            if args.data_dir.resolve() not in target.parents and target != args.data_dir.resolve():
                raise SystemExit(f"unsafe archive path: {name}")
    if not args.yes:
        print("Dry run. Use --yes after stopping the container to restore.")
        print("Contains:", ", ".join(sorted(names)))
        return 0
    backup = args.data_dir / "restore-previous"
    backup.mkdir(parents=True, exist_ok=True)
    for name, dest in (("database.sqlite3", args.data_dir / "ui" / "oxidized-ui.sqlite3"), ("config.yaml", args.config_dir / "config"), ("known_hosts", args.config_dir / ".ssh" / "known_hosts")):
        if dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, backup / dest.name)
        if name in names:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zipfile.ZipFile(io.BytesIO(raw)).read(name))
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for name in sorted(names):
            if not name.startswith(("branding/", "avatars/")):
                continue
            dest = args.data_dir / "ui" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(archive.read(name))
    fernet = zipfile.ZipFile(io.BytesIO(raw)).read("fernet.key").decode("ascii")
    print(f"Restored. Set this in .env before starting:\nFERNET_KEY={fernet}")
    print("Previous files were copied to", backup)
    return 0


if __name__ == "__main__":
    sys.exit(main())
