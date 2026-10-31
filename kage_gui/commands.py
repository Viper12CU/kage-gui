"""Construcción de comandos de kage y detección del binario.

Este módulo no depende de GTK: es lógica pura y se puede testear sin GUI.
La GUI nunca escribe comandos como texto para una shell; siempre construye
listas de argumentos que se pasan a subprocess sin shell=True. Así una URL
con caracteres raros no puede inyectar nada.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field

DEFAULT_OUT_ROOT = os.path.expanduser("~/data/kage")
DEFAULT_ADDR = "127.0.0.1:8800"


def find_kage() -> str | None:
    """Devuelve la ruta al binario kage, o None si no está instalado."""
    path = shutil.which("kage")
    if path:
        return path
    # Sitios típicos cuando se instala a mano desde el .tar.gz de releases.
    for candidate in ("~/.local/bin/kage", "~/bin/kage", "/usr/local/bin/kage"):
        full = os.path.expanduser(candidate)
        if os.path.isfile(full) and os.access(full, os.X_OK):
            return full
    return None


def kage_version(kage_bin: str) -> str:
    """'kage version 0.3.12' -> '0.3.12'. Vacío si algo falla."""
    try:
        out = subprocess.run(
            [kage_bin, "--version"],
            capture_output=True, text=True, timeout=5,
        )
        parts = (out.stdout or out.stderr).strip().split()
        return parts[-1] if parts else ""
    except (OSError, subprocess.SubprocessError):
        return ""


@dataclass
class CloneOptions:
    url: str
    out_root: str = DEFAULT_OUT_ROOT
    max_pages: int = 0          # 0 = sin límite
    max_depth: int = 0          # 0 = sin límite
    scope_prefix: str = ""
    exclude: list[str] = field(default_factory=list)
    subdomains: bool = False
    scroll: bool = False
    refresh: bool = False
    force: bool = False
    workers: int = 4
    chrome: str = ""            # ruta a Chrome/Chromium, si no es el del sistema


def build_clone_command(kage_bin: str, opts: CloneOptions) -> list[str]:
    """`kage clone <url>` con solo los flags que se apartan del defecto."""
    cmd = [kage_bin, "clone", opts.url, "--out", opts.out_root]
    if opts.max_pages > 0:
        cmd += ["--max-pages", str(opts.max_pages)]
    if opts.max_depth > 0:
        cmd += ["--max-depth", str(opts.max_depth)]
    if opts.scope_prefix:
        cmd += ["--scope-prefix", opts.scope_prefix]
    for path in opts.exclude:
        if path:
            cmd += ["--exclude", path]
    if opts.subdomains:
        cmd.append("--subdomains")
    if opts.scroll:
        cmd.append("--scroll")
    if opts.refresh:
        cmd.append("--refresh")
    if opts.force:
        cmd.append("--force")
    if opts.workers != 4:
        cmd += ["--workers", str(opts.workers)]
    if opts.chrome:
        cmd += ["--chrome", opts.chrome]
    return cmd


def build_serve_command(kage_bin: str, mirror_dir: str, addr: str = DEFAULT_ADDR) -> list[str]:
    return [kage_bin, "serve", mirror_dir, "--addr", addr]


def build_open_command(kage_bin: str, zim_path: str, addr: str = DEFAULT_ADDR) -> list[str]:
    # --open=false: la GUI decide cuándo abrir el navegador, no kage.
    return [kage_bin, "open", zim_path, "--addr", addr, "--open=false"]


def build_pack_command(
    kage_bin: str,
    mirror_dir: str,
    fmt: str = "zim",           # "zim" | "binary"
    out_path: str = "",
    app: bool = False,
) -> list[str]:
    cmd = [kage_bin, "pack", mirror_dir, "--format", fmt]
    if out_path:
        cmd += ["--out", out_path]
    if app:
        cmd.append("--app")
    return cmd


def default_pack_output(mirror_dir: str, fmt: str = "zim", app: bool = False) -> str:
    """Dónde va a parar un pack si no se elige salida (regla de kage).

    zim    -> <host>.zim junto a la carpeta raíz de mirrors
    binary -> <host> (ejecutable) en la misma raíz
    app    -> <host>.AppDir en la misma raíz
    """
    host = os.path.basename(os.path.normpath(mirror_dir))
    root = os.path.dirname(os.path.normpath(mirror_dir))
    if fmt == "zim":
        return os.path.join(root, host + ".zim")
    if app:
        return os.path.join(root, host + ".AppDir")
    return os.path.join(root, host)
