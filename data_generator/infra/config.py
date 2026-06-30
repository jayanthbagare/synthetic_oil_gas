"""YAML-based configuration loader with typed access and CLI overrides.

Usage:
    from infra.config import load_config
    cfg = load_config()                      # defaults only
    cfg = load_config("config/custom.yaml")  # merge a custom file over defaults
    cfg.override(seed=99, output_dir="./out")

The config is a shallow tree of dicts. Convenience accessors are provided,
but generators may also read nested keys directly via ``cfg.get("sensors.history_days")``.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    import yaml  # PyYAML
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "PyYAML is required for the config system. Install with: pip install pyyaml"
    ) from exc

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "default.yaml"


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge ``overlay`` onto ``base`` (returns a new dict)."""
    out = deepcopy(base)
    for k, v in overlay.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


class Config:
    """Mutable configuration tree."""

    def __init__(self, data: dict) -> None:
        self._data: dict = data

    # -- read access -------------------------------------------------------
    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Fetch a nested value via dotted notation, e.g. ``cfg.get("sensors.history_days")``."""
        node: Any = self._data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def section(self, name: str) -> dict:
        """Return a full top-level section as a plain dict (copy)."""
        return deepcopy(self._data.get(name, {}))

    @property
    def seed(self) -> int:
        return int(self._data.get("seed", 42))

    @property
    def output_dir(self) -> Path:
        return Path(self._data.get("output_dir", "./output"))

    @property
    def raw(self) -> dict:
        return deepcopy(self._data)

    # -- write access ------------------------------------------------------
    def override(self, **kwargs: Any) -> "Config":
        """Override top-level keys (e.g. seed, output_dir). Returns self for chaining."""
        for k, v in kwargs.items():
            if v is not None:
                self._data[k] = v
        return self

    def set(self, dotted_key: str, value: Any) -> "Config":
        """Set a nested value via dotted notation."""
        parts = dotted_key.split(".")
        node = self._data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
        return self

    def __repr__(self) -> str:
        return f"Config(seed={self.seed}, output_dir={self.output_dir})"


def load_config(path: str | Path | None = None) -> Config:
    """Load default config, optionally merged with a user-provided YAML file."""
    data = yaml.safe_load(_DEFAULT_PATH.read_text())
    if path is not None:
        p = Path(path)
        if p.exists():
            user = yaml.safe_load(p.read_text()) or {}
            data = _deep_merge(data, user)
    return Config(data)
