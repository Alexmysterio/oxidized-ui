from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import UploadFile

from .errors import AppError

MAX_IMAGE_BYTES = 1_500_000
IMAGE_TYPES = {
    "png": ".png",
    "jpeg": ".jpg",
    "webp": ".webp",
    "gif": ".gif",
}
MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _detect_extension(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    return None


def read_image(upload: UploadFile) -> tuple[bytes, str]:
    """Read and validate a raster image. SVG is rejected on purpose."""
    data = upload.file.read(MAX_IMAGE_BYTES + 1)
    if not data:
        raise AppError("validation.invalid_format", params={"field": "file"})
    if len(data) > MAX_IMAGE_BYTES:
        raise AppError("app.payload_too_large")
    detected = _detect_extension(data)
    if detected is None:
        raise AppError("validation.invalid_format", params={"field": "file"})
    return data, IMAGE_TYPES[detected]


def write_atomic(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    fd, temporary = tempfile.mkstemp(prefix=".image-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def media_type(path: Path) -> str:
    return MEDIA_TYPES.get(path.suffix.casefold(), "application/octet-stream")
