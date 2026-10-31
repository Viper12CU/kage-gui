# Kage GUI

Interfaz gráfica nativa para Ubuntu (Python + GTK4) para la CLI
[kage](https://github.com/tamnd/kage): clona sitios web para leerlos offline,
sin JavaScript. La GUI no reimplementa nada: construye los comandos y los
ejecuta con `subprocess`, mostrando progreso y registro en vivo.

## Vistas

- **Clonar**: URL, carpeta destino (`~/data/kage` por defecto), máx. páginas,
  profundidad, solo una sección, subdominios, scroll, actualizar y forzar
  (con confirmación, porque borra). Avanzado: workers, rutas a excluir y
  ruta de Chrome. Contadores en vivo (páginas/assets/errores) y botón
  Cancelar que manda SIGINT — kage guarda el estado y el clon se reanuda
  la próxima vez.
- **Biblioteca**: los mirrors de la carpeta raíz en un **grid de cards**,
  cada una con una **preview real del sitio** (captura de su página
  principal con Chrome headless, cacheada en `~/.cache/kage-gui/thumbs/`),
  nombre, nº de páginas (desde `_kage/state.json`), tamaño y fecha.
  Acciones sobre la card seleccionada: **Ver** (arranca `kage serve` en
  un puerto libre y abre el navegador), **Empaquetar ZIM / binario / App**
  (`kage pack`), abrir la carpeta y eliminar.
- **Abrir ZIM**: elige un `.zim` y lo sirve con `kage open` para leerlo.
- **Preferencias** (incluye lo que antes era Sistema): versión de kage
  instalada y su ruta, Chrome detectado, **Buscar actualizaciones**
  (consulta la última release en GitHub y dice si estás al día, con
  enlaces a la release y al `.deb`), selector de tema, accesos a los
  datos de la app (configuración y caché de previews) y enlaces a la
  documentación oficial de kage, su repositorio, las releases y los
  issues. La carpeta de destino de los clones se abre desde la
  Biblioteca (o junto al campo «Guardar en» de Clonar), no desde aquí.

## Primera vez y tema

Al arrancar, si **kage no está instalado**, la app abre un diálogo para
instalarlo desde ahí (repo apt del autor, vía `pkexec`) o seguir las
instrucciones manuales; también queda el aviso en la parte superior y el
botón «Instalar kage…» en Sistema.

El selector de tema del encabezado (Sistema / Claro / Oscuro) se guarda en
`~/.config/kage-gui/config.json` y se aplica al arrancar.

## Requisitos

```bash
# GTK4 para Python (Ubuntu 24.04)
sudo apt install python3-gi gir1.2-gtk-4.0

# kage (elige una)
sudo apt install kage        # tras añadir el repo del autor, ver su README
# o el .deb de https://github.com/tamnd/kage/releases
```

kage necesita Chrome/Chromium para clonar; si no encuentra ninguno, él
mismo descarga Chromium la primera vez (~150 MB).

## Ejecutar

El proyecto vive en su propio entorno virtual. Ojo al detalle: el venv se
crea con `--system-site-packages` porque GTK (`gi`) se instala con apt y
no existe como paquete pip instalable; con esa opción el venv ve los
paquetes del sistema y a la vez aísla lo que instales con pip.

```bash
python3 -m venv --system-site-packages .venv   # solo la primera vez
./run.sh                                       # usa .venv/bin/python
```

Sin `run.sh`, el equivalente manual es:

```bash
.venv/bin/python -m kage_gui
```

Opcional, para tenerla en el menú de aplicaciones:

```bash
# Ajusta la ruta en Exec= de kage-gui.desktop a tu carpeta y luego:
cp kage-gui.desktop ~/.local/share/applications/
```

## Estructura

| Archivo | Qué contiene |
|---|---|
| `kage_gui/commands.py` | Construcción de comandos (listas, sin shell) y detección del binario. Sin GTK. |
| `kage_gui/runner.py` | Ejecuta procesos: quita ANSI, parsea contadores, cancelar = SIGINT. Sin GTK. |
| `kage_gui/library.py` | Escanea la carpeta de mirrors y lee su estado. Sin GTK. |
| `kage_gui/config.py` | Configuración persistente (tema, primera vez). Sin GTK. |
| `kage_gui/updates.py` | Última release de kage en GitHub y comparación de versiones. Sin GTK. |
| `kage_gui/previews.py` | Miniaturas de los mirrors con Chrome headless y su caché. Sin GTK. |
| `kage_gui/window.py` | Toda la interfaz GTK4: ventana, las 4 vistas y los diálogos. |
| `kage_gui/__main__.py` | Punto de entrada (`python3 -m kage_gui`). |
| `tests/` | Tests de la lógica sin GUI (v1 y v2). |

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Release automático (AppImage)

Cada push a `main` dispara `.github/workflows/appimage-release.yml`:
corre los tests, descarga el binario oficial de kage, construye el
`.AppImage` con appimage-builder (receta `AppImageBuilder.yml`, base
Ubuntu 22.04 para que corra en 22.04 en adelante), hace un smoke test
abriendo la ventana bajo Xvfb y publica un Release nuevo con el
ejecutable adjunto.

- El tag es `v<versión>-build<nº>` y el release queda como pre-release,
  porque la versión de la app no cambia en cada push. Para releases
  «de verdad» solo con tag, mira el comentario al inicio del workflow.
- El AppImage lleva **kage empaquetado dentro** (`usr/bin/kage`): quien
  lo descarga no necesita instalar kage aparte. Chrome/Chromium no va
  dentro; si el sistema no tiene ninguno, kage descarga el suyo la
  primera vez que clona, como siempre.
- Ejecutarlo en el PC puede pedir FUSE (`libfuse2` en Ubuntu 22.04;
  en 24.04+ suele venir `libfuse2t64`). Sin FUSE:
  `./Kage_GUI-*.AppImage --appimage-extract-and-run`.

Build local del mismo AppImage:

```bash
VERSION=0.4.0 appimage-builder --recipe AppImageBuilder.yml
```

## Notas de diseño

- `serve`/`open` usan un puerto libre en vez del 8800 fijo de kage, para
  no chocar si ya hay algo escuchando.
- Casi toda la salida de kage va a *stderr* con colores ANSI y el progreso
  se sobrescribe con `\r`; `runner.py` lo limpia y lo convierte en
  contadores para la barra de estado.
- `clone` puede salir con código 0 aunque haya páginas con error: la GUI
  juzga el resultado por el resumen final y el contador de errores.
