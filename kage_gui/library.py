"""Biblioteca de mirrors: qué hay en la carpeta raíz de kage (~/data/kage).

Sin dependencias de GTK. Un mirror es una carpeta <root>/<host>/ que contiene
index.html y/o _kage/state.json (el estado trae las páginas visitadas).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass
class Mirror:
    name: str           # host, p. ej. "paulgraham.com"
    path: str           # ruta completa a la carpeta del mirror
    size_bytes: int
    pages: int          # páginas visitadas según _kage/state.json (-1 si no hay)
    mtime: float

    @property
    def size_human(self) -> str:
        size = float(self.size_bytes)
        for unit in ("B", "KiB", "MiB", "GiB"):
            if size < 1024 or unit == "GiB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GiB"

    @property
    def subtitle(self) -> str:
        pages = f"{self.pages} páginas" if self.pages >= 0 else "sin estado"
        return f"{pages} · {self.size_human} · {self.path}"


def _dir_size(path: str) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return total


def _visited_pages(mirror_path: str) -> int:
    state = os.path.join(mirror_path, "_kage", "state.json")
    try:
        with open(state, encoding="utf-8") as fh:
            data = json.load(fh)
        visited = data.get("visited")
        return len(visited) if isinstance(visited, list) else -1
    except (OSError, ValueError):
        return -1


def is_mirror(path: str) -> bool:
    return (
        os.path.isfile(os.path.join(path, "index.html"))
        or os.path.isfile(os.path.join(path, "_kage", "state.json"))
    )


def scan_library(root: str) -> list[Mirror]:
    """Mirrors en `root`, del más reciente al más viejo. [] si no existe."""
    if not os.path.isdir(root):
        return []
    mirrors: list[Mirror] = []
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if not os.path.isdir(path) or name.startswith(".") or not is_mirror(path):
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = 0.0
        mirrors.append(Mirror(
            name=name,
            path=path,
            size_bytes=_dir_size(path),
            pages=_visited_pages(path),
            mtime=mtime,
        ))
    mirrors.sort(key=lambda m: m.mtime, reverse=True)
    return mirrors


def free_port() -> int:
    """Un puerto libre en localhost, para no chocar con el 8800 por defecto."""
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
