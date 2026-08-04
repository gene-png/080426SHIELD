"""Backend selection.

Tests construct LocalFilesystemStorage directly (via dependency override)
and skip this module entirely. Production calls `get_storage()` from the
route layer.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.storage.base import StorageBackend
from app.storage.local import LocalFilesystemStorage


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    settings = get_settings()
    endpoint = settings.s3_endpoint_url
    if not endpoint or endpoint.startswith("file://"):
        root = (
            endpoint.removeprefix("file://")
            if endpoint
            else "/tmp/shield-artifacts"  # noqa: S108 - dev-only fallback; production always sets s3_endpoint_url
        )
        return LocalFilesystemStorage(root)

    # Defer the boto3 import to here so test runs don't pay for it.
    from app.storage.s3 import S3Storage

    return S3Storage(settings)
