# Cambios

## 1.0.0 — 2026-10-31

Primera versión publicada como ejecutable.

- **AppImage oficial**: `kage-gui-1.0.0.AppImage`, con Python, GTK4 y el
  binario de kage 0.3.12 dentro. El nombre del archivo lleva la versión
  de la app, leída de `kage_gui/__init__.py`.
- **Release automático**: cada push a `main` corre los tests, construye
  el AppImage (base Ubuntu 22.04), lo prueba bajo Xvfb y publica el
  Release (tag `v<versión>-build<nº>`, pre-release).
- GUI completa: vistas Clonar, Biblioteca (cards con preview real),
  Abrir ZIM y Preferencias (estado de kage, actualizaciones, tema
  Sistema/Claro/Oscuro, datos de la app y enlaces a la documentación
  oficial de kage).
- Instalación guiada de kage cuando falta (al correr desde el código).
- README reescrito y corregido; se añaden `LICENSE` (MIT) y este
  changelog.

## 0.4.0 — 2026-10-31 (desarrollo)

- Sistema y Preferencias unificadas en una sola vista.
- Corrección del cambio de tema en GTK ≥ 4.20 (`gtk-interface-color-scheme`).

## 0.3.0 — 2026-10-31 (desarrollo)

- Abrir la carpeta destino de los clones desde la Biblioteca y Clonar.
- Vista Preferencias con enlaces a la documentación oficial de kage.

## 0.2.0 — 2026-10-31 (desarrollo)

- Diálogo de instalación de kage, búsqueda de actualizaciones, Biblioteca
  en grid de cards con preview y selector de tema persistente.

## 0.1.0 — 2026-10-31 (desarrollo)

- Primera GUI: Clonar, Biblioteca en lista y Abrir ZIM sobre la CLI kage.
