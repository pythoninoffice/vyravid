import json
import logging
import os
import threading
import traceback
from datetime import datetime, timezone
from typing import Any, Dict


_STANDARD_RECORD_FIELDS = {
    "args",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


def _repo_fallback_path() -> str:
    configured = os.getenv("ERROR_LOG_LOCAL_PATH")
    if configured:
        return configured

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    logs_dir = os.path.join(repo_root, "logs")
    try:
        os.makedirs(logs_dir, exist_ok=True)
        return os.path.join(logs_dir, "error_logs.ndjson")
    except Exception:
        return "/tmp/error_logs.ndjson"


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


class PersistentErrorLogHandler(logging.Handler):
    def __init__(self, service_name: str, environment: str) -> None:
        super().__init__(level=logging.ERROR)
        self.service_name = service_name
        self.environment = environment
        self.local_path = _repo_fallback_path()
        self._emit_state = threading.local()

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(self._emit_state, "active", False):
            return

        self._emit_state.active = True
        try:
            payload = self._build_payload(record)
            self._append_to_local_file(payload)
        except Exception:
            pass
        finally:
            self._emit_state.active = False

    def _build_payload(self, record: logging.LogRecord) -> Dict[str, Any]:
        exception_type = None
        exception_message = None
        traceback_text = None

        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            exception_type = exc_type.__name__ if exc_type else None
            exception_message = str(exc_value) if exc_value else None
            traceback_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        elif record.exc_text:
            traceback_text = str(record.exc_text)

        metadata = {
            key: _json_safe(value)
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_FIELDS and not key.startswith("_")
        }

        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "service_name": self.service_name,
            "environment": self.environment,
            "level": record.levelname,
            "logger_name": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function_name": record.funcName,
            "line_no": record.lineno,
            "path": record.pathname,
            "exception_type": exception_type,
            "exception_message": exception_message,
            "traceback": traceback_text,
            "metadata": metadata,
        }

    def _append_to_local_file(self, payload: Dict[str, Any]) -> None:
        directory = os.path.dirname(self.local_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.local_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True))
            handle.write("\n")


def install_persistent_error_logging(service_name: str, environment: str) -> None:
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, PersistentErrorLogHandler):
            return

    handler = PersistentErrorLogHandler(service_name=service_name, environment=environment)
    root_logger.addHandler(handler)
