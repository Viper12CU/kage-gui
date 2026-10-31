"""Ejecución de procesos kage: salida en vivo, progreso y cancelación.

Sin dependencias de GTK. Los callbacks se invocan desde el hilo lector;
la capa de UI es responsable de saltar al hilo principal (GLib.idle_add).

Hechos de kage que este módulo encapsula (verificados en el estudio):
- Casi toda la salida va a stderr y lleva colores ANSI.
- El progreso se sobrescribe con \\r y tiene la forma
  "pages N  assets N  errors N  skipped N".
- `clone` puede terminar con código 0 aunque alguna página falle: el
  resumen final ("done <dir>") y el contador de errores mandan.
- Cancelar es SIGINT: kage guarda el estado en _kage/state.json y el
  clon se puede reanudar en la siguiente corrida. Nunca SIGKILL primero.
"""

from __future__ import annotations

import re
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_COUNTER_RE = re.compile(r"(pages|assets|errors|skipped)\s+(\d+)")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


@dataclass
class Counters:
    pages: int = 0
    assets: int = 0
    errors: int = 0
    skipped: int = 0

    def update_from_line(self, line: str) -> bool:
        """Actualiza los contadores presentes en la línea. True si cambió algo."""
        found = _COUNTER_RE.findall(line)
        if not found:
            return False
        for key, value in found:
            setattr(self, key, int(value))
        return True

    def summary(self) -> str:
        return (f"{self.pages} páginas · {self.assets} assets · "
                f"{self.errors} errores · {self.skipped} omitidas")


@dataclass
class ProcessRunner:
    """Corre un comando, emite líneas limpias y contadores, y sabe cancelar."""

    on_line: Callable[[str], None] = lambda line: None
    on_counters: Callable[[Counters], None] = lambda counters: None
    on_exit: Callable[[int], None] = lambda code: None

    _proc: subprocess.Popen | None = field(default=None, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    counters: Counters = field(default_factory=Counters, init=False)
    done_dir: str = field(default="", init=False)

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, cmd: list[str]) -> None:
        if self.running:
            raise RuntimeError("ya hay un proceso en curso")
        self.counters = Counters()
        self.done_dir = ""
        self.on_line("$ " + " ".join(cmd))
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,   # kage escribe el progreso a stderr
            text=True,
            bufsize=1,
        )
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self) -> None:
        proc = self._proc
        assert proc is not None and proc.stdout is not None
        # newline=None (defecto en modo texto): \r, \n y \r\n separan líneas,
        # así que cada refresco del progreso llega como su propia "línea".
        for raw in proc.stdout:
            line = strip_ansi(raw).strip()
            if not line:
                continue
            if line.startswith("done ") or line.startswith("done\t"):
                self.done_dir = line[5:].strip()
            if self.counters.update_from_line(line):
                self.on_counters(self.counters)
            self.on_line(line)
        code = proc.wait()
        self.on_exit(code)

    def cancel(self, grace_seconds: float = 5.0) -> None:
        """SIGINT primero (kage guarda estado); si no sale, terminate/kill."""
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return

        def _escalate() -> None:
            try:
                proc.send_signal(signal.SIGINT)
                proc.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except OSError:
                pass

        threading.Thread(target=_escalate, daemon=True).start()

    def stop_server(self) -> None:
        """Para serve/open basta SIGTERM: no hay estado que guardar."""
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
