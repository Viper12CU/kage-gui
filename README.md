# Kage GUI

**Versión 1.0.0** · Python + GTK4 · Linux (Ubuntu 22.04 o superior)

Interfaz gráfica nativa para la CLI [kage](https://github.com/tamnd/kage):
clona sitios web para leerlos sin conexión, sin JavaScript. La GUI no
reimplementa nada: construye los comandos y los ejecuta con `subprocess`,
mostrando el progreso y el registro en vivo.

## Descarga: el AppImage

La forma más simple de usarla. Cada push a `main` publica un Release con
un único ejecutable, nombrado con la versión de la app:

```
kage-gui-1.0.0.AppImage
```

```bash
chmod +x kage-gui-1.0.0.AppImage
./kage-gui-1.0.0.AppImage
```

- Lleva dentro Python, GTK4 y el binario de **kage 0.3.12**: no hay que
  instalar nada más para empezar.
- Chrome/Chromium **no** va dentro. Si el sistema no tiene ninguno, kage
  descarga el suyo la primera vez que clona un sitio (~150 MB).
- Ejecutar un AppImage necesita FUSE (`libfuse2` en Ubuntu 22.04;
  `libfuse2t64` en 24.04 o superior). Sin FUSE, vale esto:
  `./kage-gui-1.0.0.AppImage --appimage-extract-and-run`.

## Vistas

- **Clonar**: URL, carpeta destino (`~/data/kage` por defecto), máx.
  páginas, profundidad, solo una sección, subdominios, scroll, actualizar
  y forzar (con confirmación, porque borra). Avanzado: workers, rutas a
  excluir y ruta de Chrome. Contadores en vivo (páginas/assets/errores) y
  botón Cancelar que manda SIGINT — kage guarda el estado y el clon se
  reanuda la próxima vez. Botón para abrir la carpeta destino en el
  explorador de archivos.
- **Biblioteca**: los mirrors de la carpeta raíz en un **grid de cards**,
  cada una con una **preview real del sitio** (captura de su página
  principal con Chrome headless, cacheada en `~/.cache/kage-gui/thumbs/`),
  nombre, nº de páginas (desde `_kage/state.json`), tamaño y fecha.
  Acciones sobre la card seleccionada: **Ver** (arranca `kage serve` en
  un puerto libre y abre el navegador), **Empaquetar ZIM / binario / App**
  (`kage pack`), abrir la carpeta del mirror, abrir la carpeta raíz y
  eliminar.
- **Abrir ZIM**: elige un `.zim` y lo sirve con `kage open` para leerlo.
- **Preferencias**: todo el estado y la configuración en una sola vista —
  versión de kage instalada y su ruta, Chrome detectado, **Buscar
  actualizaciones** de kage (consulta la última release en GitHub y dice
  si estás al día, con enlaces a la release y al `.deb`), botón
  «Instalar kage…», selector de tema, accesos a los datos de la app
  (carpeta de configuración y caché de previews) y enlaces a la
  documentación oficial de kage, su repositorio, las releases y los
  issues.

## Primera vez y tema

Al arrancar, si **kage no está instalado** (solo puede pasar corriendo
desde el código: el AppImage lo trae dentro), la app abre un diálogo para
instalarlo desde ahí (repo apt del autor, vía `pkexec`) o seguir las
instrucciones manuales; también queda un aviso en la parte superior y el
botón «Instalar kage…» en la vista **Preferencias**.

El tema (Sistema / Claro / Oscuro) se puede cambiar desde el selector del
encabezado o desde Preferencias — ambos están sincronizados — y se guarda
en `~/.config/kage-gui/config.json`.

## Ejecutar desde el código

Requisitos del sistema (Ubuntu 22.04+):

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 python3-venv
```

Y kage, si no lo tienes (elige una vía):

```bash
sudo apt install kage        # tras añadir el repo del autor, ver su README
# o el .deb de https://github.com/tamnd/kage/releases
```

El proyecto vive en su propio entorno virtual. Ojo al detalle: el venv se
crea con `--system-site-packages` porque GTK (`gi`) se instala con apt y
no existe como paquete pip instalable; con esa opción el venv ve los
paquetes del sistema y a la vez aísla lo que instales con pip.

```bash
python3 -m venv --system-site-packages .venv   # solo la primera vez
./run.sh                                       # usa .venv/bin/python
```

Sin `run.sh`, el equivalente manual es `.venv/bin/python -m kage_gui`.

Opcional, para tenerla en el menú de aplicaciones: ajusta la ruta en
`Exec=` de `kage-gui.desktop` a tu carpeta y luego:

```bash
cp kage-gui.desktop ~/.local/share/applications/
```

Guía detallada de instalación y solución de problemas: `INSTALACION.md`.

## Estructura

| Ruta | Qué contiene |
|---|---|
| `kage_gui/commands.py` | Construcción de comandos (listas, sin shell) y detección del binario. Sin GTK. |
| `kage_gui/runner.py` | Ejecuta procesos: quita ANSI, parsea contadores, cancelar = SIGINT. Sin GTK. |
| `kage_gui/library.py` | Escanea la carpeta de mirrors y lee su estado. Sin GTK. |
| `kage_gui/config.py` | Configuración persistente (tema, primera vez). Sin GTK. |
| `kage_gui/updates.py` | Última release de kage en GitHub y comparación de versiones. Sin GTK. |
| `kage_gui/previews.py` | Miniaturas de los mirrors con Chrome headless y su caché. Sin GTK. |
| `kage_gui/window.py` | Toda la interfaz GTK4: ventana, las 4 vistas y los diálogos. |
| `kage_gui/__main__.py` | Punto de entrada (`python3 -m kage_gui`). |
| `kage_gui/__init__.py` | La versión de la app (`__version__`): única fuente de la versión. |
| `tests/` | Tests de la lógica sin GUI. |
| `AppImageBuilder.yml` | Receta del AppImage (base Ubuntu 22.04). |
| `packaging/` | Lanzador, `.desktop` e icono que van dentro del AppImage. |
| `.github/workflows/appimage-release.yml` | CI: tests, build del AppImage y publicación del Release. |

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Release automático (AppImage)

Cada push a `main` dispara `.github/workflows/appimage-release.yml`:
corre los tests, descarga el binario oficial de kage verificando su
sha256, construye el `.AppImage` con appimage-builder (base Ubuntu 22.04
para que corra en 22.04 en adelante), hace un smoke test abriendo la
ventana bajo Xvfb y publica un Release nuevo con el ejecutable adjunto.

- El ejecutable se llama `kage-gui-<versión>.AppImage`, con la versión
  leída de `kage_gui/__init__.py` — por ejemplo `kage-gui-1.0.0.AppImage`.
  Para sacar una versión nueva, basta con subir `__version__` ahí.
- El tag del Release es `v<versión>-build<nº de ejecución>` y queda como
  pre-release, porque la versión no cambia en cada push. Para releases
  «de verdad» solo con tag, mira el comentario al inicio del workflow.

Build local del mismo AppImage:

```bash
VERSION=1.0.0 appimage-builder --recipe AppImageBuilder.yml
# produce kage-gui-1.0.0.AppImage
```

## Notas de diseño

- `serve`/`open` usan un puerto libre en vez del 8800 fijo de kage, para
  no chocar si ya hay algo escuchando.
- Casi toda la salida de kage va a *stderr* con colores ANSI y el progreso
  se sobrescribe con `\r`; `runner.py` lo limpia y lo convierte en
  contadores para la barra de estado.
- `clone` puede salir con código 0 aunque haya páginas con error: la GUI
  juzga el resultado por el resumen final y el contador de errores.

## Licencia

MIT — ver `LICENSE`. Kage GUI es un proyecto independiente: kage es obra
de su autor (tamnd), también MIT.
