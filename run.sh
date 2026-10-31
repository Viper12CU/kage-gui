#!/bin/sh
# Lanza Kage GUI usando el venv del proyecto (.venv), sin instalar nada global.
# El venv se crea con --system-site-packages porque GTK (gi) viene de apt,
# no de pip:  python3 -m venv --system-site-packages .venv
cd "$(dirname "$0")" || exit 1
if [ -x .venv/bin/python ]; then
    exec .venv/bin/python -m kage_gui "$@"
fi
echo "No existe .venv. Créalo con:" >&2
echo "  python3 -m venv --system-site-packages .venv" >&2
exit 1
