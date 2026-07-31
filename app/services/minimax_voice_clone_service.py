"""MiniMax voice cloning service."""

from __future__ import annotations

import asyncio
import mimetypes
import os
import re
import uuid
from typing import Any, Dict, Optional

import requests


class MiniMaxVoiceCloneError(Exception):
    """Raised when MiniMax voice cloning fails."""


class MiniMaxVoiceCloneService:
    """Small wrapper around MiniMax file upload, voice clone, and voice delete APIs."""

    API_BASE_URL = "https://api.minimax.io/v1"
    DEFAULT_PREVIEW_TEXT = "Hello, this is a preview of my cloned voice."
    DEFAULT_MODEL = "speech-2.8-turbo"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("MINIMAX_API_KEY")
        if not self.api_key:
            raise MiniMaxVoiceCloneError("Please set MINIMAX_API_KEY environment variable")

    @property
    def headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    @staticmethod
    def generate_voice_id(voice_name: str) -> str:
        """Generate a MiniMax-compatible custom voice ID.

        Rules from MiniMax: 8-256 chars, starts with English letter, contains
        letters/digits/-/_, and cannot end with - or _.
        """
        slug = re.sub(r"[^A-Za-z0-9_-]+", "_", voice_name.strip())
        slug = re.sub(r"[_-]+", "_", slug).strip("_-") or "voice"
        if not slug[0].isalpha():
            slug = f"voice_{slug}"

        unique_suffix = uuid.uuid4().hex[:16]
        voice_id = f"vyravid_{slug}_{unique_suffix}"
        voice_id = voice_id[:256].rstrip("_-")

        if len(voice_id) < 8:
            voice_id = f"{voice_id}_{uuid.uuid4().hex[:8]}"[:256].rstrip("_-")

        return voice_id

    @staticmethod
    def _check_base_resp(payload: Dict[str, Any], action: str) -> None:
        base_resp = payload.get("base_resp") or {}
        status_code = base_resp.get("status_code", 0)
        if status_code != 0:
            status_msg = base_resp.get("status_msg") or "Unknown MiniMax error"
            raise MiniMaxVoiceCloneError(f"MiniMax {action} failed: {status_msg} (code: {status_code})")

    async def upload_audio_file(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        purpose: str = "voice_clone",
        content_type: Optional[str] = None,
    ) -> int:
        """Upload audio bytes to MiniMax and return file_id."""

        def _upload() -> int:
            guessed_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
            files = {"file": (filename, audio_bytes, guessed_type)}
            data = {"purpose": purpose}

            response = requests.post(
                f"{self.API_BASE_URL}/files/upload",
                headers=self.headers,
                files=files,
                data=data,
                timeout=180,
            )
            if response.status_code != 200:
                raise MiniMaxVoiceCloneError(
                    f"MiniMax upload failed ({response.status_code}): {response.text}"
                )

            payload = response.json()
            self._check_base_resp(payload, "upload")
            file_id = (payload.get("file") or {}).get("file_id") or payload.get("file_id")
            if file_id is None:
                raise MiniMaxVoiceCloneError(f"MiniMax upload response missing file_id: {payload}")
            return int(file_id)

        return await asyncio.to_thread(_upload)

    async def clone_voice(
        self,
        *,
        voice_name: str,
        audio_bytes: bytes,
        filename: str,
        content_type: Optional[str] = None,
        description: Optional[str] = None,
        preview_text: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        voice_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Clone a voice through MiniMax and return metadata."""
        try:
            source_file_id = await self.upload_audio_file(
                audio_bytes=audio_bytes,
                filename=filename,
                purpose="voice_clone",
                content_type=content_type,
            )
            minimax_voice_id = voice_id or self.generate_voice_id(voice_name)
            text = (preview_text or description or self.DEFAULT_PREVIEW_TEXT)[:1000]

            def _clone() -> Dict[str, Any]:
                payload = {
                    "file_id": source_file_id,
                    "voice_id": minimax_voice_id,
                    "text": text,
                    "model": model,
                    "need_noise_reduction": True,
                    "need_volume_normalization": True,
                }

                response = requests.post(
                    f"{self.API_BASE_URL}/voice_clone",
                    headers={**self.headers, "Content-Type": "application/json"},
                    json=payload,
                    timeout=300,
                )
                if response.status_code != 200:
                    raise MiniMaxVoiceCloneError(
                        f"MiniMax voice cloning failed ({response.status_code}): {response.text}"
                    )

                result = response.json()
                self._check_base_resp(result, "voice clone")
                return result

            result = await asyncio.to_thread(_clone)
            return {
                "success": True,
                "voice_id": minimax_voice_id,
                "name": voice_name,
                "file_id": source_file_id,
                "demo_audio": result.get("demo_audio"),
                "raw_response": result,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def delete_cloned_voice(self, voice_id: str) -> bool:
        """Delete a MiniMax cloned voice."""

        def _delete() -> bool:
            response = requests.post(
                f"{self.API_BASE_URL}/delete_voice",
                headers={**self.headers, "Content-Type": "application/json"},
                json={"voice_type": "voice_cloning", "voice_id": voice_id},
                timeout=120,
            )
            if response.status_code != 200:
                return False
            payload = response.json()
            self._check_base_resp(payload, "delete voice")
            return True

        try:
            return await asyncio.to_thread(_delete)
        except Exception:
            return False


def get_minimax_voice_clone_service() -> MiniMaxVoiceCloneService:
    return MiniMaxVoiceCloneService()
