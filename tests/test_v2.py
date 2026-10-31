"""Tests de la lógica nueva en v2: updates, config y previews (sin GTK)."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kage_gui import config, previews, updates  # noqa: E402


class TestVersions(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(updates.parse_version("v0.3.12"), (0, 3, 12))
        self.assertEqual(updates.parse_version("1.0"), (1, 0))

    def test_is_newer(self):
        self.assertTrue(updates.is_newer("0.4.0", "0.3.12"))
        self.assertTrue(updates.is_newer("0.3.13", "0.3.12"))
        self.assertFalse(updates.is_newer("0.3.12", "0.3.12"))
        self.assertFalse(updates.is_newer("0.3.9", "0.3.12"))
        self.assertTrue(updates.is_newer("0.3.12", ""))  # sin instalar

    def test_parse_release_picks_deb(self):
        payload = {
            "tag_name": "v9.9.9",
            "html_url": "https://example/release",
            "published_at": "2026-01-01T00:00:00Z",
            "body": "notas",
            "assets": [
                {"name": "kage_9.9.9_arm64.deb",
                 "browser_download_url": "https://example/arm.deb"},
                {"name": "kage_9.9.9_amd64.deb",
                 "browser_download_url": "https://example/amd.deb"},
            ],
        }
        info = updates.parse_release(payload)
        self.assertEqual(info.version, "9.9.9")
        self.assertEqual(info.deb_amd64_url, "https://example/amd.deb")


class TestConfig(unittest.TestCase):
    def test_roundtrip_and_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cfg", "config.json")
            cfg = config.load_config(path)
            self.assertEqual(cfg["theme"], "system")
            self.assertFalse(cfg["welcomed"])
            cfg["theme"] = "dark"
            cfg["welcomed"] = True
            config.save_config(cfg, path)
            again = config.load_config(path)
            self.assertEqual(again["theme"], "dark")
            self.assertTrue(again["welcomed"])

    def test_bad_theme_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            with open(path, "w") as fh:
                json.dump({"theme": "neon"}, fh)
            self.assertEqual(config.load_config(path)["theme"], "system")


class TestPreviews(unittest.TestCase):
    def test_thumbnail_name_uses_host_and_mtime(self):
        path = previews.thumbnail_file("/data/kage/paulgraham.com", 1700000000.9,
                                       cache="/tmp/thumbs")
        self.assertEqual(path, "/tmp/thumbs/paulgraham.com-1700000000.png")

    def test_no_chrome_no_thumb(self):
        with tempfile.TemporaryDirectory() as tmp:
            mirror = os.path.join(tmp, "x.com")
            os.makedirs(mirror)
            with open(os.path.join(mirror, "index.html"), "w") as fh:
                fh.write("<html></html>")
            self.assertIsNone(previews.generate_thumbnail(
                mirror, 1.0, chrome="/no/existe/chrome",
                cache=os.path.join(tmp, "thumbs")))


if __name__ == "__main__":
    unittest.main()
