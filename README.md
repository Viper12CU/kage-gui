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
- **Biblioteca**: los mirrors de la carpeta raíz, con nº de páginas (desde
  `_kage/state.json`) y tamaño. Acciones: **Ver** (arranca `kage serve` en
  un puerto libre y abre el navegador), **Empaquetar ZIM / binario / App**
  (`kage pack`), abrir la carpeta y eliminar.
- **Abrir ZIM**: elige un `.zim` y lo sirve con `kage open` para leerlo.

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
| `kage_gui/window.py` | Toda la interfaz GTK4: ventana, las 3 vistas y el diálogo de pack. |
| `kage_gui/__main__.py` | Punto de entrada (`python3 -m kage_gui`). |
| `tests/test_logic.py` | Tests de la lógica sin GUI. |

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Notas de diseño

- `serve`/`open` usan un puerto libre en vez del 8800 fijo de kage, para
  no chocar si ya hay algo escuchando.
- Casi toda la salida de kage va a *stderr* con colores ANSI y el progreso
  se sobrescribe con `\r`; `runner.py` lo limpia y lo convierte en
  contadores para la barra de estado.
- `clone` puede salir con código 0 aunque haya páginas con error: la GUI
  juzga el resultado por el resumen final y el contador de errores.
