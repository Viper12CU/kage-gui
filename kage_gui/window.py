"""Interfaz GTK4 de Kage GUI.

Solo depende de GTK 4 (nada de libadwaita, para mantener la instalación
simple). Toda la lógica de kage vive en commands.py / runner.py /
library.py; aquí solo hay widgets y el pegamento con GLib: los callbacks
del runner llegan desde un hilo lector y siempre vuelven al hilo
principal con GLib.idle_add antes de tocar un widget.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import webbrowser

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import commands
from .commands import CloneOptions
from .library import Mirror, free_port, scan_library
from .runner import Counters, ProcessRunner


def _idle(fn, *args):
    """Programa fn(*args) en el hilo principal de GTK."""
    GLib.idle_add(fn, *args)
    return False


def _label(text: str, bold: bool = False) -> Gtk.Label:
    label = Gtk.Label(label=text, xalign=0)
    if bold:
        label.set_markup(f"<b>{GLib.markup_escape_text(text)}</b>")
    return label


def _row(label_text: str, widget: Gtk.Widget) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    box.append(_label(label_text))
    widget.set_hexpand(True)
    box.append(widget)
    return box


class LogView(Gtk.ScrolledWindow):
    """Consola de solo lectura para la salida de kage."""

    def __init__(self) -> None:
        super().__init__()
        self.set_min_content_height(170)
        self.set_vexpand(True)
        self._view = Gtk.TextView(editable=False, monospace=True, cursor_visible=False)
        self._view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.set_child(self._view)
        self._buffer = self._view.get_buffer()

    def append_line(self, line: str) -> None:
        end = self._buffer.get_end_iter()
        self._buffer.insert(end, line + "\n")
        end = self._buffer.get_end_iter()
        self._view.scroll_to_iter(end, 0.0, False, 0.0, 1.0)

    def clear(self) -> None:
        self._buffer.set_text("")


class ServerSession:
    """Un proceso serve/open en curso, con su URL local."""

    def __init__(self) -> None:
        self.runner = ProcessRunner()
        self.url: str = ""
        self.what: str = ""       # qué está sirviendo (ruta)
        self.on_stopped = lambda: None

    @property
    def running(self) -> bool:
        return self.runner.running

    def start(self, kage_bin: str, kind: str, path: str) -> str:
        port = free_port()
        addr = f"127.0.0.1:{port}"
        if kind == "serve":
            cmd = commands.build_serve_command(kage_bin, path, addr)
        else:
            cmd = commands.build_open_command(kage_bin, path, addr)
        self.runner.on_exit = lambda code: _idle(self._exited)
        self.runner.start(cmd)
        self.url = f"http://{addr}"
        self.what = path
        return self.url

    def _exited(self) -> None:
        self.url = ""
        self.what = ""
        self.on_stopped()

    def stop(self) -> None:
        self.runner.stop_server()


# ---------------------------------------------------------------------------
# Vista: Clonar
# ---------------------------------------------------------------------------

class ClonePage(Gtk.Box):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._window = window
        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)

        self._runner = ProcessRunner(
            on_line=lambda line: _idle(self._on_line, line),
            on_counters=lambda c: _idle(self._on_counters, c),
            on_exit=lambda code: _idle(self._on_exit, code),
        )

        self._url = Gtk.Entry(placeholder_text="https://ejemplo.com  o  ejemplo.com")
        self.append(_row("Sitio", self._url))

        out_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._out = Gtk.Entry(text=commands.DEFAULT_OUT_ROOT)
        self._out.set_hexpand(True)
        out_box.append(self._out)
        pick = Gtk.Button(label="Elegir…")
        pick.connect("clicked", self._pick_out_dir)
        out_box.append(pick)
        self.append(_row("Guardar en", out_box))

        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        spin_pages = Gtk.SpinButton.new_with_range(0, 100000, 1)
        spin_pages.set_tooltip_text("0 = sin límite")
        self._max_pages = spin_pages
        self._max_depth = Gtk.SpinButton.new_with_range(0, 1000, 1)
        self._max_depth.set_tooltip_text("0 = sin límite")
        self._scope = Gtk.Entry(placeholder_text="/doc (opcional)")
        grid.attach(_label("Máx. páginas"), 0, 0, 1, 1)
        grid.attach(self._max_pages, 1, 0, 1, 1)
        grid.attach(_label("Profundidad"), 2, 0, 1, 1)
        grid.attach(self._max_depth, 3, 0, 1, 1)
        grid.attach(_label("Solo esta sección"), 0, 1, 1, 1)
        self._scope.set_hexpand(True)
        grid.attach(self._scope, 1, 1, 3, 1)
        self.append(grid)

        switches = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        self._subdomains = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._scroll = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._refresh = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._force = Gtk.Switch(valign=Gtk.Align.CENTER)
        for text, switch in (
            ("Subdominios", self._subdomains),
            ("Scroll (lazy-load)", self._scroll),
            ("Actualizar", self._refresh),
            ("Forzar (borra)", self._force),
        ):
            cell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            cell.append(Gtk.Label(label=text))
            cell.append(switch)
            switches.append(cell)
        self.append(switches)

        advanced = Gtk.Expander(label="Avanzado")
        adv_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        adv_box.set_margin_top(8)
        self._workers = Gtk.SpinButton.new_with_range(1, 16, 1)
        self._workers.set_value(4)
        adv_box.append(_row("Workers", self._workers))
        self._exclude = Gtk.Entry(placeholder_text="/blog, /archivo (separados por comas)")
        adv_box.append(_row("Excluir rutas", self._exclude))
        self._chrome = Gtk.Entry(placeholder_text="Ruta a Chrome/Chromium (vacío = automático)")
        adv_box.append(_row("Chrome", self._chrome))
        advanced.set_child(adv_box)
        self.append(advanced)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._btn_clone = Gtk.Button(label="Clonar")
        self._btn_clone.add_css_class("suggested-action")
        self._btn_clone.connect("clicked", self._start_clone)
        buttons.append(self._btn_clone)
        self._btn_cancel = Gtk.Button(label="Cancelar")
        self._btn_cancel.add_css_class("destructive-action")
        self._btn_cancel.set_sensitive(False)
        self._btn_cancel.connect("clicked", lambda *_: self._runner.cancel())
        buttons.append(self._btn_cancel)
        self.append(buttons)

        self._progress = Gtk.ProgressBar(show_text=False)
        self.append(self._progress)
        self._status = Gtk.Label(label="Listo.", xalign=0)
        self.append(self._status)

        self._log = LogView()
        self.append(self._log)

    # -- acciones -----------------------------------------------------------

    def _pick_out_dir(self, _btn) -> None:
        dialog = Gtk.FileDialog(title="Carpeta raíz para los mirrors")
        dialog.select_folder(self._window, None, self._on_out_picked)

    def _on_out_picked(self, dialog, result, *args) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return  # usuario canceló
        if folder and folder.get_path():
            self._out.set_text(folder.get_path())

    def _collect_options(self) -> CloneOptions:
        exclude = [p.strip() for p in self._exclude.get_text().split(",")]
        return CloneOptions(
            url=self._url.get_text().strip(),
            out_root=os.path.expanduser(self._out.get_text().strip())
            or commands.DEFAULT_OUT_ROOT,
            max_pages=self._max_pages.get_value_as_int(),
            max_depth=self._max_depth.get_value_as_int(),
            scope_prefix=self._scope.get_text().strip(),
            exclude=exclude,
            subdomains=self._subdomains.get_active(),
            scroll=self._scroll.get_active(),
            refresh=self._refresh.get_active(),
            force=self._force.get_active(),
            workers=self._workers.get_value_as_int(),
            chrome=self._chrome.get_text().strip(),
        )

    def _start_clone(self, _btn) -> None:
        kage_bin = self._window.kage_bin
        if not kage_bin:
            self._status.set_text("kage no está instalado (mira el aviso superior).")
            return
        opts = self._collect_options()
        if not opts.url:
            self._status.set_text("Escribe primero la URL del sitio.")
            self._url.grab_focus()
            return
        if opts.force:
            self._confirm_force(opts)
            return
        self._launch(opts)

    def _confirm_force(self, opts: CloneOptions) -> None:
        dialog = Gtk.AlertDialog(
            message="¿Clonar con --force?",
            detail="kage borrará el mirror existente de este host antes de "
                   "empezar. Esta acción no se puede deshacer.",
            buttons=["Cancelar", "Borrar y clonar"],
        )
        dialog.set_cancel_button(0)
        dialog.set_default_button(0)
        dialog.choose(self._window, None, self._on_force_chosen, opts)

    def _on_force_chosen(self, dialog, result, opts, *args) -> None:
        try:
            if dialog.choose_finish(result) == 1:
                self._launch(opts)
        except GLib.Error:
            pass

    def _launch(self, opts: CloneOptions) -> None:
        self._log.clear()
        self._progress.pulse()
        self._pulse_timer = GLib.timeout_add(120, self._pulse)
        self._status.set_text(f"Clonando {opts.url} …")
        self._btn_clone.set_sensitive(False)
        self._btn_cancel.set_sensitive(True)
        cmd = commands.build_clone_command(self._window.kage_bin, opts)
        self._runner.start(cmd)

    def _pulse(self) -> bool:
        if self._runner.running:
            self._progress.pulse()
            return True
        return False

    # -- callbacks del runner (ya en el hilo principal) ---------------------

    def _on_line(self, line: str) -> None:
        # El progreso crudo haría spam en el log; solo van líneas "reales".
        if not line.startswith("pages "):
            self._log.append_line(line)

    def _on_counters(self, counters: Counters) -> None:
        self._status.set_text("Clonando… " + counters.summary())

    def _on_exit(self, code: int) -> None:
        self._btn_clone.set_sensitive(True)
        self._btn_cancel.set_sensitive(False)
        self._progress.set_fraction(0)
        counters, done_dir = self._runner.counters, self._runner.done_dir
        if not self._runner.running and code != 0 and not done_dir:
            self._status.set_text(f"kage salió con código {code}. Revisa el registro.")
        elif counters.errors:
            self._status.set_text(
                f"Terminado con {counters.errors} errores. " + counters.summary())
        elif done_dir:
            self._status.set_text(f"Listo. Mirror en {done_dir}")
        else:
            self._status.set_text("Terminado (cancelado o sin páginas nuevas).")
        self._window.refresh_library()


# ---------------------------------------------------------------------------
# Vista: Biblioteca
# ---------------------------------------------------------------------------

class LibraryPage(Gtk.Box):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self._window = window
        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)
        self._server = ServerSession()
        self._server.on_stopped = self._server_stopped

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._root_label = Gtk.Label(xalign=0)
        self._root_label.set_hexpand(True)
        toolbar.append(self._root_label)
        refresh = Gtk.Button(label="Refrescar")
        refresh.connect("clicked", lambda *_: self.refresh())
        toolbar.append(refresh)
        self.append(toolbar)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self._list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self._list.add_css_class("boxed-list")
        self._list.connect("row-selected", lambda *_: self._sync_buttons())
        scroll.set_child(self._list)
        self.append(scroll)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._btn_view = Gtk.Button(label="Ver")
        self._btn_view.add_css_class("suggested-action")
        self._btn_view.connect("clicked", self._toggle_view)
        actions.append(self._btn_view)
        self._btn_browser = Gtk.Button(label="Abrir en el navegador")
        self._btn_browser.connect(
            "clicked", lambda *_: self._server.url and webbrowser.open(self._server.url))
        actions.append(self._btn_browser)
        pack_zim = Gtk.Button(label="Empaquetar ZIM")
        pack_zim.connect("clicked", lambda *_: self._pack("zim", app=False))
        actions.append(pack_zim)
        pack_bin = Gtk.Button(label="Empaquetar binario")
        pack_bin.connect("clicked", lambda *_: self._pack("binary", app=False))
        actions.append(pack_bin)
        pack_app = Gtk.Button(label="Crear App")
        pack_app.connect("clicked", lambda *_: self._pack("binary", app=True))
        actions.append(pack_app)
        open_folder = Gtk.Button(label="Abrir carpeta")
        open_folder.connect("clicked", self._open_folder)
        actions.append(open_folder)
        self._btn_delete = Gtk.Button(label="Eliminar")
        self._btn_delete.add_css_class("destructive-action")
        self._btn_delete.connect("clicked", self._confirm_delete)
        actions.append(self._btn_delete)
        self._action_buttons = [
            self._btn_view, pack_zim, pack_bin, pack_app, open_folder, self._btn_delete,
        ]
        self.append(actions)

        self._status = Gtk.Label(label="", xalign=0)
        self.append(self._status)
        self.refresh()

    # -- datos ---------------------------------------------------------------

    def refresh(self) -> None:
        root = self._window.out_root()
        self._root_label.set_text(f"Mirrors en {root}")
        while (row := self._list.get_row_at_index(0)) is not None:
            self._list.remove(row)
        mirrors = scan_library(root)
        if not mirrors:
            row = Gtk.ListBoxRow(selectable=False)
            row.set_child(Gtk.Label(
                label="Todavía no hay mirrors. Clona un sitio en la pestaña Clonar.",
                margin_top=12, margin_bottom=12))
            self._list.append(row)
        for mirror in mirrors:
            row = Gtk.ListBoxRow()
            row.mirror = mirror  # type: ignore[attr-defined]
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_margin_top(6)
            box.set_margin_bottom(6)
            box.set_margin_start(10)
            title = Gtk.Label(label=mirror.name, xalign=0)
            title.set_markup(f"<b>{GLib.markup_escape_text(mirror.name)}</b>")
            box.append(title)
            box.append(Gtk.Label(label=mirror.subtitle, xalign=0))
            row.set_child(box)
            self._list.append(row)
        self._sync_buttons()

    def _selected(self) -> Mirror | None:
        row = self._list.get_selected_row()
        return getattr(row, "mirror", None) if row else None

    def _sync_buttons(self) -> None:
        has = self._selected() is not None
        for btn in self._action_buttons:
            btn.set_sensitive(has)
        self._btn_view.set_label("Detener" if self._server.running else "Ver")
        self._btn_browser.set_sensitive(bool(self._server.url))

    # -- acciones -------------------------------------------------------------

    def _toggle_view(self, _btn) -> None:
        if self._server.running:
            self._server.stop()
            return
        mirror = self._selected()
        if not mirror or not self._window.kage_bin:
            return
        url = self._server.start(self._window.kage_bin, "serve", mirror.path)
        self._status.set_text(f"Sirviendo {mirror.name} en {url}")
        webbrowser.open(url)
        self._sync_buttons()

    def _server_stopped(self) -> None:
        self._status.set_text("Servidor detenido.")
        self._sync_buttons()

    def _open_folder(self, _btn) -> None:
        mirror = self._selected()
        if mirror:
            subprocess.Popen(["xdg-open", mirror.path])

    def _pack(self, fmt: str, app: bool) -> None:
        mirror = self._selected()
        if not mirror or not self._window.kage_bin:
            return
        out = commands.default_pack_output(mirror.path, fmt, app)
        cmd = commands.build_pack_command(
            self._window.kage_bin, mirror.path, fmt, out_path=out, app=app)
        PackDialog(self._window, cmd, out).present()

    def _confirm_delete(self, _btn) -> None:
        mirror = self._selected()
        if not mirror:
            return
        dialog = Gtk.AlertDialog(
            message=f"¿Eliminar «{mirror.name}»?",
            detail=f"Se borrará la carpeta {mirror.path} con todo su contenido.",
            buttons=["Cancelar", "Eliminar"],
        )
        dialog.set_cancel_button(0)
        dialog.set_default_button(0)
        dialog.choose(self._window, None, self._on_delete_chosen, mirror)

    def _on_delete_chosen(self, dialog, result, mirror, *args) -> None:
        try:
            chosen = dialog.choose_finish(result)
        except GLib.Error:
            return
        if chosen != 1:
            return
        if self._server.running and self._server.what == mirror.path:
            self._server.stop()
        shutil.rmtree(mirror.path, ignore_errors=True)
        self.refresh()


# ---------------------------------------------------------------------------
# Vista: Abrir ZIM
# ---------------------------------------------------------------------------

class OpenZimPage(Gtk.Box):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._window = window
        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)
        self._server = ServerSession()
        self._server.on_stopped = self._stopped

        file_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._path = Gtk.Entry(placeholder_text="/ruta/al/archivo.zim")
        self._path.set_hexpand(True)
        file_box.append(self._path)
        pick = Gtk.Button(label="Elegir…")
        pick.connect("clicked", self._pick)
        file_box.append(pick)
        self.append(_row("Archivo ZIM", file_box))

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._btn_view = Gtk.Button(label="Ver")
        self._btn_view.add_css_class("suggested-action")
        self._btn_view.connect("clicked", self._toggle)
        buttons.append(self._btn_view)
        self._btn_browser = Gtk.Button(label="Abrir en el navegador", sensitive=False)
        self._btn_browser.connect(
            "clicked", lambda *_: self._server.url and webbrowser.open(self._server.url))
        buttons.append(self._btn_browser)
        self.append(buttons)

        self._status = Gtk.Label(
            label="Abre un .zim empaquetado con kage pack (o de Kiwix).", xalign=0)
        self.append(self._status)

    def _pick(self, _btn) -> None:
        dialog = Gtk.FileDialog(title="Elige un archivo ZIM")
        zim_filter = Gtk.FileFilter(name="Archivos ZIM")
        zim_filter.add_pattern("*.zim")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(zim_filter)
        dialog.set_filters(filters)
        dialog.open(self._window, None, self._on_picked)

    def _on_picked(self, dialog, result, *args) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        if file and file.get_path():
            self._path.set_text(file.get_path())

    def _toggle(self, _btn) -> None:
        if self._server.running:
            self._server.stop()
            return
        path = self._path.get_text().strip()
        if not path or not os.path.isfile(path):
            self._status.set_text("Elige primero un archivo .zim que exista.")
            return
        if not self._window.kage_bin:
            self._status.set_text("kage no está instalado (mira el aviso superior).")
            return
        url = self._server.start(self._window.kage_bin, "open", path)
        self._status.set_text(f"Sirviendo el ZIM en {url}")
        self._btn_view.set_label("Detener")
        self._btn_browser.set_sensitive(True)
        webbrowser.open(url)

    def _stopped(self) -> None:
        self._status.set_text("Servidor detenido.")
        self._btn_view.set_label("Ver")
        self._btn_browser.set_sensitive(False)


# ---------------------------------------------------------------------------
# Diálogo de pack (tarea corta con registro)
# ---------------------------------------------------------------------------

class PackDialog(Gtk.Window):
    def __init__(self, parent: "MainWindow", cmd: list[str], out_path: str) -> None:
        super().__init__(title="Empaquetando…", transient_for=parent, modal=True)
        self.set_default_size(560, 340)
        self._out_path = out_path
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        self._log = LogView()
        box.append(self._log)
        self._status = Gtk.Label(label="Trabajando…", xalign=0)
        box.append(self._status)
        close = Gtk.Button(label="Cerrar")
        close.connect("clicked", lambda *_: self.close())
        box.append(close)
        self.set_child(box)

        self._runner = ProcessRunner(
            on_line=lambda line: _idle(self._log.append_line, line),
            on_exit=lambda code: _idle(self._done, code),
        )
        self._runner.start(cmd)

    def _done(self, code: int) -> None:
        if code == 0 and os.path.exists(self._out_path):
            self.set_title("Empaquetado listo")
            self._status.set_text(f"Creado: {self._out_path}")
        else:
            self.set_title("Empaquetado terminado")
            self._status.set_text(
                f"kage salió con código {code}. Salida esperada: {self._out_path}")


# ---------------------------------------------------------------------------
# Ventana principal
# ---------------------------------------------------------------------------

class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Kage GUI")
        self.set_default_size(860, 640)

        self.kage_bin = commands.find_kage()
        self._clone_page = ClonePage(self)
        self._library_page = LibraryPage(self)
        self._zim_page = OpenZimPage(self)

        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        stack.add_titled(self._clone_page, "clone", "Clonar")
        stack.add_titled(self._library_page, "library", "Biblioteca")
        stack.add_titled(self._zim_page, "zim", "Abrir ZIM")

        header = Gtk.HeaderBar()
        switcher = Gtk.StackSwitcher(stack=stack)
        header.set_title_widget(switcher)
        if self.kage_bin:
            version = commands.kage_version(self.kage_bin)
            header.pack_end(Gtk.Label(label=f"kage {version}".strip()))
        self.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        if not self.kage_bin:
            banner = Gtk.InfoBar(message_type=Gtk.MessageType.WARNING)
            banner.set_show_close_button(True)
            banner.add_child(Gtk.Label(
                label="No encuentro el binario «kage». Instálalo con el .deb de "
                      "github.com/tamnd/kage/releases o «sudo apt install kage» "
                      "y reinicia esta app."))
            root.append(banner)
        root.append(stack)
        self.set_child(root)

    def out_root(self) -> str:
        return os.path.expanduser(self._clone_page._out.get_text().strip()) \
            or commands.DEFAULT_OUT_ROOT

    def refresh_library(self) -> None:
        self._library_page.refresh()
