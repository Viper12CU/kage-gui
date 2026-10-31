"""Tests de la lógica sin GUI. Se corren con el unittest de la stdlib:

    python3 -m unittest discover -s tests -v

No necesitan GTK ni kage instalado, salvo test_runner_integration, que usa
un binario kage real si está en tests/fixtures o en el PATH (si no, se salta).
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kage_gui.commands import (  # noqa: E402
    CloneOptions, build_clone_command, build_open_command,
    build_pack_command, build_serve_command, default_pack_output,
)
from kage_gui.library import is_mirror, scan_library  # noqa: E402
from kage_gui.runner import Counters, strip_ansi  # noqa: E402


class TestCommands(unittest.TestCase):
    def test_clone_minimal(self):
        cmd = build_clone_command("kage", CloneOptions(url="ejemplo.com"))
        self.assertEqual(cmd[:3], ["kage", "clone", "ejemplo.com"])
        self.assertIn("--out", cmd)
        self.assertNotIn("--force", cmd)
        self.assertNotIn("--max-pages", cmd)  # 0 = sin límite, no se pasa

    def test_clone_full(self):
        opts = CloneOptions(
            url="https://go.dev", max_pages=50, max_depth=2,
            scope_prefix="/doc", exclude=["/blog", "/legal"],
            subdomains=True, scroll=True, workers=8,
        )
        cmd = build_clone_command("kage", opts)
        for expected in (
            ["--max-pages", "50"], ["--max-depth", "2"],
            ["--scope-prefix", "/doc"], ["--workers", "8"],
        ):
            idx = cmd.index(expected[0])
            self.assertEqual(cmd[idx + 1], expected[1])
        self.assertEqual(cmd.count("--exclude"), 2)
        self.assertIn("--subdomains", cmd)
        self.assertIn("--scroll", cmd)

    def test_serve_open_pack(self):
        self.assertEqual(
            build_serve_command("kage", "/tmp/m", "127.0.0.1:9000"),
            ["kage", "serve", "/tmp/m", "--addr", "127.0.0.1:9000"])
        self.assertIn("--open=false", build_open_command("kage", "/tmp/a.zim"))
        pack = build_pack_command("kage", "/tmp/m", "binary", "/tmp/m-bin", app=True)
        self.assertEqual(pack[pack.index("--format") + 1], "binary")
        self.assertIn("--app", pack)

    def test_default_pack_output(self):
        self.assertEqual(
            default_pack_output("/data/kage/paulgraham.com", "zim"),
            "/data/kage/paulgraham.com.zim")
        self.assertEqual(
            default_pack_output("/data/kage/paulgraham.com", "binary"),
            "/data/kage/paulgraham.com")


class TestParsing(unittest.TestCase):
    def test_strip_ansi(self):
        self.assertEqual(strip_ansi("\x1b[92mdone\x1b[m ok"), "done ok")

    def test_counters_from_progress_line(self):
        c = Counters()
        line = strip_ansi("\x1b[90mpages 12  assets 34  errors 1  skipped 2\x1b[m")
        self.assertTrue(c.update_from_line(line))
        self.assertEqual((c.pages, c.assets, c.errors, c.skipped), (12, 34, 1, 2))

    def test_counters_from_summary_lines(self):
        # El resumen final reparte los contadores en dos líneas.
        c = Counters()
        c.update_from_line("  pages 2   assets 1")
        c.update_from_line("  errors 1  render: boom  https://x/")
        self.assertEqual((c.pages, c.assets, c.errors), (2, 1, 1))

    def test_no_counters(self):
        self.assertFalse(Counters().update_from_line("kage cloning https://x/"))


class TestLibrary(unittest.TestCase):
    def _make_mirror(self, root, host, pages):
        path = os.path.join(root, host)
        os.makedirs(os.path.join(path, "_kage"))
        with open(os.path.join(path, "index.html"), "w") as fh:
            fh.write("<html></html>")
        import json
        with open(os.path.join(path, "_kage", "state.json"), "w") as fh:
            json.dump({"visited": ["index.html"] * pages}, fh)
        return path

    def test_scan(self):
        with tempfile.TemporaryDirectory() as root:
            self._make_mirror(root, "ejemplo.com", 5)
            os.makedirs(os.path.join(root, "no-es-mirror"))
            mirrors = scan_library(root)
            self.assertEqual(len(mirrors), 1)
            self.assertEqual(mirrors[0].name, "ejemplo.com")
            self.assertEqual(mirrors[0].pages, 5)
            self.assertTrue(is_mirror(mirrors[0].path))

    def test_scan_missing_root(self):
        self.assertEqual(scan_library("/no/existe/esta/ruta"), [])


if __name__ == "__main__":
    unittest.main()
