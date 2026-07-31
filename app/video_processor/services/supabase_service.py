"""
Local SQLite-backed project updates for the video processor.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)

VYRAVID_ROOT = Path(os.getenv("VYRAVID_ROOT", Path(__file__).resolve().parents[2]))
DB_PATH = Path(os.getenv("VYRAVID_DB", VYRAVID_ROOT / "data" / "db" / "openvid.sqlite3"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalProjectStore:
    def __init__(self):
        self.db_path = DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def is_available(self) -> bool:
        return True

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    async def update_project_status(
        self,
        project_id: str,
        status: str,
        **fields,
    ) -> bool:
        try:
            conn = self._conn()
            data = {"status": status, "updated_at": _now()}
            for k, v in fields.items():
                if isinstance(v, (dict, list)):
                    data[k] = json.dumps(v)
                else:
                    data[k] = v
            # ensure columns exist loosely
            existing = {r[1] for r in conn.execute('PRAGMA table_info("video_projects")').fetchall()}
            for k in list(data.keys()):
                if k not in existing:
                    try:
                        conn.execute(f'ALTER TABLE video_projects ADD COLUMN "{k}" TEXT')
                    except sqlite3.OperationalError:
                        pass
            sets = ", ".join(f'"{k}" = ?' for k in data)
            conn.execute(
                f'UPDATE video_projects SET {sets} WHERE id = ?',
                list(data.values()) + [str(project_id)],
            )
            conn.commit()
            conn.close()
            logger.info("project_status_updated", project_id=project_id, status=status)
            return True
        except Exception as e:
            logger.error("project_status_update_failed", error=str(e))
            return False

    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        try:
            conn = self._conn()
            row = conn.execute(
                "SELECT * FROM video_projects WHERE id = ?", (str(project_id),)
            ).fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error("get_project_failed", error=str(e))
            return None

    async def update_project(self, project_id: str, data: Dict[str, Any]) -> bool:
        try:
            conn = self._conn()
            payload = dict(data)
            payload["updated_at"] = _now()
            encoded = {}
            for k, v in payload.items():
                if isinstance(v, (dict, list)):
                    encoded[k] = json.dumps(v)
                else:
                    encoded[k] = v
            existing = {r[1] for r in conn.execute('PRAGMA table_info("video_projects")').fetchall()}
            for k in list(encoded.keys()):
                if k not in existing:
                    try:
                        conn.execute(f'ALTER TABLE video_projects ADD COLUMN "{k}" TEXT')
                    except sqlite3.OperationalError:
                        pass
            sets = ", ".join(f'"{k}" = ?' for k in encoded)
            conn.execute(
                f'UPDATE video_projects SET {sets} WHERE id = ?',
                list(encoded.values()) + [str(project_id)],
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error("update_project_failed", error=str(e))
            return False

    async def update_video_project(self, project_id: str, data: Dict[str, Any]) -> bool:
        """Alias used by some processor completion paths."""
        return await self.update_project(project_id, data)

    async def update_project_with_completion(
        self,
        project_id: str,
        video_url: str,
        signed_url: str,
        file_size: int = 0,
        duration: float = 0.0,
        processing_time_seconds: float = 0.0,
    ) -> bool:
        """Compatibility method for processor completion updates."""
        now = _now()
        return await self.update_project(project_id, {
            "status": "completed",
            "completed_at": now,
            "gcs_path": video_url,
            "gcs_signed_url": signed_url,
            "file_size": file_size,
            "duration": duration,
            "processing_time_seconds": processing_time_seconds,
        })

    async def update_project_with_failure(
        self,
        project_id: str,
        error_message: str,
        processing_time_seconds: float = 0.0,
    ) -> bool:
        """Compatibility method for processor failure updates."""
        return await self.update_project(project_id, {
            "status": "failed",
            "error_message": error_message,
            "processing_time_seconds": processing_time_seconds,
        })


SupabaseService = LocalProjectStore

_project_store: Optional[LocalProjectStore] = None


def get_supabase_service() -> LocalProjectStore:
    """Compatibility factory for legacy imports."""
    global _project_store
    if _project_store is None:
        _project_store = LocalProjectStore()
    return _project_store
