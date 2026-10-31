"""Punto de entrada: `python3 -m kage_gui`."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from .window import MainWindow  # noqa: E402


def main() -> int:
    app = Gtk.Application(application_id="cu.fabian.kagegui")

    def on_activate(_app: Gtk.Application) -> None:
        win = app.get_active_window()
        if win is None:
            win = MainWindow(app)
        win.present()

    app.connect("activate", on_activate)
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
