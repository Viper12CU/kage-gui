"""Miniaturas (preview) de los mirrors para las cards de la Biblioteca.

La preview es una captura real de la página principal del mirror, hecha
con Chrome/Chromium headless sobre el index.html local (los mirrors no
tienen JavaScript, así que el render es fiel y rápido). Se cachean en
~/.cache/kage-gui/thumbs/ con el nombre del host y su fecha: si el mirror
cambia, la miniatura se regenera sola.

Sin dependencias de GTK. Si no hay ningún Chrome disponible, las cards
muestran un marcador en su lugar y la app sigue funcionando.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess

_WIDTH, _HEIGHT = 640, 420


def find_chrome_binary() -> str | None:
    """Chrome/Chromium del sistema, el descargado por kage (go-rod) o $KAGE_CHROME."""
    env = os.environ.get("KAGE_CHROME")
    if env and os.path.isfile(env):
        return env
    for name in ("google-chrome", "google-chrome-stable", "chromium",
                 "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    rod_cache = os.path.expanduser("~/.cache/rod/browser")
    for candidate in sorted(glob.glob(os.path.join(rod_cache, "**", "chrome"),
                                      recursive=True)):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def thumbs_dir(path: str | None = None) -> str:
    if path:
        return path
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "kage-gui", "thumbs")


def thumbnail_file(mirror_path: str, mtime: float, cache: str | None = None) -> str:
    host = os.path.basename(os.path.normpath(mirror_path))
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", host)
    return os.path.join(thumbs_dir(cache), f"{safe}-{int(mtime)}.png")


def generate_thumbnail(mirror_path: str, mtime: float,
                       chrome: str | None = None,
                       cache: str | None = None) -> str | None:
    """Ruta a la miniatura (cacheada o recién generada); None si no se pudo."""
    target = thumbnail_file(mirror_path, mtime, cache)
    if os.path.isfile(target) and os.path.getsize(target) > 0:
        return target
    chrome = chrome or find_chrome_binary()
    index = os.path.join(mirror_path, "index.html")
    if not chrome or not os.path.isfile(index):
        return None
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = target + ".tmp.png"
    cmd = [
        chrome,
        "--headless", "--disable-gpu", "--no-sandbox",
        "--hide-scrollbars", "--force-device-scale-factor=1",
        f"--window-size={_WIDTH},{_HEIGHT}",
        "--virtual-time-budget=5000",
        f"--screenshot={tmp}",
        "file://" + index,
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
        os.replace(tmp, target)
        return target
    return None
