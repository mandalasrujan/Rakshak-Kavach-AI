"""Object storage interface. Local volume now; an S3-compatible backend can implement the
same protocol later. Keys are random and never derived from file names."""

import asyncio
import os
import re
import uuid
from pathlib import Path
from typing import Protocol

_VALID_KEY = re.compile(r"^[a-z0-9][a-z0-9/_.-]{0,254}$")


class ObjectStorage(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...


class LocalObjectStorage:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not _VALID_KEY.fullmatch(key) or ".." in key.split("/"):
            raise ValueError("invalid storage key")
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError("invalid storage key")
        return path

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        with open(tmp, "xb") as handle:  # atomic: write a temp file, then rename
            handle.write(data)
        os.replace(tmp, path)
        os.chmod(path, 0o600)

    async def put(self, key: str, data: bytes) -> None:
        await asyncio.to_thread(self._write, self._path(key), data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, missing_ok=True)


def create_storage(backend: str, local_path: str) -> ObjectStorage:
    if backend == "local":
        return LocalObjectStorage(local_path)
    raise ValueError(f"unsupported storage backend: {backend}")
