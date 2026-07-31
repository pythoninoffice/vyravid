"""
Local filesystem storage for the video processor (GCS-compatible).
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import aiohttp
import structlog

logger = structlog.get_logger(__name__)

VYRAVID_ROOT = Path(os.getenv("VYRAVID_ROOT", Path(__file__).resolve().parents[3]))
STORAGE_ROOT = Path(os.getenv("VYRAVID_STORAGE", VYRAVID_ROOT / "data" / "storage"))
PUBLIC_BASE = os.getenv("VYRAVID_PUBLIC_BASE", "http://localhost:8000").rstrip("/")
MEDIA_PREFIX = "/media"
GCS_PUBLIC_PREFIX = "https://storage.googleapis.com/"


class GCSError(Exception):
    pass


class GCSUploadError(GCSError):
    pass


class GCSDownloadError(GCSError):
    pass


class GCSBucketError(GCSError):
    pass


class _FakeBlob:
    def __init__(self, path: Path, rel: str, service: "GCSService"):
        self._path = path
        self.name = rel
        self._service = service

    def upload_from_filename(self, filename: str, **kwargs):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(filename, self._path)

    def upload_from_string(self, data: bytes | str, content_type: str = None, **kwargs):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._path.write_bytes(data)

    def download_to_filename(self, filename: str, **kwargs):
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self._path, filename)

    def generate_signed_url(self, **kwargs) -> str:
        return self._service._url(self.name)

    def delete(self):
        if self._path.exists():
            self._path.unlink()

    @property
    def exists(self):
        return self._path.exists()


class _FakeBucket:
    def __init__(self, service: "GCSService"):
        self._service = service
        self.name = "local"

    def blob(self, name: str) -> _FakeBlob:
        return _FakeBlob(self._service._abs(name), name, self._service)


class _FakeClient:
    def __init__(self, service: "GCSService"):
        self._service = service

    def bucket(self, name: str = "local") -> _FakeBucket:
        return _FakeBucket(self._service)


class GCSService:
    def __init__(self):
        STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        self.bucket_name = "local"
        self._temp_dir = Path(tempfile.gettempdir()) / "openvid_processor"
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self._client = _FakeClient(self)
        self._bucket = _FakeBucket(self)

    def is_available(self) -> bool:
        return True

    def can_generate_signed_urls(self) -> bool:
        return True

    @property
    def client(self):
        return self._client

    @property
    def bucket(self):
        return self._bucket

    def _url(self, rel: str) -> str:
        return f"{PUBLIC_BASE}{MEDIA_PREFIX}/{rel.lstrip('/')}"

    def _abs(self, rel: str) -> Path:
        return STORAGE_ROOT / rel.lstrip("/").replace("..", "")

    def _upload_destination(
        self,
        src: str,
        destination_path: str = None,
        gcs_path: str = None,
        content_type: str = None,
        metadata: Dict = None,
        **kwargs,
    ) -> str:
        user_id = kwargs.get("user_id")
        job_id = kwargs.get("job_id") or kwargs.get("project_id")
        filename = kwargs.get("filename")
        file_type = kwargs.get("file_type")

        # Legacy GCS-style call shape:
        # upload_file(local_path, user_id, job_id, filename, file_type)
        if (
            destination_path
            and gcs_path
            and isinstance(content_type, str)
            and isinstance(metadata, str)
        ):
            user_id = destination_path
            job_id = gcs_path
            filename = content_type
            file_type = metadata
            destination_path = None
            gcs_path = None

        if user_id and job_id:
            filename = filename or Path(src).name
            file_type = file_type or "output"
            parts = [str(file_type), str(user_id), str(job_id), str(filename)]
            return "/".join(part.strip("/").replace("..", "") for part in parts if part)

        dest_rel = destination_path or gcs_path
        if dest_rel:
            return dest_rel

        ext = Path(src).suffix or ".mp4"
        return f"processed/{datetime.now(timezone.utc).strftime('%Y%m%d')}/{uuid.uuid4().hex}{ext}"

    def _resolve_local(self, url_or_path: str) -> Optional[Path]:
        if not url_or_path:
            return None
        if os.path.isabs(url_or_path) and os.path.exists(url_or_path):
            return Path(url_or_path)
        path = url_or_path
        if path.startswith(PUBLIC_BASE):
            path = path[len(PUBLIC_BASE) :]
        elif path.startswith(GCS_PUBLIC_PREFIX):
            parts = urlparse(path).path.lstrip("/").split("/", 1)
            if len(parts) == 2:
                p = self._abs(parts[1])
                if p.exists():
                    return p
            return None
        elif path.startswith(("http://", "https://")):
            path = urlparse(path).path
        if path.startswith(MEDIA_PREFIX + "/"):
            rel = path[len(MEDIA_PREFIX) + 1 :]
            p = self._abs(rel)
            if p.exists():
                return p
        # gs://bucket/path
        if path.startswith("gs://"):
            parts = path[5:].split("/", 1)
            if len(parts) == 2:
                p = self._abs(parts[1])
                if p.exists():
                    return p
        p = self._abs(url_or_path)
        if p.exists():
            return p
        return None

    async def download_file(self, url: str, destination: Optional[str] = None) -> str:
        local = self._resolve_local(url)
        if destination is None:
            suffix = Path(urlparse(url).path).suffix or ".bin"
            destination = str(self._temp_dir / f"{uuid.uuid4().hex}{suffix}")
        Path(destination).parent.mkdir(parents=True, exist_ok=True)

        if local and local.exists():
            shutil.copy2(local, destination)
            logger.info("local_copy", src=str(local), dest=destination)
            return destination

        if url.startswith(("gs://", GCS_PUBLIC_PREFIX)):
            raise GCSDownloadError(
                "External Google Cloud Storage URLs are not supported in local mode"
            )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                    if resp.status != 200:
                        raise GCSDownloadError(f"HTTP {resp.status} for {url}")
                    with open(destination, "wb") as f:
                        async for chunk in resp.content.iter_chunked(1024 * 256):
                            f.write(chunk)
            return destination
        except GCSDownloadError:
            raise
        except Exception as e:
            raise GCSDownloadError(f"Failed to download {url}: {e}") from e

    async def download_to_temp(self, url: str) -> str:
        return await self.download_file(url)

    async def upload_file(
        self,
        local_path: str = None,
        destination_path: str = None,
        gcs_path: str = None,
        content_type: str = None,
        metadata: Dict = None,
        make_public: bool = True,
        file_path: str = None,
        **kwargs,
    ) -> Any:
        src = local_path or file_path
        if not src or not os.path.exists(src):
            raise GCSUploadError(f"File not found: {src}")

        dest_rel = self._upload_destination(
            src,
            destination_path=destination_path,
            gcs_path=gcs_path,
            content_type=content_type,
            metadata=metadata,
            **kwargs,
        )

        dest = self._abs(dest_rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        url = self._url(dest_rel)
        logger.info("local_upload", path=dest_rel, url=url)
        # Some callers expect a bare URL string
        return url

    async def upload_final_video(
        self,
        local_path: str,
        user_id: str,
        project_id: str,
        title: str = None,
        language_code: str = None,
        **kwargs,
    ) -> str:
        suffix = Path(local_path).suffix or ".mp4"
        language_part = f"_{language_code}" if language_code else ""
        filename = kwargs.get("filename") or f"final_video_{project_id}{language_part}{suffix}"
        return await self.upload_file(
            local_path=local_path,
            user_id=user_id,
            job_id=project_id,
            filename=filename,
            file_type="output",
            **kwargs,
        )

    async def upload_content(
        self,
        content: str | bytes,
        destination_path: str = None,
        gcs_path: str = None,
        content_type: str = "text/plain",
        user_id: str = "local",
        filename: str = None,
        **kwargs,
    ) -> str:
        data = content.encode("utf-8") if isinstance(content, str) else content

        # Legacy GCS-style call shape:
        # upload_content(content, user_id, job_id, filename, file_type)
        if (
            destination_path
            and gcs_path
            and isinstance(content_type, str)
            and user_id
            and user_id != "local"
            and filename is None
        ):
            actual_user_id = destination_path
            job_id = gcs_path
            actual_filename = content_type
            file_type = user_id
            parts = [str(file_type), str(actual_user_id), str(job_id), str(actual_filename)]
            dest_rel = "/".join(part.strip("/").replace("..", "") for part in parts if part)
        else:
            job_id = kwargs.get("job_id") or kwargs.get("project_id")
            file_type = kwargs.get("file_type")
            if job_id:
                actual_filename = filename or f"{uuid.uuid4().hex}{Path(str(content_type)).suffix or '.txt'}"
                actual_file_type = file_type or "output"
                parts = [str(actual_file_type), str(user_id), str(job_id), str(actual_filename)]
                dest_rel = "/".join(part.strip("/").replace("..", "") for part in parts if part)
            else:
                dest_rel = destination_path or gcs_path
                if not dest_rel:
                    ext = Path(filename).suffix if filename else ".txt"
                    dest_rel = f"content/{user_id}/{uuid.uuid4().hex}{ext}"

        dest = self._abs(dest_rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        logger.info("local_upload_content", path=dest_rel, url=self._url(dest_rel))
        return self._url(dest_rel)

    async def generate_signed_url(
        self,
        gcs_path: str = None,
        blob_name: str = None,
        bucket_name: str = None,
        expiration_hours: int = 24,
        expiration_minutes: int = None,
        **kwargs,
    ) -> str:
        # Support generate_signed_url(bucket, blob) positional style
        path = gcs_path or blob_name or ""
        # If first arg is a bucket name and second arg is the blob path.
        if blob_name and (bucket_name or (gcs_path and "/" not in gcs_path and not gcs_path.startswith(("http", "gs://", MEDIA_PREFIX)))):
            path = blob_name
        if not path:
            return ""
        local = self._resolve_local(path)
        if local and local.exists():
            return self._url(str(local.relative_to(STORAGE_ROOT)))
        if path.startswith(("gs://", GCS_PUBLIC_PREFIX)):
            return ""
        if path.startswith("http"):
            return path
        if path.startswith(MEDIA_PREFIX):
            return f"{PUBLIC_BASE}{path}"
        if path.startswith("gs://"):
            parts = path[5:].split("/", 1)
            path = parts[1] if len(parts) == 2 else path
        return self._url(path)

    async def get_file_info(self, gcs_path_or_url: str) -> Dict[str, Any]:
        local = self._resolve_local(gcs_path_or_url)
        if local and local.exists():
            return {
                "exists": True,
                "size": local.stat().st_size,
                "path": str(local),
                "content_type": "application/octet-stream",
            }
        return {"exists": False}

    def upload_file_sync(self, local_path: str, destination_path: str, **kwargs) -> Dict[str, Any]:
        dest = self._abs(destination_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest)
        url = self._url(destination_path)
        return {
            "gcs_path": destination_path,
            "public_url": url,
            "signed_url": url,
            "url": url,
            "file_size": os.path.getsize(local_path),
        }

    async def file_exists(self, gcs_path: str) -> bool:
        return self._abs(gcs_path).exists()

    async def delete_file(self, gcs_path: str) -> bool:
        p = self._abs(gcs_path)
        if p.exists():
            p.unlink()
            return True
        return False


_gcs_service = None


def get_gcs_service() -> GCSService:
    global _gcs_service
    if _gcs_service is None:
        _gcs_service = GCSService()
    return _gcs_service


async def ensure_valid_signed_url(url: str, expiration_minutes: int = 1440) -> str:
    """Local mode: URLs do not expire; resolve/return a usable media URL."""
    if not url:
        return url
    gcs = get_gcs_service()
    # Already a full URL
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith(MEDIA_PREFIX):
        return f"{PUBLIC_BASE}{url}"
    return await gcs.generate_signed_url(url)
