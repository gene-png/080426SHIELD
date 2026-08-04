"""Local-filesystem storage backend.

Used by tests and (optionally) by developer workflows that don't want a
MinIO container. The signed_url method returns a `file://` URL with a
short TTL marker in the query string - the backend doesn't enforce TTL
(that's S3's job in production); the marker exists so callers can prove
to themselves that a fresh URL is signed each time.
"""

from __future__ import annotations

import time
from pathlib import Path

from app.storage.base import StorageBackend, StoredObject, sha256_of


class LocalFilesystemStorage(StorageBackend):
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        # Don't let `key` escape the root via "../" — keys are
        # always app-generated, but defense in depth.
        safe = key.lstrip("/").replace("..", "_")
        target = self.root / safe
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def put(self, key: str, data: bytes, *, content_type: str) -> StoredObject:  # noqa: ARG002
        path = self._path_for(key)
        path.write_bytes(data)
        return StoredObject(key=key, size_bytes=len(data), sha256=sha256_of(data))

    def get(self, key: str) -> bytes:
        path = self._path_for(key)
        if not path.exists():
            raise FileNotFoundError(key)
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path_for(key).exists()

    def health_check(self) -> None:
        # Reachable == the root directory exists and is writable. mkdir on
        # construction already ensures it; re-checking here keeps the probe
        # honest if the volume vanished at runtime.
        if not self.root.is_dir():
            raise FileNotFoundError(f"storage root {self.root} is not a directory")

    def signed_url(self, key: str, *, ttl_seconds: int = 600) -> str:
        path = self._path_for(key)
        return f"file://{path.absolute()}?expires={int(time.time()) + ttl_seconds}"
