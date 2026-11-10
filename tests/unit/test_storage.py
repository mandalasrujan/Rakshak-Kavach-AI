from pathlib import Path

import pytest

from app.core.storage import LocalObjectStorage, create_storage


async def test_put_get_delete_round_trip(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path)
    await storage.put("patients/abc/file.pdf", b"%PDF-data")
    assert await storage.get("patients/abc/file.pdf") == b"%PDF-data"
    assert list((tmp_path / "patients" / "abc").iterdir()) == [
        tmp_path / "patients" / "abc" / "file.pdf"
    ]  # no temp files left behind
    await storage.delete("patients/abc/file.pdf")
    await storage.delete("patients/abc/file.pdf")  # idempotent
    with pytest.raises(FileNotFoundError):
        await storage.get("patients/abc/file.pdf")


@pytest.mark.parametrize(
    "key", ["../escape.pdf", "patients/../../etc/passwd", "/abs.pdf", "Upper.pdf", "a b.pdf", ""]
)
async def test_unsafe_keys_are_rejected(tmp_path: Path, key: str) -> None:
    storage = LocalObjectStorage(tmp_path / "root")
    with pytest.raises(ValueError):
        await storage.put(key, b"x")


def test_unknown_backend_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        create_storage("s3", str(tmp_path))
