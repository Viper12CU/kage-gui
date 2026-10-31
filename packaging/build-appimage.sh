#!/usr/bin/env bash
# Construye kage-gui-<VERSION>.AppImage SIN appimage-builder.
#
# Por qué a mano: appimage-builder (1.1.0, sin mantenimiento desde 2022)
# rompió tres veces seguidas contra el entorno moderno de CI (clave GPG
# de ejemplo obsoleta, packaging>=22 sin LegacyVersion, su propio venv
# de apt). Este script usa solo piezas aburridas y mantenidas: apt del
# propio runner (Ubuntu 22.04 = jammy, el denominador glibc que busca-
# mos), dpkg -x para extraer los .deb en el AppDir y appimagetool
# oficial para empaquetar. Sin receta, sin keyserver, sin Python de por
# medio comparando versiones.
#
# El AppImage incluye kage: el script descarga la última release
# oficial (o la fijada en KAGE_VERSION) y verifica su sha256.
# Ejecutable autocontenido, sin instalar nada.
#
# Uso:  VERSION=1.0.0 bash packaging/build-appimage.sh
# Si VERSION no viene del entorno, se lee de kage_gui/__init__.py.
set -euo pipefail

cd "$(dirname "$0")/.."

VERSION="${VERSION:-$(sed -n "s/^__version__ = [\"']\(.*\)[\"']/\1/p" kage_gui/__init__.py)}"
if [ -z "$VERSION" ]; then
  echo "ERROR: no se pudo determinar la versión" >&2
  exit 1
fi

APPDIR="$PWD/AppDir"
WORKDIR="$PWD/.appimage-build"
DEBDIR="$WORKDIR/debs"
MULTIARCH="$(dpkg-architecture -q DEB_HOST_MULTIARCH 2>/dev/null || echo x86_64-linux-gnu)"
APPIMAGETOOL="${APPIMAGETOOL:-appimagetool}"
export APPIMAGE_EXTRACT_AND_RUN=1

if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi
APT_OPTS="${APT_OPTS:-}"

# Paquetes cuyo cierre de dependencias forma el runtime empaquetado.
PKGS="python3 python3-gi gir1.2-gtk-4.0 adwaita-icon-theme hicolor-icon-theme librsvg2-common"

echo "== AppImage manual: kage-gui-$VERSION.AppImage (multiarch $MULTIARCH) =="

# --- 1. Esqueleto del AppDir y archivos propios (igual que la receta) ---
rm -rf "$APPDIR" "$WORKDIR"
mkdir -p "$APPDIR/usr/bin" \
         "$APPDIR/usr/share/kage-gui" \
         "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps" \
         "$DEBDIR"
cp -r kage_gui "$APPDIR/usr/share/kage-gui/"
find "$APPDIR/usr/share/kage-gui" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
install -m 755 packaging/kage-gui "$APPDIR/usr/bin/kage-gui"
install -m 644 packaging/kage-gui.desktop "$APPDIR/usr/share/applications/cu.fabian.kagegui.desktop"
install -m 644 packaging/kage-gui.desktop "$APPDIR/cu.fabian.kagegui.desktop"
install -m 644 packaging/kage-gui.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/kage-gui.png"
install -m 644 packaging/kage-gui.png "$APPDIR/kage-gui.png"

# --- 1b. kage DENTRO del AppImage (decisión de Fabian, 2026-10-31) ---
# Se descarga la release oficial y se verifica el sha256 comparando
# hashes directamente (nada de `sha256sum -c` contra un tarball
# renombrado: ese fue el fallo original de la v1 del workflow).
# Un binario dejado a mano en build/kage tiene prioridad y salta la
# descarga (útil para builds locales sin red).
if [ -f build/kage ]; then
  install -m 755 build/kage "$APPDIR/usr/bin/kage"
  echo "== kage: usando el binario local de build/kage =="
else
  # Versión a empaquetar: la ÚLTIMA release oficial, resuelta en cada
  # build siguiendo la redirección de /releases/latest (sin API ni
  # claves), para que el AppImage nunca lleve un kage viejo. Se puede
  # fijar una concreta con KAGE_VERSION=0.3.12 (builds reproducibles).
  if [ -n "${KAGE_VERSION:-}" ]; then
    KAGE_TAG="v${KAGE_VERSION}"
  else
    KAGE_TAG="$(curl -fsIL -o /dev/null -w '%{url_effective}' https://github.com/tamnd/kage/releases/latest | sed 's@.*/tag/@@')"
    case "$KAGE_TAG" in
      v*) KAGE_VERSION="${KAGE_TAG#v}" ;;
      *) echo "ERROR: no se pudo resolver la última versión de kage (tag: '$KAGE_TAG')" >&2; exit 1 ;;
    esac
  fi
  KAGE_TARBALL="kage_${KAGE_VERSION}_linux_amd64.tar.gz"
  KAGE_URL="https://github.com/tamnd/kage/releases/download/${KAGE_TAG}"
  mkdir -p "$WORKDIR/kage"
  curl -fL -o "$WORKDIR/kage/$KAGE_TARBALL" "$KAGE_URL/$KAGE_TARBALL"
  curl -fL -o "$WORKDIR/kage/checksums.txt" "$KAGE_URL/checksums.txt"
  expected="$(awk -v f="$KAGE_TARBALL" '$2 == f || $2 == "*" f {print $1}' "$WORKDIR/kage/checksums.txt")"
  actual="$(sha256sum "$WORKDIR/kage/$KAGE_TARBALL" | awk '{print $1}')"
  if [ -z "$expected" ] || [ "$expected" != "$actual" ]; then
    echo "ERROR: el sha256 de $KAGE_TARBALL no coincide (esperado: $expected, real: $actual)" >&2
    exit 1
  fi
  echo "== kage $KAGE_VERSION (última release): sha256 verificado =="
  # --no-same-owner: como root, tar intentaría restaurar el uid del
  # tarball (1001) y hay entornos (contenedores) donde no puede.
  tar --no-same-owner -xzf "$WORKDIR/kage/$KAGE_TARBALL" -C "$WORKDIR/kage"
  install -m 755 "$WORKDIR/kage/kage" "$APPDIR/usr/bin/kage"
fi
"$APPDIR/usr/bin/kage" --version || true

# --- 2. Runtime: descargar el cierre completo de .deb y extraerlo ---
# Estado de apt vacío => apt ignora lo que el runner ya tenga instalado
# y descarga TODAS las dependencias (si no, el AppImage dependería de
# librerías que solo están en el runner, no en la máquina del usuario).
: > "$WORKDIR/empty-status"
$SUDO apt-get $APT_OPTS update
$SUDO apt-get $APT_OPTS install --download-only -y \
  -o Dir::State::status="$WORKDIR/empty-status" \
  -o Dir::Cache::archives="$DEBDIR" \
  $PKGS
count="$(find "$DEBDIR" -maxdepth 1 -name '*.deb' | wc -l)"
echo "== .deb descargados: $count =="
if [ "$count" -lt 50 ]; then
  echo "ERROR: cierre de dependencias sospechosamente pequeño ($count)" >&2
  exit 1
fi
for deb in "$DEBDIR"/*.deb; do dpkg -x "$deb" "$APPDIR"; done

# Limpiar peso muerto (documentación y manuales no hacen falta a bordo).
rm -rf "$APPDIR/usr/share/doc" "$APPDIR/usr/share/man" "$APPDIR/usr/share/lintian" || true

# Cachés de iconos (sus rutas son relativas: seguras dentro del AppDir).
if [ -x "$APPDIR/usr/bin/gtk-update-icon-cache" ]; then
  for theme in hicolor adwaita; do
    dir="$APPDIR/usr/share/icons/$theme"
    [ -d "$dir" ] && "$APPDIR/usr/bin/gtk-update-icon-cache" -f -t "$dir" 2>/dev/null || true
  done
fi

# --- 3. AppRun: entorno del runtime empaquetado ---
cat > "$APPDIR/AppRun" <<EOF
#!/bin/sh
APPDIR="\$(dirname "\$(readlink -f "\$0")")"
LIB="\$APPDIR/usr/lib/$MULTIARCH"
# usr/bin primero en el PATH: la GUI localiza kage por el PATH y debe
# encontrar el empaquetado antes que cualquier kage del sistema.
export PATH="\$APPDIR/usr/bin:\$PATH"
export LD_LIBRARY_PATH="\$LIB:\$APPDIR/usr/lib\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
export PYTHONHOME="\$APPDIR/usr"
export PYTHONPATH="\$APPDIR/usr/share/kage-gui:\$APPDIR/usr/lib/python3/dist-packages"
export GI_TYPELIB_PATH="\$LIB/girepository-1.0:\$APPDIR/usr/lib/girepository-1.0"
export XDG_DATA_DIRS="\$APPDIR/usr/share:\${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
# La caché de loaders de gdk-pixbuf guarda rutas absolutas y el punto de
# montaje del AppImage cambia en cada ejecución: se regenera al arrancar.
QUERY="\$LIB/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders"
LOADERS="\$LIB/gdk-pixbuf-2.0/2.10.0/loaders"
if [ -x "\$QUERY" ] && ls "\$LOADERS"/*.so >/dev/null 2>&1; then
  CACHE="\$(mktemp /tmp/gdk-pixbuf-loaders.XXXXXX)"
  if "\$QUERY" "\$LOADERS"/*.so > "\$CACHE" 2>/dev/null; then
    export GDK_PIXBUF_MODULE_FILE="\$CACHE"
  else
    rm -f "\$CACHE"
  fi
fi
exec "\$APPDIR/usr/bin/python3" -m kage_gui "\$@"
EOF
chmod +x "$APPDIR/AppRun"

# --- 4. Empaquetar ---
ARCH="$MULTIARCH" "$APPIMAGETOOL" "$APPDIR" "kage-gui-$VERSION.AppImage"
ls -lh "kage-gui-$VERSION.AppImage"
echo "== OK: kage-gui-$VERSION.AppImage =="
