"""Structured logging setup for the generator and agent layer.

Replaces ad-hoc ``print()`` calls with a configured logger that can emit
either human-readable (plain) or machine-parseable (structured JSON) records.

Usage:
    from infra.logging_setup import get_logger
    log = get_logger(__name__)
    log.info("Generated assets", extra={"rows": 500, "phase": "assets"})
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

_CONFIGURED = False


class _StructuredFormatter(logging.Formatter):
    """Emits one JSON object per log record for machine consumption."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Pull known extra fields
        for key in ("rows", "phase", "seed", "entity", "elapsed_s", "event"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", fmt: str = "structured") -> None:
    """Configure the root logger. Safe to call multiple times."""
    global _CONFIGURED
    root = logging.getLogger()

    # Clear previous handlers to make reconfiguration idempotent
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler()
    if fmt == "structured":
        handler.setFormatter(_StructuredFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                              datefmt="%Y-%m-%d %H:%M:%S")
        )
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger, configuring the root once on first use."""
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(name)
