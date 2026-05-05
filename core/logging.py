import json
import logging
import sys
import time
from typing import Any

from sqlalchemy import event

from core.config import settings

try:
    import axiom_py
    from axiom_py.logging import AxiomHandler

    class SafeAxiomHandler(AxiomHandler):
        def emit(self, record):
            try:
                super().emit(record)
            except Exception as exc:
                print(f"Axiom emit failed: {exc}", file=sys.stderr)
        
        def flush(self):
            try:
                super().flush()
            except Exception as exc:
                print(f"Axiom flush failed: {exc}", file=sys.stderr)

    HAS_AXIOM = True
except ImportError:
    HAS_AXIOM = False


APP_LOGGER_NAME = "futurex"
_AXIOM_HANDLER_ATTACHED = False
_SQL_LOGGING_REGISTERED = False


def configure_logging() -> logging.Logger:
    global _AXIOM_HANDLER_ATTACHED

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if not any(getattr(handler, "_futurex_console", False) for handler in root_logger.handlers):
        console_handler = logging.StreamHandler()
        console_handler._futurex_console = True
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        root_logger.addHandler(console_handler)

    if (
        HAS_AXIOM
        and settings.AXIOM_TOKEN
        and settings.AXIOM_DATASET
        and not _AXIOM_HANDLER_ATTACHED
    ):
        try:
            axiom_client = axiom_py.Client(settings.AXIOM_TOKEN)
            axiom_handler = SafeAxiomHandler(axiom_client, settings.AXIOM_DATASET)
            axiom_handler._futurex_axiom = True
            axiom_handler.setLevel(logging.INFO)
            root_logger.addHandler(axiom_handler)
            _AXIOM_HANDLER_ATTACHED = True
        except Exception:
            root_logger.exception("Failed to initialize Axiom handler")

    return logging.getLogger(APP_LOGGER_NAME)


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)


def log_event(logger: logging.Logger, message: str, **fields: Any) -> None:
    logger.info(message, extra={"event": message, **fields})


def log_exception(logger: logging.Logger, message: str, **fields: Any) -> None:
    logger.exception(message, extra={"event": message, **fields})


def sanitize_headers(headers: Any) -> dict[str, str]:
    redacted_headers = {}
    for key, value in headers.items():
        if key.lower() in {"authorization", "cookie", "set-cookie", "x-api-key"}:
            redacted_headers[key] = "[REDACTED]"
        else:
            redacted_headers[key] = value
    return redacted_headers


def safe_serialize(value: Any, max_length: int = 5000) -> Any:
    if value is None:
        return None

    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
        return _truncate(text, max_length)

    if isinstance(value, (str, int, float, bool)):
        if isinstance(value, str):
            return _truncate(value, max_length)
        return value

    if isinstance(value, dict):
        return {str(key): safe_serialize(item, max_length) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [safe_serialize(item, max_length) for item in value]

    try:
        return _truncate(json.dumps(value, default=str), max_length)
    except Exception:
        return _truncate(repr(value), max_length)


def truncate_for_log(value: Any, max_chars: int) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    return _truncate(text, max_chars)


def serialize_http_body(body: bytes, content_type: str | None, max_length: int = 10000) -> str | None:
    if not body:
        return None

    normalized_type = (content_type or "").lower()
    if any(token in normalized_type for token in ("json", "text", "xml", "form")):
        return safe_serialize(body, max_length)

    return f"[non-text body omitted: {len(body)} bytes]"


def register_sqlalchemy_logging(engine) -> None:
    global _SQL_LOGGING_REGISTERED

    if _SQL_LOGGING_REGISTERED:
        return

    logger = configure_logging().getChild("db")

    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("query_start_time", []).append(time.perf_counter())
        conn.info.setdefault("query_details", []).append(
            {
                "statement": safe_serialize(statement, 10000),
                "parameters": safe_serialize(parameters, 5000),
                "executemany": executemany,
            }
        )

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        started_at = conn.info["query_start_time"].pop()
        details = conn.info["query_details"].pop()
        duration_ms = round((time.perf_counter() - started_at) * 1000, 3)

        log_event(
            logger,
            "db_query",
            statement=details["statement"],
            parameters=details["parameters"],
            executemany=details["executemany"],
            duration_ms=duration_ms,
            rowcount=cursor.rowcount,
        )

    @event.listens_for(engine, "handle_error")
    def handle_error(exception_context):
        conn = exception_context.connection
        duration_ms = None
        details = {
            "statement": safe_serialize(exception_context.statement, 10000),
            "parameters": safe_serialize(exception_context.parameters, 5000),
        }

        if conn is not None:
            start_times = conn.info.get("query_start_time") or []
            query_details = conn.info.get("query_details") or []
            if start_times:
                started_at = start_times.pop()
                duration_ms = round((time.perf_counter() - started_at) * 1000, 3)
            if query_details:
                details.update(query_details.pop())

        log_exception(
            logger,
            "db_query_error",
            statement=details.get("statement"),
            parameters=details.get("parameters"),
            executemany=details.get("executemany"),
            duration_ms=duration_ms,
            error=str(exception_context.original_exception),
        )

    _SQL_LOGGING_REGISTERED = True


def _truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}... [truncated {len(text) - max_length} chars]"
