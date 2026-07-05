"""Logging configuration.

Every log event is rendered as JSON to stdout AND appended, in a compact
human-readable form, to a per-run trace file (`settings.trace_path`). The trace
file is truncated at the start of each run by `configure()`, so after any run it
contains the full behind-the-scenes trace of exactly what happened: every browser
navigation, DOM extraction count, LLM call, tool invocation, and timing.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
import structlog.contextvars

from config.settings import settings

# Verbatim tool payloads (LLM tool inputs/outputs) are capped to this many chars in
# the trace file so a single huge job description can't bloat the log unboundedly.
_PAYLOAD_MAX_CHARS = 20000

# Keys handled positionally in each trace line — everything else is appended as key=val.
_TRACE_HEADER_KEYS = ("timestamp", "level", "event")


def _trace_file_processor(_logger: Any, _method: str, event_dict: dict) -> dict:
    """structlog processor: append a readable line to the trace file, pass event through."""
    ts = str(event_dict.get("timestamp", ""))
    level = str(event_dict.get("level", _method)).upper()
    event = str(event_dict.get("event", ""))
    extras = " ".join(f"{k}={event_dict[k]}" for k in event_dict if k not in _TRACE_HEADER_KEYS)
    line = f"{ts}  {level:<7} {event:<34} {extras}".rstrip() + "\n"
    try:
        with open(settings.trace_path, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        # Never let trace-file I/O break the pipeline.
        pass
    return event_dict


def trace_payload(label: str, data: Any) -> None:
    """Append a verbatim tool input/output block to the trace file only (not stdout).

    `data` may be a dict/list (pretty-printed as JSON) or a string (pretty-printed if it
    parses as JSON, otherwise written as-is). Capped to `_PAYLOAD_MAX_CHARS`.
    """
    try:
        if isinstance(data, (dict, list)):
            body = json.dumps(data, ensure_ascii=False, indent=2)
        else:
            body = str(data)
            if body.strip()[:1] in ("{", "["):
                try:
                    body = json.dumps(json.loads(body), ensure_ascii=False, indent=2)
                except Exception:
                    pass
        if len(body) > _PAYLOAD_MAX_CHARS:
            dropped = len(body) - _PAYLOAD_MAX_CHARS
            body = body[:_PAYLOAD_MAX_CHARS] + f"\n… [truncated {dropped} chars]"
        block = f"\n    ──── RAW: {label} ────\n{body}\n    ──── END RAW ────\n\n"
        with open(settings.trace_path, "a", encoding="utf-8") as fh:
            fh.write(block)
    except Exception:
        # Never let trace-file I/O break the pipeline.
        pass


def configure() -> None:
    # Truncate the trace file at the start of every run and write a header.
    trace = Path(settings.trace_path)
    trace.parent.mkdir(parents=True, exist_ok=True)
    trace.write_text(
        f"# Execution trace — run started {datetime.now(timezone.utc).isoformat()}\n"
        f"# Format: <timestamp>  <LEVEL>  <event>  <key=value ...>\n\n",
        encoding="utf-8",
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _trace_file_processor,  # tee to trace file (must run before JSONRenderer)
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)
