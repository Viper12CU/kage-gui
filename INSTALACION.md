# Instalación y prueba en tu máquina (Ubuntu)

Guía paso a paso para dejar Kage GUI funcionando en tu Ubuntu.
Tiempo estimado: 10 minutos (más la primera descarga de Chromium si no
tienes Chrome, ~150 MB).

## 1. Descomprimir

```bash
cd ~/Descargas        # o donde guardes el zip
unzip kage-gui.zip
cd kage-gui
```

El zip trae el repositorio git completo (historial incluido), así que
puedes seguir trabajando con `git` desde ahí.

## 2. Instalar las dependencias del sistema

GTK4 para Python (lo único que la GUI necesita del sistema):

```bash
sudo apt update
sudo apt install -y python3-gi gir1.2-gtk-4.0 python3-venv
```

## 3. Instalar kage (la CLI)

Elige **una** de las dos vías:

**Vía A — paquete .deb (la más rápida):** descarga
`kage_0.3.12_amd64.deb` desde
https://github.com/tamnd/kage/releases/latest y luego:

```bash
sudo apt install ./kage_0.3.12_amd64.deb
```

**Vía B — repositorio apt del autor** (recibe actualizaciones con el
sistema):

```bash
curl -fsSL https://tamnd.github.io/linux-repo/gpg.key | \
  sudo gpg --dearmor -o /usr/share/keyrings/tamnd.gpg
echo "deb [signed-by=/usr/share/keyrings/tamnd.gpg] \
  https://tamnd.github.io/linux-repo/apt stable main" | \
  sudo tee /etc/apt/sources.list.d/tamnd.list
sudo apt update && sudo apt install -y kage
```

Comprobación:

```bash
kage --version        # debe imprimir: kage version 0.3.12 (o superior)
```

> Si te saltas este paso, no pasa nada grave: al abrir Kage GUI sin kage
> instalado, la propia app te ofrece instalarlo desde un diálogo.

## 4. Crear el entorno virtual

Importante: con `--system-site-packages`, porque GTK viene de apt y no
de pip; sin eso la app no ve el módulo `gi`.

```bash
cd kage-gui           # si no estás ya dentro
python3 -m venv --system-site-packages .venv
```

## 5. Probar que todo está sano (tests)

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Resultado esperado: `Ran 17 tests ... OK`.

## 6. Ejecutar la app

```bash
./run.sh
```

Primera prueba sugerida:

1. Pestaña **Clonar**: pega `https://example.com`, activa si quieres
   «Máx. páginas» = 5 y pulsa **Clonar**.
2. Al terminar, pestaña **Biblioteca**: verás la card de example.com con
   su preview; selecciónala y pulsa **Ver** para navegar el clon offline.
3. Pestaña **Sistema** → **Buscar actualizaciones**: debe decir que
   estás al día.

Nota: en el primer clon, si no tienes Chrome/Chromium instalado, kage
descarga Chromium automáticamente (por eso puede tardar unos minutos la
primera vez; las siguientes ya no).

## 7. (Opcional) Icono en el menú de aplicaciones

Edita en `kage-gui.desktop` la línea `Exec=` con la ruta real donde
descomprimiste el proyecto, por ejemplo:

```
Exec=/home/tu-usuario/Descargas/kage-gui/run.sh
```

y copia el archivo:

```bash
cp kage-gui.desktop ~/.local/share/applications/
```

## Problemas típicos

| Síntoma | Causa y arreglo |
|---|---|
| `ModuleNotFoundError: No module named 'gi'` | El venv se creó sin `--system-site-packages`, o falta el paso 2. Borra `.venv` y repite el paso 4. |
| La app abre pero avisa «sin kage» | Falta el paso 3, o instalaste kage en una ruta fuera del PATH. Usa el diálogo de instalación de la propia app (pestaña Sistema → «Instalar kage…»). |
| El primer clon tarda mucho | Está descargando Chromium (~150 MB). Es solo la primera vez. |
| `kage clone` falla con un sitio concreto | Revisa el registro de la pestaña Clonar: ahí sale el error de kage tal cual (red, robots.txt, timeout…). |
| La ventana se ve con tema raro | En Preferencias elige tema Claro u Oscuro explícito. |

## Desinstalar

Borra la carpeta del proyecto y, si quieres, los datos:
`~/data/kage` (tus clones), `~/.cache/kage-gui` (miniaturas) y
`~/.config/kage-gui` (preferencias). kage se quita con
`sudo apt remove kage`.
