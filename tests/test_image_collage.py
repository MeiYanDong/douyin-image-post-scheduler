from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "idea-subtitle-collage" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from collage_layout import render_collage
from render_image_collage import read_images


def test_font():
    for candidate in ["DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"]:
        try:
            return ImageFont.truetype(candidate, 24).path
        except OSError:
            continue
    raise RuntimeError("Tests need DejaVu Sans or Arial Unicode")


class ImageCollageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.image = self.root / "scene.png"
        self.second = self.root / "second.png"
        Image.new("RGB", (720, 960), (45, 60, 80)).save(self.image)
        Image.new("RGB", (720, 960), (100, 55, 35)).save(self.second)
        self.script = self.root / "post.json"
        self.data = {"title": "New tools", "body": "A creator's commentary.",
                     "tags": ["#AI", "#Tools", "#Work", "#Tech", "#Creator"],
                     "label": "Creator commentary",
                     "lines": ["Ready?", "A new tool", "Another subscription", "Back to work"]}
        self.font = test_font()

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *output):
        self.script.write_text(json.dumps(self.data), encoding="utf-8")
        return subprocess.run([sys.executable, str(SCRIPTS / "render_image_collage.py"),
                               "--image", str(self.image), "--script", str(self.script),
                               "--font", self.font, *map(str, output)],
                              text=True, capture_output=True, check=False)

    def test_layout_has_no_gaps_and_readable_white_subtitles(self):
        colors = [(30, 60, 90), (100, 55, 30), (40, 90, 60), (90, 50, 100), (100, 100, 40)]
        for count, expected_fraction in [(5, 0.7), (4, 0.775), (3, 0.82)]:
            with self.subTest(count=count):
                frames = [Image.new("RGB", (720, 960), color) for color in colors[:count]]
                canvas, layout = render_collage(frames, ["Readable line"] * count,
                                                font_path=self.font, label="Commentary")
                self.assertEqual(canvas.size, (1080, 1440))
                self.assertAlmostEqual(layout["hero_fraction"], expected_fraction)
                y = 0
                for region, color, line in zip(layout["regions"], colors, layout["lines"]):
                    self.assertEqual(region["y"], y)
                    self.assertEqual(canvas.getpixel((0, y)), color)
                    self.assertEqual(canvas.getpixel((0, y + region["height"] - 1)), color)
                    bounds = line["bounds"]
                    self.assertGreaterEqual(bounds[1], y)
                    self.assertLessEqual(bounds[3], y + region["height"])
                    pixels = set(canvas.crop(tuple(bounds)).getdata())
                    self.assertIn((255, 255, 255), pixels)
                    self.assertIn((0, 0, 0), pixels)
                    y += region["height"]
                self.assertEqual(y, 1440)

    def test_post_export_feeds_existing_queue_without_padding_images(self):
        self.data["lines"][1] = {"text": "Different scene", "image": "second.png"}
        post = self.root / "content" / "001_New tools"
        result = self.run_cli("--post-dir", post)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((post / "05_生成清单.json").read_text(encoding="utf-8"))
        image_path = Path(manifest["output_image"])
        with Image.open(image_path) as image:
            self.assertEqual(image.size, (1080, 1440))
            image.verify()
        self.assertEqual(manifest["output_sha256"], hashlib.sha256(image_path.read_bytes()).hexdigest())
        self.assertEqual(manifest["line_images"][1], str(self.second.resolve()))
        self.assertEqual(len(manifest["source_images"]), 2)
        queue = self.root / "queue.json"
        prepared = subprocess.run(
            [sys.executable, str(ROOT / "skills" / "douyin-image-post-scheduler" / "scripts" / "prepare_queue.py"),
             str(post.parent), "--start-date", "2026-10-01", "--image-count", "1", "--seed", "123",
             "--json-output", str(queue)], text=True, capture_output=True, check=False)
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        item = json.loads(queue.read_text(encoding="utf-8"))["items"][0]
        self.assertEqual(item["images"], [str(image_path)])
        self.assertEqual(item["title"], self.data["title"])
        self.assertEqual(item["body"], self.data["body"])
        self.assertFalse(item["body_truncated"])
        self.assertEqual(item["tags"], self.data["tags"])

    def test_invalid_input_fails_before_creating_output(self):
        for lines in [["only one"], ["first", ""], ["first", "two\nlines"],
                      [{"text": "first", "t": 0}, "second"], ["first", "W" * 200]]:
            with self.subTest(lines=lines):
                self.data["lines"] = lines
                out = self.root / "invalid.jpg"
                result = self.run_cli("--out", out)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(out.exists())
                self.assertFalse(out.with_suffix(".json").exists())

    def test_existing_output_and_post_are_preserved(self):
        out = self.root / "existing.jpg"
        out.write_bytes(b"keep existing image")
        self.assertEqual(self.run_cli("--out", out).returncode, 2)
        self.assertEqual(out.read_bytes(), b"keep existing image")
        post = self.root / "001_Existing"
        post.mkdir()
        sentinel = post / "keep.txt"
        sentinel.write_text("keep existing post")
        self.assertEqual(self.run_cli("--post-dir", post).returncode, 2)
        self.assertEqual(sentinel.read_text(), "keep existing post")

    def test_invalid_post_fields_do_not_create_package(self):
        for field, value in [("title", "../bad"), ("body", "A" * 1000),
                             ("tags", ["#same"] * 5)]:
            with self.subTest(field=field):
                previous = self.data[field]
                self.data[field] = value
                post = self.root / "001_Invalid"
                self.assertEqual(self.run_cli("--post-dir", post).returncode, 2)
                self.assertFalse(post.exists())
                self.data[field] = previous

    def test_camera_orientation_is_applied_before_layout(self):
        photo = self.root / "rotated.jpg"
        original = Image.new("RGB", (80, 40), (20, 30, 40))
        exif = original.getexif()
        exif[274] = 6
        original.save(photo, exif=exif)
        frames, sources = read_images([photo])
        self.assertEqual(frames[0].size, (40, 80))
        self.assertEqual((sources[0]["width"], sources[0]["height"]), (40, 80))


if __name__ == "__main__":
    unittest.main()
