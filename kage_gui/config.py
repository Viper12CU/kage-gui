"""Configuración persistente de la GUI: tema y marcas de primera vez.

Se guarda en ~/.config/kage-gui/config.json (o $XDG_CONFIG_HOME).
Sin dependencias de GTK.
"""

from __future__ import annotations

import json
import os

DEFAULTS = {
    "theme": "system",      # "system" | "light" | "dark"
    "welcomed": False,      # True tras mostrar la bienvenida de primera vez
}

THEMES = ("system", "light", "dark")


def config_path(path: str | None = None) -> str:
    if path:
        return path
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "kage-gui", "config.json")


def load_config(path: str | None = None) -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(config_path(path), encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    if cfg["theme"] not in THEMES:
        cfg["theme"] = "system"
    return cfg


def save_config(cfg: dict, path: str | None = None) -> None:
    target = config_path(path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    clean = {k: cfg.get(k, DEFAULTS[k]) for k in DEFAULTS}
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(clean, fh, indent=2)
