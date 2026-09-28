"""File storage for tailored PDFs: local folder in development, Supabase Storage in production."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import httpx


class Storage(Protocol):
    def put(self, path: str, data: bytes, content_type: str = "application/pdf") -> str: ...
    def signed_url(self, path: str, expires_in: int = 600) -> str: ...
    def get_bytes(self, path: str) -> bytes: ...


class LocalStorage:
    def __init__(self, root: str | Path = ".chirp/files") -> None:
        self.root = Path(root)

    def put(self, path: str, data: bytes, content_type: str = "application/pdf") -> str:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return path

    def signed_url(self, path: str, expires_in: int = 600) -> str:
        return f"/files/{path}"

    def get_bytes(self, path: str) -> bytes:
        return (self.root / path).read_bytes()


class SupabaseStorage:
    def __init__(self, url: str, service_key: str, bucket: str) -> None:
        self.base = f"{url.rstrip('/')}/storage/v1"
        self.bucket = bucket
        self.client = httpx.Client(
            timeout=30, headers={"Authorization": f"Bearer {service_key}", "apikey": service_key}
        )

    def put(self, path: str, data: bytes, content_type: str = "application/pdf") -> str:
        r = self.client.post(
            f"{self.base}/object/{self.bucket}/{path}",
            content=data,
            headers={"Content-Type": content_type, "x-upsert": "true"},
        )
        r.raise_for_status()
        return path

    def signed_url(self, path: str, expires_in: int = 600) -> str:
        r = self.client.post(
            f"{self.base}/object/sign/{self.bucket}/{path}", json={"expiresIn": expires_in}
        )
        r.raise_for_status()
        return f"{self.base}{r.json()['signedURL']}"

    def get_bytes(self, path: str) -> bytes:
        r = self.client.get(f"{self.base}/object/{self.bucket}/{path}")
        r.raise_for_status()
        return r.content


def make_storage(settings) -> Storage:
    key = settings.supabase_service_key.get_secret_value()
    if settings.supabase_url and key:
        return SupabaseStorage(settings.supabase_url, key, settings.storage_bucket)
    return LocalStorage()
