"""
Local filesystem storage that mimics GCSService method signatures.

URLs returned look like /media/<relative_path> and are served by FastAPI StaticFiles.
Field names keep gcs_path / gcs_signed_url for compatibility with existing code.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from local.constants import STORAGE_ROOT, MEDIA_URL_PREFIX

logger = logging.getLogger(__name__)
GCS_PUBLIC_PREFIX = "https://storage.googleapis.com/"


class LocalStorageService:
    """GCS-compatible local storage."""

    def __init__(self, storage_root: Path = STORAGE_ROOT, public_base: Optional[str] = None):
        self.storage_root = Path(storage_root)
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=4)
        # Optional absolute base like http://localhost:8000 for signed URLs used by ffmpeg downloads
        self.public_base = (public_base or os.getenv("VYRAVID_PUBLIC_BASE", "http://localhost:8000")).rstrip("/")
        self.bucket_name = "local"
        self.client = True  # truthy for is_available checks
        self._bucket = True  # subclasses may override with a @property named bucket

    def is_available(self) -> bool:
        return True

    def _abs(self, rel: str) -> Path:
        # Normalize and prevent path escape
        rel = rel.lstrip("/").replace("..", "")
        return self.storage_root / rel

    def _url(self, rel: str, absolute: bool = True) -> str:
        rel = rel.lstrip("/")
        path = f"{MEDIA_URL_PREFIX}/{rel}"
        if absolute:
            return f"{self.public_base}{path}"
        return path

    def path_from_url(self, url: str) -> Optional[Path]:
        """Resolve a /media/... or public URL back to a local file."""
        if not url:
            return None
        if url.startswith(self.public_base):
            url = url[len(self.public_base):]
        elif url.startswith(GCS_PUBLIC_PREFIX):
            parts = urlparse(url).path.lstrip("/").split("/", 1)
            if len(parts) == 2:
                p = self._abs(parts[1])
                return p if p.exists() else None
            return None
        elif url.startswith("gs://"):
            parts = url[5:].split("/", 1)
            if len(parts) == 2:
                p = self._abs(parts[1])
                return p if p.exists() else None
            return None
        if url.startswith(MEDIA_URL_PREFIX + "/"):
            rel = url[len(MEDIA_URL_PREFIX) + 1:]
            p = self._abs(rel)
            return p if p.exists() else None
        # Maybe it's already a relative storage path
        p = self._abs(url)
        if p.exists():
            return p
        # Absolute filesystem path
        if os.path.isabs(url) and os.path.exists(url):
            return Path(url)
        return None

    def resolve_to_local_path(self, url_or_path: str) -> Optional[str]:
        p = self.path_from_url(url_or_path)
        return str(p) if p else (url_or_path if os.path.exists(url_or_path) else None)

    async def get_video_info(self, gcs_path: str) -> Optional[Dict[str, Any]]:
        """Return local file metadata for GCS-compatible video lookups."""
        p = self.path_from_url(gcs_path)
        if not p:
            return None

        stat = p.stat()
        content_type = mimetypes.guess_type(str(p))[0] or "video/mp4"
        rel = str(p.relative_to(self.storage_root))
        return {
            "name": rel,
            "size": stat.st_size,
            "content_type": content_type,
            "updated": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "url": self._url(rel),
        }

    def is_signed_url_expired(self, url: str, buffer_minutes: int = 60) -> bool:
        """Local /media URLs do not expire; preserve GCS compatibility for callers."""
        if not url:
            return True
        if self.path_from_url(url):
            return False

        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        date_values = qs.get("X-Goog-Date")
        expires_values = qs.get("X-Goog-Expires")
        if not date_values or not expires_values:
            return False

        try:
            signed_at = datetime.strptime(date_values[0], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            expires_at = signed_at + timedelta(seconds=int(expires_values[0]))
            return datetime.now(timezone.utc) + timedelta(minutes=buffer_minutes) >= expires_at
        except (TypeError, ValueError):
            return False

    def is_url_expired_or_expiring_soon(self, url_or_expires_at: Any, buffer_hours: int = 1) -> bool:
        """Compatibility alias used by older GCS-backed project endpoints.

        Some callers pass the signed URL, while others pass its expires_at value.
        Local /media URLs do not expire, but missing/expired timestamps should
        still trigger URL regeneration.
        """
        if not url_or_expires_at:
            return True
        if isinstance(url_or_expires_at, datetime):
            return datetime.now(timezone.utc) + timedelta(hours=buffer_hours) >= url_or_expires_at
        if isinstance(url_or_expires_at, str):
            try:
                expires_at = datetime.fromisoformat(url_or_expires_at.replace("Z", "+00:00"))
                return datetime.now(timezone.utc) + timedelta(hours=buffer_hours) >= expires_at
            except ValueError:
                return self.is_signed_url_expired(url_or_expires_at, buffer_minutes=buffer_hours * 60)
        return False

    def _write_bytes(self, rel: str, content: bytes) -> str:
        dest = self._abs(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return rel

    def _copy_file(self, local_file_path: str, rel: str) -> str:
        dest = self._abs(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_file_path, dest)
        return rel

    async def upload_video(
        self,
        local_file_path: str,
        user_id: str,
        video_title: str = None,
        metadata: Dict[str, Any] = None,
    ) -> Optional[Dict[str, Any]]:
        if not os.path.exists(local_file_path):
            logger.error(f"Local file not found: {local_file_path}")
            return None
        try:
            ext = Path(local_file_path).suffix or ".mp4"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            gcs_filename = f"videos/{user_id}/{timestamp}_{unique_id}{ext}"
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self.executor, self._copy_file, local_file_path, gcs_filename)
            url = self._url(gcs_filename)
            return {
                "gcs_path": gcs_filename,
                "public_url": url,
                "signed_url": url,
                "bucket_name": self.bucket_name,
                "file_size": os.path.getsize(local_file_path),
                "uploaded_at": datetime.now().isoformat(),
                "metadata": metadata or {},
            }
        except Exception as e:
            logger.error(f"Error uploading video: {e}")
            return None

    async def upload_user_watermark(self, local_file_path: str, user_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        ext = Path(local_file_path).suffix or ".png"
        rel = f"watermarks/{user_id}/logo{ext}"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, self._copy_file, local_file_path, rel)
        url = self._url(rel)
        return {"gcs_path": rel, "public_url": url, "signed_url": url}

    async def delete_user_watermarks(self, user_id: str) -> bool:
        d = self._abs(f"watermarks/{user_id}")
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        return True

    async def upload_avatar(self, file_content: bytes, user_id: str, content_type: str = "image/png", **kwargs) -> Optional[Dict[str, Any]]:
        ext = mimetypes.guess_extension(content_type) or ".png"
        rel = f"avatars/{user_id}/avatar{ext}"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, self._write_bytes, rel, file_content)
        url = self._url(rel)
        return {"public_url": url, "signed_url": url, "blob_name": rel, "gcs_path": rel}

    async def delete_avatar(self, user_id: str) -> bool:
        d = self._abs(f"avatars/{user_id}")
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        return True

    async def delete_file(self, gcs_path: str) -> bool:
        p = self._abs(gcs_path)
        if p.exists():
            p.unlink()
            return True
        return False

    async def delete_video(self, gcs_path: str) -> bool:
        return await self.delete_file(gcs_path)

    async def generate_signed_url(
        self,
        gcs_path: str,
        expiration_hours: int = 24,
        method: str = "GET",
        **kwargs,
    ) -> Optional[str]:
        if not gcs_path:
            return None
        local = self.path_from_url(gcs_path)
        if local:
            return self._url(str(local.relative_to(self.storage_root)))
        if gcs_path.startswith(("gs://", GCS_PUBLIC_PREFIX)):
            return None
        # Already a URL
        if gcs_path.startswith("http://") or gcs_path.startswith("https://") or gcs_path.startswith(MEDIA_URL_PREFIX):
            return gcs_path if gcs_path.startswith("http") else f"{self.public_base}{gcs_path}"
        return self._url(gcs_path)

    async def upload_audio_bytes(
        self,
        audio_bytes: bytes,
        user_id: str,
        filename: str = None,
        content_type: str = "audio/wav",
        file_extension: str = None,
        audio_id: str = None,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        if file_extension:
            ext = file_extension if file_extension.startswith(".") else f".{file_extension}"
        elif filename:
            ext = Path(filename).suffix or ".wav"
        else:
            ext = ".wav"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = (audio_id or str(uuid.uuid4()))[:36]
        # Keep a stable name when audio_id is the project id (overwrite)
        if audio_id:
            rel = f"audio/{user_id}/{audio_id}{ext}"
        else:
            rel = f"audio/{user_id}/{timestamp}_{unique_id[:8]}{ext}"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, self._write_bytes, rel, audio_bytes)
        url = self._url(rel)
        return {
            "gcs_path": rel,
            "public_url": url,
            "signed_url": url,
            "file_size": len(audio_bytes),
            "uploaded_at": datetime.now().isoformat(),
        }

    async def upload_video_bytes(
        self,
        video_bytes: bytes,
        user_id: str,
        filename: str = None,
        content_type: str = "video/mp4",
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        ext = Path(filename).suffix if filename else ".mp4"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        rel = f"videos/{user_id}/{timestamp}_{unique_id}{ext}"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, self._write_bytes, rel, video_bytes)
        url = self._url(rel)
        return {
            "gcs_path": rel,
            "public_url": url,
            "signed_url": url,
            "file_size": len(video_bytes),
            "uploaded_at": datetime.now().isoformat(),
        }

    async def upload_file_to_path(
        self,
        local_file_path: str,
        gcs_path: str,
        content_type: str = None,
        metadata: Dict = None,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        if not os.path.exists(local_file_path):
            return None
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, self._copy_file, local_file_path, gcs_path)
        url = self._url(gcs_path)
        return {
            "gcs_path": gcs_path,
            "public_url": url,
            "signed_url": url,
            "file_size": os.path.getsize(local_file_path),
        }

    async def upload_image(
        self,
        local_file_path: str = None,
        image_bytes: bytes = None,
        user_id: str = "local",
        filename: str = None,
        content_type: str = "image/png",
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        ext = Path(filename).suffix if filename else (mimetypes.guess_extension(content_type) or ".png")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        rel = f"images/{user_id}/{timestamp}_{unique_id}{ext}"
        loop = asyncio.get_event_loop()
        if local_file_path:
            await loop.run_in_executor(self.executor, self._copy_file, local_file_path, rel)
            size = os.path.getsize(local_file_path)
        elif image_bytes:
            await loop.run_in_executor(self.executor, self._write_bytes, rel, image_bytes)
            size = len(image_bytes)
        else:
            return None
        url = self._url(rel)
        thumb_rel = rel  # same for local simplicity
        return {
            "gcs_path": rel,
            "public_url": url,
            "signed_url": url,
            "thumbnail_gcs_path": thumb_rel,
            "thumbnail_signed_url": url,
            "file_size": size,
            "uploaded_at": datetime.now().isoformat(),
        }

    async def delete_image(self, gcs_path: str, thumbnail_path: str = None) -> bool:
        ok = await self.delete_file(gcs_path)
        if thumbnail_path:
            await self.delete_file(thumbnail_path)
        return ok

    async def upload_content(
        self,
        content: str,
        user_id: str,
        job_id: str = None,
        filename: str = None,
        file_type: str = "output",
        content_type: str = "text/plain",
        **kwargs,
    ):
        """
        Upload text/binary content.

        Compatible with both call styles:
          upload_content(content, user_id, job_id, filename, "output")  # original GCS
          upload_content(content, user_id, filename="x.txt")            # simple
        Returns URL string (original GCS contract) for the 5-arg form,
        or a dict for the simple form when job_id is omitted and filename kw used oddly.
        """
        data = content.encode("utf-8") if isinstance(content, str) else content

        # Original GCS signature: (content, user_id, job_id, filename, file_type)
        if job_id is not None and filename is not None:
            rel = f"{file_type}/{user_id}/{job_id}/{filename}"
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self.executor, self._write_bytes, rel, data)
            return self._url(rel)

        # Simple fallback
        fname = filename or kwargs.get("filename") or "content.txt"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        ext = Path(fname).suffix or ".txt"
        rel = f"content/{user_id}/{timestamp}_{unique_id}{ext}"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, self._write_bytes, rel, data)
        url = self._url(rel)
        return {"gcs_path": rel, "public_url": url, "signed_url": url, "file_size": len(data)}

    async def download_file(self, url_or_path: str, destination: str = None) -> str:
        """Copy a storage object or /media URL to destination (or a temp file)."""
        local = self.path_from_url(url_or_path) or self._abs(url_or_path.lstrip("/"))
        if not local.exists() and not os.path.isabs(url_or_path):
            # try as relative storage path
            local = self._abs(url_or_path)
        if not local.exists():
            raise FileNotFoundError(f"Storage object not found: {url_or_path}")
        if destination is None:
            import tempfile
            suffix = local.suffix or ".bin"
            fd, destination = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local, destination)
        return destination

    def read_text(self, gcs_path_or_url: str) -> str:
        """Read text content from local storage."""
        local = self.path_from_url(gcs_path_or_url) or self._abs(str(gcs_path_or_url).lstrip("/"))
        if not local.exists():
            raise FileNotFoundError(f"Not found: {gcs_path_or_url}")
        return local.read_text(encoding="utf-8")

    # Sync helpers used by video processor
    def upload_file_sync(self, local_file_path: str, gcs_filename: str, metadata: Dict = None) -> Dict[str, Any]:
        self._copy_file(local_file_path, gcs_filename)
        url = self._url(gcs_filename)
        return {
            "gcs_path": gcs_filename,
            "public_url": url,
            "signed_url": url,
            "file_size": os.path.getsize(local_file_path),
        }

    def download_to_path(self, gcs_path_or_url: str, dest: str) -> str:
        src = self.path_from_url(gcs_path_or_url)
        if src is None:
            # try as relative path
            src = self._abs(gcs_path_or_url)
        if not src.exists():
            raise FileNotFoundError(f"Cannot find storage object: {gcs_path_or_url}")
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return dest


_storage: Optional[LocalStorageService] = None


def get_local_storage() -> LocalStorageService:
    global _storage
    if _storage is None:
        _storage = LocalStorageService()
    return _storage
