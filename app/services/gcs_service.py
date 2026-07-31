"""
Local filesystem storage service (GCS-compatible API).

All media is stored under data/storage/ and served at /media/.
"""

from local.storage import LocalStorageService, get_local_storage


class GCSService(LocalStorageService):
    """Alias kept so existing imports continue to work."""

    def __init__(self, *args, **kwargs):
        super().__init__()
        # Some code checks these attributes
        self.settings = type("S", (), {
            "gcs_bucket_name": "local",
            "gcs_project_id": "local",
            "gcs_make_public": True,
        })()



    # Compatibility helpers for code that treats storage like a GCS bucket
    class _Bucket:
        def list_blobs(self, prefix=None, **kwargs):
            root = self.service.storage_root
            prefix = (prefix or "").lstrip("/")
            base = root / prefix if prefix else root
            if not base.exists():
                return []
            results = []
            for path in base.rglob("*"):
                if path.is_file():
                    rel = str(path.relative_to(root))
                    results.append(type("Blob", (), {"name": rel, "size": path.stat().st_size})())
            return results

        def blob(self, name):
            return type("Blob", (), {"name": name})()

    @property
    def bucket(self):
        b = self._Bucket()
        b.service = self
        b.name = "local"
        return b


# Singleton used by modules that import module-level instances
_gcs_service = None


def get_gcs_service() -> GCSService:
    global _gcs_service
    if _gcs_service is None:
        _gcs_service = GCSService()
    return _gcs_service
