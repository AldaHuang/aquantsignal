"""Configuration — YAML file at ~/.aquant/config.yaml. Auto-created on first run."""

import os
import yaml
from pathlib import Path

DEFAULTS = {
    "data": {
        "cache_dir": "~/.aquant/cache",
        "default_adjust": "qfq",
    },
    "backtest": {
        "initial_cash": 50_000,
        "commission": 0.0003,
        "stamp_duty": 0.001,
        "min_commission": 5.0,
        "fill_at": "next_open",
    },
}

_cfg = None


def _path():
    return Path(os.path.expanduser("~/.aquant/config.yaml"))


def load():
    """Return merged config dict (defaults + file overrides). Cached after first read."""
    global _cfg
    if _cfg is not None:
        return _cfg

    path = _path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(DEFAULTS, f, allow_unicode=True)
        _cfg = dict(DEFAULTS)
        return _cfg

    with open(path) as f:
        loaded = yaml.safe_load(f) or {}

    # Shallow merge: loaded top-level keys override defaults
    merged = dict(DEFAULTS)
    for section in merged:
        if section in loaded and isinstance(loaded[section], dict):
            merged[section].update(loaded[section])
    _cfg = merged
    return merged


def get(key_path, default=None):
    """Get nested key: 'backtest.initial_cash'."""
    keys = key_path.split(".")
    node = load()
    for k in keys:
        if isinstance(node, dict):
            node = node.get(k)
        else:
            return default
    return node if node is not None else default
