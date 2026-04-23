from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from app.core.request_context import get_request_id


_SKIP_RECORD_FIELDS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
}


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()
        return True


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }

        extras: dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key in _SKIP_RECORD_FIELDS or key == "request_id":
                continue
            extras[key] = self._to_jsonable(value)
        if extras:
            payload["extra"] = extras

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)

    def _to_jsonable(self, value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (list, tuple)):
            return [self._to_jsonable(item) for item in value]
        if isinstance(value, dict):
            return {str(k): self._to_jsonable(v) for k, v in value.items()}
        return str(value)


def setup_logging(
    level: str = "INFO",
    *,
    json_logs: bool = True,
    log_to_file: bool = True,
    logs_dir: Path | None = None,
    file_name: str = "application.log",
    max_bytes: int = 5_000_000,
    backup_count: int = 3,
) -> None:
    normalized = (level or "INFO").upper()
    log_level = getattr(logging, normalized, logging.INFO)

    formatter: logging.Formatter
    if json_logs:
        formatter = JsonLogFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(log_level)

    context_filter = RequestContextFilter()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(context_filter)
    root_logger.addHandler(console_handler)

    if log_to_file and logs_dir:
        logs_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            filename=logs_dir / file_name,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(context_filter)
        root_logger.addHandler(file_handler)

    logging.getLogger("backend").setLevel(log_level)
    # Evita duplicado de access logs default de uvicorn. El tracking queda en middleware.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # Evita ruido de cliente HTTP interno (ej: TestClient/httpx).
    logging.getLogger("httpx").setLevel(logging.WARNING)

