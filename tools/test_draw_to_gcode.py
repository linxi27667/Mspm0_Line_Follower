#!/usr/bin/env python3
"""Host-side tests for draw_to_gcode.py."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw


TOOLS = Path(__file__).resolve().parent
CONVERTER = TOOLS / "draw_to_gcode.py"


class DrawToGcodeTests(unittest.TestCase):
    def run_converter(
        self, input_path: Path, *extra: str
    ) -> tuple[Path, Path, Path, Path]:
        output = input_path.with_suffix(".gcode")
        preview = input_path.with_suffix(".preview.png")
        vector = input_path.with_suffix(".vector.svg")
        manifest = input_path.with_suffix(".json")
        command = [
            sys.executable,
            str(CONVERTER),
            str(input_path),
            "--output",
            str(output),
            "--preview",
            str(preview),
            "--vector",
            str(vector),
            "--manifest",
            str(manifest),
            *extra,
        ]
        completed = subprocess.run(
            command,
            cwd=TOOLS.parent,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        return output, preview, vector, manifest

    def assert_gcode_state_contract(self, text: str) -> None:
        pen_down = False
        path_count = 0
        for raw_line in text.splitlines():
            line = raw_line.split(";", 1)[0].strip()
            if not line:
                continue
            if line == "M3":
                self.assertFalse(pen_down)
                pen_down = True
                path_count += 1
            elif line == "M5":
                pen_down = False
            elif line.startswith("G0 "):
                self.assertFalse(pen_down)
            elif line.startswith("G1 "):
                self.assertTrue(pen_down)
            elif re.match(r"G(?:2|3|20|28)(?:\s|$)", line):
                self.fail(f"unsupported command: {line}")
            self.assertLess(len(raw_line), 192)
        self.assertFalse(pen_down)
        self.assertGreater(path_count, 0)

    def test_png_outline_generates_audited_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "line_art.png"
            image = Image.new("L", (180, 120), "white")
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((15, 15, 165, 105), radius=18, outline="black", width=6)
            draw.line((35, 85, 90, 35, 145, 85), fill="black", width=5)
            image.save(source)

            output, preview, vector, manifest_path = self.run_converter(source)
            self.assertTrue(output.is_file())
            self.assertTrue(preview.is_file())
            self.assertTrue(vector.is_file())
            self.assert_gcode_state_contract(output.read_text(encoding="ascii"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertFalse(manifest["machine_contract"]["offline_mapping"])
            self.assertEqual(manifest["input"]["type"], "raster")
            self.assertGreaterEqual(
                manifest["safety"]["drawing_sequence"]["minimum_joint_margin_deg"],
                15.0,
            )
            bounds = manifest["safety"]["paper_bounds_mm"]
            self.assertGreaterEqual(bounds[0], 25.0)
            self.assertGreaterEqual(bounds[1], 130.0)
            self.assertLessEqual(bounds[2], 185.0)
            self.assertLessEqual(bounds[3], 235.0)
            vector_root = ET.parse(vector).getroot()
            self.assertEqual(vector_root.attrib["viewBox"], "0 0 210 297")
            vector_paths = vector_root.findall(
                ".//{http://www.w3.org/2000/svg}path"
            )
            self.assertEqual(len(vector_paths), manifest["safety"]["path_count"])

    def test_png_hatch_uses_multiple_open_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "filled.png"
            image = Image.new("L", (100, 100), "white")
            ImageDraw.Draw(image).ellipse((10, 10, 90, 90), fill="black")
            image.save(source)

            output, _, _, manifest_path = self.run_converter(
                source, "--mode", "hatch", "--hatch-spacing-mm", "3"
            )
            self.assert_gcode_state_contract(output.read_text(encoding="ascii"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["conversion"]["mode"], "hatch")
            self.assertGreater(manifest["safety"]["path_count"], 10)

    def test_svg_curves_are_flattened_to_g1(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "curve.svg"
            source.write_text(
                """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80">
  <path d="M 10 60 C 25 5, 95 5, 110 60" fill="none" stroke="black"/>
  <circle cx="60" cy="42" r="18" fill="none" stroke="black"/>
</svg>
""",
                encoding="utf-8",
            )
            output, _, _, manifest_path = self.run_converter(source)
            text = output.read_text(encoding="ascii")
            self.assert_gcode_state_contract(text)
            self.assertNotIn("G2 ", text)
            self.assertNotIn("G3 ", text)
            self.assertGreater(text.count("G1 "), 20)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["input"]["type"], "svg")

    def test_unverified_target_frame_is_rejected_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "dot.png"
            image = Image.new("L", (30, 30), "white")
            ImageDraw.Draw(image).rectangle((5, 5, 25, 25), fill="black")
            image.save(source)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(CONVERTER),
                    str(source),
                    "--bottom-mm",
                    "100",
                    "--height-mm",
                    "20",
                ],
                cwd=TOOLS.parent,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("verified upper", completed.stderr)

    def test_existing_outputs_require_force(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "box.png"
            image = Image.new("L", (40, 40), "white")
            ImageDraw.Draw(image).rectangle((5, 5, 35, 35), outline="black", width=3)
            image.save(source)
            output, preview, vector, manifest = self.run_converter(source)

            command = [
                sys.executable,
                str(CONVERTER),
                str(source),
                "--output",
                str(output),
                "--preview",
                str(preview),
                "--vector",
                str(vector),
                "--manifest",
                str(manifest),
            ]
            refused = subprocess.run(
                command,
                cwd=TOOLS.parent,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(refused.returncode, 2)
            self.assertIn("pass --force", refused.stderr)

            replaced = subprocess.run(
                [*command, "--force"],
                cwd=TOOLS.parent,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(replaced.returncode, 0, msg=replaced.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
