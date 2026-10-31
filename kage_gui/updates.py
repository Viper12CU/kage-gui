"""Actualizaciones de kage: consultar la última release en GitHub.

Sin dependencias de GTK. La red se limita a fetch_latest(); el parseo y
la comparación de versiones son funciones puras y testeables sin conexión.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

LATEST_URL = "https://api.github.com/repos/tamnd/kage/releases/latest"
RELEASES_URL = "https://github.com/tamnd/kage/releases"
REPO_URL = "https://github.com/tamnd/kage"
DOCS_URL = "https://kage.tamnd.com"
ISSUES_URL = "https://github.com/tamnd/kage/issues"

# Script de instalación con el repo apt del autor (se ejecuta con pkexec,
# es decir, ya como root: por eso no lleva sudo).
APT_INSTALL_SCRIPT = (
    "set -e; "
    "curl -fsSL https://tamnd.github.io/linux-repo/gpg.key | "
    "gpg --dearmor -o /usr/share/keyrings/tamnd.gpg; "
    "echo 'deb [signed-by=/usr/share/keyrings/tamnd.gpg] "
    "https://tamnd.github.io/linux-repo/apt stable main' "
    "> /etc/apt/sources.list.d/tamnd.list; "
    "apt-get update; apt-get install -y kage"
)

INSTALL_INSTRUCTIONS = """\
Opción 1 — con apt (Debian/Ubuntu), usando el repositorio del autor:

  curl -fsSL https://tamnd.github.io/linux-repo/gpg.key | \\
    sudo gpg --dearmor -o /usr/share/keyrings/tamnd.gpg
  echo "deb [signed-by=/usr/share/keyrings/tamnd.gpg] \\
    https://tamnd.github.io/linux-repo/apt stable main" | \\
    sudo tee /etc/apt/sources.list.d/tamnd.list
  sudo apt update && sudo apt install kage

Opción 2 — descargar el .deb de la última release y:

  sudo apt install ./kage_*_amd64.deb

Opción 3 — con Go instalado:

  go install github.com/tamnd/kage/cmd/kage@latest

Después reinicia Kage GUI (o pulsa «Volver a comprobar»).
"""


@dataclass
class ReleaseInfo:
    version: str            # sin la "v" inicial, p. ej. "0.3.12"
    tag: str                # "v0.3.12"
    url: str                # página de la release
    deb_amd64_url: str      # URL del .deb amd64, o "" si no hay
    notes: str              # cuerpo de la release (markdown)
    published: str          # fecha ISO


def parse_version(text: str) -> tuple[int, ...]:
    """'v0.3.12' / '0.3.12' -> (0, 3, 12). Partes no numéricas cuentan 0."""
    parts = []
    for chunk in text.strip().lstrip("v").split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(latest: str, installed: str) -> bool:
    if not installed:
        return True
    return parse_version(latest) > parse_version(installed)


def parse_release(data: dict) -> ReleaseInfo:
    deb_url = ""
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if name.endswith("_amd64.deb"):
            deb_url = asset.get("browser_download_url", "")
            break
    tag = data.get("tag_name", "")
    return ReleaseInfo(
        version=tag.lstrip("v"),
        tag=tag,
        url=data.get("html_url", RELEASES_URL),
        deb_amd64_url=deb_url,
        notes=(data.get("body") or "").strip(),
        published=data.get("published_at", ""),
    )


def fetch_latest(timeout: float = 12.0) -> ReleaseInfo:
    """Última release publicada. Lanza OSError/URLError si no hay red."""
    request = urllib.request.Request(
        LATEST_URL,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "kage-gui"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return parse_release(json.load(response))
