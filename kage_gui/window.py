"""Interfaz GTK4 de Kage GUI (v2).

Solo depende de GTK 4. La lógica vive en commands.py / runner.py /
library.py / config.py / updates.py / previews.py; aquí solo hay widgets
y el pegamento con GLib: los callbacks que llegan desde hilos (runner,
red, miniaturas) vuelven al hilo principal con GLib.idle_add.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import webbrowser
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import commands, config, previews, updates
from .commands import CloneOptions
from .library import Mirror, free_port, scan_library
from .runner import Counters, ProcessRunner

_THEME_ORDER = ("system", "light", "dark")
_THEME_LABELS = ("Sistema", "Claro", "Oscuro")

_CSS = """
.kage-card { border: 1px solid alpha(currentColor, 0.16); border-radius: 12px;
             padding: 8px; }
.kage-card-selected { background: alpha(#3584e4, 0.18);
                      border: 1px solid #3584e4; border-radius: 12px;
                      padding: 8px; }
.kage-thumb { border-radius: 8px; background: alpha(currentColor, 0.06); }
.mono { font-family: monospace; font-size: 0.92em; }
"""


def _idle(fn, *args):
    GLib.idle_add(fn, *args)
    return False


def open_folder(path: str) -> bool:
    """Abre una carpeta en el explorador de archivos (la crea si falta)."""
    try:
        os.makedirs(path, exist_ok=True)
        subprocess.Popen(["xdg-open", path])
        return True
    except OSError:
        return False


def apply_theme(mode: str) -> None:
    settings = Gtk.Settings.get_default()
    if settings is not None:
        # "dark" fuerza oscuro; "light" y "system" dejan el valor por
        # defecto de GTK (el escritorio manda a través de sus ajustes).
        settings.set_property("gtk-application-prefer-dark-theme", mode == "dark")


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
        self.what: str = ""
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
# Diálogo de instalación de kage (primera vez / cuando falta el binario)
# ---------------------------------------------------------------------------

class SetupDialog(Gtk.Window):
    def __init__(self, parent: "MainWindow") -> None:
        super().__init__(title="Instalar kage", transient_for=parent, modal=True)
        self.set_default_size(620, 520)
        self._parent = parent

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for widget, margin in ((box, 14),):
            widget.set_margin_top(margin)
            widget.set_margin_bottom(margin)
            widget.set_margin_start(margin)
            widget.set_margin_end(margin)

        title = Gtk.Label(xalign=0)
        title.set_markup("<b><big>Kage GUI necesita el programa «kage»</big></b>")
        box.append(title)
        box.append(Gtk.Label(
            label="No se encontró el binario de kage en este equipo. Sin él la "
                  "app no puede clonar ni servir sitios. Puedes instalarlo "
                  "desde aquí o seguir las instrucciones manuales.",
            xalign=0, wrap=True))

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._btn_install = Gtk.Button(label="Instalar automáticamente (apt)")
        self._btn_install.add_css_class("suggested-action")
        self._btn_install.connect("clicked", self._install)
        buttons.append(self._btn_install)
        releases = Gtk.Button(label="Abrir página de releases")
        releases.connect("clicked", lambda *_: webbrowser.open(updates.RELEASES_URL))
        buttons.append(releases)
        recheck = Gtk.Button(label="Volver a comprobar")
        recheck.connect("clicked", lambda *_: self._recheck())
        buttons.append(recheck)
        box.append(buttons)

        expander = Gtk.Expander(label="Instrucciones manuales")
        instructions = Gtk.Label(
            label=updates.INSTALL_INSTRUCTIONS, xalign=0, selectable=True)
        instructions.add_css_class("mono")
        expander.set_child(instructions)
        box.append(expander)

        self._log = LogView()
        self._log.set_min_content_height(130)
        box.append(self._log)
        self._status = Gtk.Label(label="", xalign=0)
        box.append(self._status)
        close = Gtk.Button(label="Cerrar")
        close.connect("clicked", lambda *_: self.close())
        box.append(close)
        self.set_child(box)

        self._runner = ProcessRunner(
            on_line=lambda line: _idle(self._log.append_line, line),
            on_exit=lambda code: _idle(self._install_done, code),
        )

    def _install(self, _btn) -> None:
        if not shutil.which("pkexec"):
            self._log.append_line(
                "No hay «pkexec» en este sistema: usa las instrucciones manuales.")
            return
        self._btn_install.set_sensitive(False)
        self._status.set_text("Instalando… (acepta el diálogo de contraseña)")
        self._runner.start(["pkexec", "sh", "-c", updates.APT_INSTALL_SCRIPT])

    def _install_done(self, code: int) -> None:
        self._btn_install.set_sensitive(True)
        if code == 0:
            self._recheck(extra="Instalación terminada. ")
        else:
            self._status.set_text(
                f"La instalación salió con código {code}. Revisa el registro "
                "o prueba con las instrucciones manuales.")

    def _recheck(self, extra: str = "") -> None:
        found = self._parent.refresh_kage_status()
        if found:
            version = commands.kage_version(found)
            self._status.set_text(f"{extra}kage detectado: {version} ({found})")
        else:
            self._status.set_text(extra + "kage sigue sin aparecer en el PATH.")


# ---------------------------------------------------------------------------
# Vista: Clonar (igual que en v1)
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
        open_out = Gtk.Button(label="Abrir")
        open_out.set_tooltip_text("Abrir la carpeta destino en el explorador")
        open_out.connect("clicked", lambda *_: open_folder(
            os.path.expanduser(self._out.get_text().strip())
            or commands.DEFAULT_OUT_ROOT))
        out_box.append(open_out)
        self.append(_row("Guardar en", out_box))

        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        self._max_pages = Gtk.SpinButton.new_with_range(0, 100000, 1)
        self._max_pages.set_tooltip_text("0 = sin límite")
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

    def _pick_out_dir(self, _btn) -> None:
        dialog = Gtk.FileDialog(title="Carpeta raíz para los mirrors")
        dialog.select_folder(self._window, None, self._on_out_picked)

    def _on_out_picked(self, dialog, result, *args) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
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
        self._status.set_text(f"Clonando {opts.url} …")
        self._btn_clone.set_sensitive(False)
        self._btn_cancel.set_sensitive(True)
        GLib.timeout_add(120, self._pulse)
        cmd = commands.build_clone_command(self._window.kage_bin, opts)
        self._runner.start(cmd)

    def _pulse(self) -> bool:
        if self._runner.running:
            self._progress.pulse()
            return True
        self._progress.set_fraction(0)
        return False

    def _on_line(self, line: str) -> None:
        if not line.startswith("pages "):
            self._log.append_line(line)

    def _on_counters(self, counters: Counters) -> None:
        self._status.set_text("Clonando… " + counters.summary())

    def _on_exit(self, code: int) -> None:
        self._btn_clone.set_sensitive(True)
        self._btn_cancel.set_sensitive(False)
        counters, done_dir = self._runner.counters, self._runner.done_dir
        if code != 0 and not done_dir:
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
# Vista: Biblioteca (grid de cards con preview)
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
        self._thumb_targets: dict[str, tuple[Gtk.Stack, Gtk.Picture]] = {}

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._root_label = Gtk.Label(xalign=0)
        self._root_label.set_hexpand(True)
        toolbar.append(self._root_label)
        open_root = Gtk.Button(label="Abrir carpeta destino")
        open_root.set_tooltip_text(
            "Abrir en el explorador la carpeta donde quedan las páginas clonadas")
        open_root.connect("clicked", self._open_root)
        toolbar.append(open_root)
        refresh = Gtk.Button(label="Refrescar")
        refresh.connect("clicked", lambda *_: self.refresh())
        toolbar.append(refresh)
        self.append(toolbar)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        # Grid fijo de 3 columnas: con FlowBox las cards se estiraban a una
        # sola columna; el Grid es predecible y la selección se lleva a mano
        # con una clase CSS sobre la card elegida.
        self._grid = Gtk.Grid(column_spacing=12, row_spacing=12,
                              column_homogeneous=True)
        self._grid.set_valign(Gtk.Align.START)
        self._selected_mirror: Mirror | None = None
        self._selected_card: Gtk.Box | None = None
        self._card_count = 0
        scroll.set_child(self._grid)
        self.append(scroll)
        self._empty_label = Gtk.Label(
            label="Todavía no hay mirrors. Clona un sitio en la pestaña Clonar.",
            margin_top=10)
        self._empty_label.set_visible(False)
        self.append(self._empty_label)

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
            self._btn_view, pack_zim, pack_bin, pack_app, open_folder,
            self._btn_delete,
        ]
        self.append(actions)

        self._status = Gtk.Label(label="", xalign=0)
        self.append(self._status)
        self.refresh()

    # -- datos ---------------------------------------------------------------

    def refresh(self) -> None:
        root = self._window.out_root()
        self._root_label.set_text(f"Mirrors en {root}")
        while (child := self._grid.get_first_child()) is not None:
            self._grid.remove(child)
        self._thumb_targets.clear()
        self._selected_mirror = None
        self._selected_card = None
        self._card_count = 0
        mirrors = scan_library(root)
        self._empty_label.set_visible(not mirrors)
        pending: list[Mirror] = []
        for mirror in mirrors:
            self._add_card(mirror)
            cached = previews.thumbnail_file(mirror.path, mirror.mtime)
            if os.path.isfile(cached):
                self._set_thumb(mirror.path, cached)
            else:
                pending.append(mirror)
        if pending:
            threading.Thread(target=self._generate_thumbs, args=(pending,),
                             daemon=True).start()
        self._sync_buttons()

    def _generate_thumbs(self, mirrors: list[Mirror]) -> None:
        for mirror in mirrors:
            path = previews.generate_thumbnail(mirror.path, mirror.mtime)
            if path:
                _idle(self._set_thumb, mirror.path, path)

    def _set_thumb(self, mirror_path: str, thumb_path: str) -> None:
        target = self._thumb_targets.get(mirror_path)
        if target is None:
            return
        stack, picture = target
        picture.set_filename(thumb_path)
        stack.set_visible_child_name("thumb")

    def _add_card(self, mirror: Mirror) -> None:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.add_css_class("kage-card")
        card.set_size_request(228, -1)

        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        # Tamaño fijo: sin esto, el ancho natural de la captura (640 px)
        # estira la card y el grid queda a una sola columna.
        stack.set_size_request(212, 132)
        stack.set_overflow(Gtk.Overflow.HIDDEN)
        stack.set_halign(Gtk.Align.CENTER)
        placeholder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        placeholder.set_size_request(212, 132)
        placeholder.set_valign(Gtk.Align.CENTER)
        icon = Gtk.Image.new_from_icon_name("web-browser-symbolic")
        icon.set_pixel_size(48)
        icon.set_halign(Gtk.Align.CENTER)
        placeholder.append(icon)
        placeholder.append(Gtk.Label(label="sin preview", halign=Gtk.Align.CENTER))
        stack.add_named(placeholder, "placeholder")
        picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER)
        picture.set_can_shrink(True)
        picture.set_size_request(212, 132)
        picture.add_css_class("kage-thumb")
        stack.add_named(picture, "thumb")
        stack.set_visible_child_name("placeholder")
        card.append(stack)
        self._thumb_targets[mirror.path] = (stack, picture)

        title = Gtk.Label(xalign=0, ellipsize=3)  # PANGO_ELLIPSIZE_END
        title.set_markup(f"<b>{GLib.markup_escape_text(mirror.name)}</b>")
        title.set_tooltip_text(mirror.path)
        card.append(title)
        pages = f"{mirror.pages} páginas" if mirror.pages >= 0 else "sin estado"
        date = datetime.fromtimestamp(mirror.mtime).strftime("%d %b %Y")
        card.append(Gtk.Label(
            label=f"{pages} · {mirror.size_human}\n{date}", xalign=0))
        card.set_valign(Gtk.Align.START)
        gesture = Gtk.GestureClick()
        gesture.connect("released", lambda *_: self._select_card(card, mirror))
        card.add_controller(gesture)
        self._grid.attach(card, self._card_count % 3, self._card_count // 3, 1, 1)
        self._card_count += 1

    def _select_card(self, card: Gtk.Box, mirror: Mirror) -> None:
        if self._selected_card is not None:
            self._selected_card.remove_css_class("kage-card-selected")
            self._selected_card.add_css_class("kage-card")
        card.remove_css_class("kage-card")
        card.add_css_class("kage-card-selected")
        self._selected_card = card
        self._selected_mirror = mirror
        self._sync_buttons()

    def _selected(self) -> Mirror | None:
        return self._selected_mirror

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
            open_folder(mirror.path)

    def _open_root(self, _btn) -> None:
        root = self._window.out_root()
        if open_folder(root):
            self._status.set_text(f"Abriendo {root} en el explorador…")
        else:
            self._status.set_text(f"No se pudo abrir {root}.")

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
# Vista: Abrir ZIM (igual que en v1)
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
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(zim_filter)
        dialog.set_filters(store)
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
# Vista: Sistema (versión instalada y actualizaciones)
# ---------------------------------------------------------------------------

class SistemaPage(Gtk.Box):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._window = window
        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)
        self._release: updates.ReleaseInfo | None = None

        self.append(_label("kage", bold=True))
        self._installed = Gtk.Label(label="", xalign=0, selectable=True)
        self.append(self._installed)
        self._chrome = Gtk.Label(label="", xalign=0)
        self.append(self._chrome)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._btn_setup = Gtk.Button(label="Instalar kage…")
        self._btn_setup.connect(
            "clicked", lambda *_: SetupDialog(self._window).present())
        buttons.append(self._btn_setup)
        self._btn_check = Gtk.Button(label="Buscar actualizaciones")
        self._btn_check.add_css_class("suggested-action")
        self._btn_check.connect("clicked", self._check)
        buttons.append(self._btn_check)
        self.append(buttons)

        self._update_status = Gtk.Label(label="", xalign=0, wrap=True)
        self.append(self._update_status)

        upd_buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._btn_release = Gtk.Button(label="Ver la release", sensitive=False)
        self._btn_release.connect("clicked", lambda *_: self._release
                                  and webbrowser.open(self._release.url))
        upd_buttons.append(self._btn_release)
        self._btn_deb = Gtk.Button(label="Descargar el .deb", sensitive=False)
        self._btn_deb.connect("clicked", lambda *_: self._release
                              and self._release.deb_amd64_url
                              and webbrowser.open(self._release.deb_amd64_url))
        upd_buttons.append(self._btn_deb)
        self.append(upd_buttons)
        self.append(Gtk.Label(
            label="Si instalaste kage con apt, actualizar es simplemente:\n"
                  "sudo apt update && sudo apt upgrade kage",
            xalign=0, selectable=True))
        self.refresh_status()

    def refresh_status(self) -> None:
        kage_bin = self._window.kage_bin
        if kage_bin:
            version = commands.kage_version(kage_bin)
            self._installed.set_text(f"Instalado: kage {version}  ({kage_bin})")
            self._btn_setup.set_label("Reinstalar kage…")
        else:
            self._installed.set_text("Instalado: no se encontró kage.")
            self._btn_setup.set_label("Instalar kage…")
        chrome = previews.find_chrome_binary()
        self._chrome.set_text(
            f"Chrome/Chromium para clonar y previews: {chrome or 'no encontrado (kage descargará uno al primer clone)'}")

    def _check(self, _btn) -> None:
        self._btn_check.set_sensitive(False)
        self._update_status.set_text("Consultando GitHub…")
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self) -> None:
        try:
            release = updates.fetch_latest()
        except Exception as exc:  # red caída, proxy, etc.
            _idle(self._check_failed, str(exc))
            return
        _idle(self._check_done, release)

    def _check_failed(self, message: str) -> None:
        self._btn_check.set_sensitive(True)
        self._update_status.set_text(f"No se pudo consultar: {message}")

    def _check_done(self, release: updates.ReleaseInfo) -> None:
        self._release = release
        self._btn_check.set_sensitive(True)
        self._btn_release.set_sensitive(True)
        self._btn_deb.set_sensitive(bool(release.deb_amd64_url))
        installed = commands.kage_version(self._window.kage_bin) \
            if self._window.kage_bin else ""
        if not installed:
            self._update_status.set_text(
                f"Última versión disponible: {release.tag}. "
                "kage no está instalado: usa «Instalar kage…».")
        elif updates.is_newer(release.version, installed):
            self._update_status.set_text(
                f"Hay una actualización: tienes {installed} y la última es "
                f"{release.version} ({release.published[:10]}). Descarga el "
                ".deb o actualiza con apt.")
        else:
            self._update_status.set_text(
                f"Estás al día: kage {installed} es la última versión "
                f"({release.tag}).")


# ---------------------------------------------------------------------------
# Vista: Preferencias (configuración y accesos del proyecto)
# ---------------------------------------------------------------------------

class PreferencesPage(Gtk.Box):
    """Agrupa la configuración de la app y los accesos a kage (docs/repo)."""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self._window = window
        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)

        self.append(_label("Apariencia", bold=True))
        self.theme_dropdown = Gtk.DropDown.new_from_strings(list(_THEME_LABELS))
        self.theme_dropdown.set_selected(
            _THEME_ORDER.index(window._cfg["theme"]))
        self.theme_dropdown.connect("notify::selected", window._on_theme_changed)
        self.append(_row("Tema", self.theme_dropdown))

        self.append(_label("Carpeta de destino", bold=True))
        self._root_label = Gtk.Label(label="", xalign=0, selectable=True)
        self.append(self._root_label)
        dest_buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        open_dest = Gtk.Button(label="Abrir carpeta de destino")
        open_dest.connect("clicked", self._open_destination)
        dest_buttons.append(open_dest)
        open_config = Gtk.Button(label="Abrir carpeta de configuración")
        open_config.connect(
            "clicked",
            lambda *_: open_folder(os.path.dirname(config.config_path())))
        dest_buttons.append(open_config)
        self.append(dest_buttons)

        self.append(_label("Documentación y proyecto kage", bold=True))
        links = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for text, url in (
            ("Documentación oficial de kage", updates.DOCS_URL),
            ("Repositorio en GitHub", updates.REPO_URL),
            ("Releases y descargas", updates.RELEASES_URL),
            ("Issues (problemas y sugerencias)", updates.ISSUES_URL),
        ):
            btn = Gtk.Button(label=f"{text}  —  {url}")
            btn.set_halign(Gtk.Align.START)
            btn.connect("clicked", lambda *_b, u=url: webbrowser.open(u))
            links.append(btn)
        self.append(links)

        self._status = Gtk.Label(label="", xalign=0)
        self.append(self._status)
        self.refresh()

    def refresh(self) -> None:
        self._root_label.set_text(
            f"Las páginas clonadas quedan en: {self._window.out_root()}")

    def _open_destination(self, _btn) -> None:
        root = self._window.out_root()
        if open_folder(root):
            self._status.set_text(f"Abriendo {root} en el explorador…")
        else:
            self._status.set_text(f"No se pudo abrir {root}.")


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
        self.set_default_size(900, 660)

        self._cfg = config.load_config()
        apply_theme(self._cfg["theme"])

        provider = Gtk.CssProvider()
        provider.load_from_string(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.kage_bin = commands.find_kage()
        self._clone_page = ClonePage(self)
        self._library_page = LibraryPage(self)
        self._zim_page = OpenZimPage(self)
        self._sistema_page = SistemaPage(self)
        self._prefs_page = PreferencesPage(self)

        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        stack.add_titled(self._clone_page, "clone", "Clonar")
        stack.add_titled(self._library_page, "library", "Biblioteca")
        stack.add_titled(self._zim_page, "zim", "Abrir ZIM")
        stack.add_titled(self._sistema_page, "sistema", "Sistema")
        stack.add_titled(self._prefs_page, "preferencias", "Preferencias")
        stack.connect("notify::visible-child",
                      lambda *_: self._prefs_page.refresh())
        self._stack = stack

        header = Gtk.HeaderBar()
        header.set_title_widget(Gtk.StackSwitcher(stack=stack))
        self._version_label = Gtk.Label(label="")
        header.pack_end(self._version_label)
        self._theme_dropdown = Gtk.DropDown.new_from_strings(list(_THEME_LABELS))
        self._theme_dropdown.set_tooltip_text("Tema de la interfaz")
        self._theme_dropdown.set_selected(_THEME_ORDER.index(self._cfg["theme"]))
        self._theme_dropdown.connect("notify::selected", self._on_theme_changed)
        header.pack_end(self._theme_dropdown)
        self.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._banner = Gtk.InfoBar(message_type=Gtk.MessageType.WARNING)
        self._banner.set_show_close_button(True)
        banner_label = Gtk.Label(
            label="No encuentro el binario «kage». Abre la pestaña Sistema "
                  "para instalarlo desde aquí.")
        self._banner.add_child(banner_label)
        root.append(self._banner)
        root.append(stack)
        self.set_child(root)

        self.refresh_kage_status()

        first_run = not self._cfg.get("welcomed", False)
        if first_run:
            self._cfg["welcomed"] = True
            config.save_config(self._cfg)
        if not self.kage_bin:
            # Primera vez (o cualquier arranque) sin kage: ofrecer instalación.
            GLib.timeout_add(500, self._offer_setup)

    def _offer_setup(self) -> bool:
        if not self.kage_bin:
            SetupDialog(self).present()
        return False

    def _on_theme_changed(self, dropdown, _param) -> None:
        if getattr(self, "_syncing_theme", False):
            return
        self.set_theme(_THEME_ORDER[dropdown.get_selected()])

    def set_theme(self, mode: str) -> None:
        """Aplica y guarda el tema, sincronizando los dos selectores."""
        self._cfg["theme"] = mode
        config.save_config(self._cfg)
        apply_theme(mode)
        self._syncing_theme = True
        try:
            index = _THEME_ORDER.index(mode)
            self._theme_dropdown.set_selected(index)
            self._prefs_page.theme_dropdown.set_selected(index)
        finally:
            self._syncing_theme = False

    def refresh_kage_status(self) -> str | None:
        """Re-detecta kage y actualiza header, banner y pestaña Sistema."""
        self.kage_bin = commands.find_kage()
        if self.kage_bin:
            version = commands.kage_version(self.kage_bin)
            self._version_label.set_text(f"kage {version}".strip())
            self._banner.set_visible(False)
        else:
            self._version_label.set_text("sin kage")
            self._banner.set_visible(True)
        self._sistema_page.refresh_status()
        return self.kage_bin

    def out_root(self) -> str:
        return os.path.expanduser(self._clone_page._out.get_text().strip()) \
            or commands.DEFAULT_OUT_ROOT

    def refresh_library(self) -> None:
        self._library_page.refresh()
        self._prefs_page.refresh()
