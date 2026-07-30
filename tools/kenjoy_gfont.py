#!/usr/bin/env python3
"""Read the proprietary Kenjoy ``.gfont`` container without launching its GUI.

The format was reconstructed from the locally archived Kenjoy classes
``com.kenjoy.kenjoycnc.e.s`` and ``com.kenjoy.kenjoycnc.e.a``.  Java writes a
small DataInputStream header followed by a ZIP archive.  Each ZIP member stores
one character as a sequence of move (0) and draw (1) points.

This module is intentionally read-only.  It is used by the diary layout and
safety tooling to prove font coverage and to obtain the exact single-line paths
that Kenjoy's Note mode would use.
"""

from __future__ import annotations

import argparse
import io
import json
import struct
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable


class GFontError(ValueError):
    """Raised when a gfont file does not match the archived Kenjoy format."""


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise GFontError(f"unexpected end of file: wanted {size}, got {len(data)}")
    return data


def _u16(stream: BinaryIO) -> int:
    return struct.unpack(">H", _read_exact(stream, 2))[0]


def _i32(stream: BinaryIO) -> int:
    return struct.unpack(">i", _read_exact(stream, 4))[0]


def _f32(stream: BinaryIO) -> float:
    return struct.unpack(">f", _read_exact(stream, 4))[0]


def _modified_utf8(data: bytes) -> str:
    # DataOutputStream.writeUTF differs from UTF-8 only for NUL and surrogate
    # code units.  Decode those explicitly so the parser remains deterministic.
    data = data.replace(b"\xC0\x80", b"\x00")
    return data.decode("utf-8", errors="surrogatepass")


def _java_utf(stream: BinaryIO) -> str:
    return _modified_utf8(_read_exact(stream, _u16(stream)))


@dataclass(frozen=True)
class Glyph:
    character: str
    points: tuple[tuple[float, float], ...]
    commands: tuple[int, ...]

    @property
    def stroke_count(self) -> int:
        return sum(command == 0 for command in self.commands)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        if not self.points:
            return (0.0, 0.0, 0.0, 0.0)
        xs = [point[0] for point in self.points]
        ys = [point[1] for point in self.points]
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass(frozen=True)
class GFont:
    path: Path
    version: int
    name: str
    font_id: str
    description: str
    em_size: int
    archive_flag: int
    glyphs: dict[str, Glyph]


def _read_glyph(stream: BinaryIO) -> Glyph:
    character = chr(_u16(stream))
    float_count = _i32(stream)
    if float_count < 0 or float_count % 2:
        raise GFontError(f"invalid float count {float_count} for {character!r}")
    values = tuple(_f32(stream) for _ in range(float_count))
    command_count = _i32(stream)
    if command_count < 0:
        raise GFontError(f"invalid command count {command_count} for {character!r}")
    commands = tuple(_read_exact(stream, command_count))
    if float_count != command_count * 2:
        raise GFontError(
            f"point/command mismatch for {character!r}: {float_count} floats, "
            f"{command_count} commands"
        )
    if any(command not in (0, 1) for command in commands):
        raise GFontError(f"unknown path command for {character!r}")
    points = tuple(zip(values[0::2], values[1::2]))
    return Glyph(character=character, points=points, commands=commands)


def load_gfont(path: str | Path, *, load_glyphs: bool = True) -> GFont:
    path = Path(path)
    raw = path.read_bytes()
    stream = io.BytesIO(raw)
    version = _i32(stream)
    name = _java_utf(stream)
    font_id = _java_utf(stream)
    description = _java_utf(stream)
    em_size = _i32(stream)
    archive_flag = _i32(stream)
    inline_count = _i32(stream)
    if inline_count < 0:
        raise GFontError(f"invalid inline glyph count {inline_count}")
    for _ in range(inline_count):
        _read_glyph(stream)

    glyphs: dict[str, Glyph] = {}
    if archive_flag:
        archive_data = raw[stream.tell() :]
        try:
            archive = zipfile.ZipFile(io.BytesIO(archive_data))
        except zipfile.BadZipFile as exc:
            raise GFontError(f"invalid embedded ZIP in {path}") from exc
        with archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                with archive.open(member) as glyph_stream:
                    glyph = _read_glyph(glyph_stream)
                if load_glyphs:
                    glyphs[glyph.character] = glyph
                else:
                    glyphs[glyph.character] = Glyph(glyph.character, (), ())
    return GFont(
        path=path,
        version=version,
        name=name,
        font_id=font_id,
        description=description,
        em_size=em_size,
        archive_flag=archive_flag,
        glyphs=glyphs,
    )


def missing_characters(font: GFont, text: str) -> str:
    seen: set[str] = set()
    missing: list[str] = []
    for character in text:
        if character.isspace() or character in seen:
            continue
        seen.add(character)
        if character not in font.glyphs:
            missing.append(character)
    return "".join(missing)


def _font_paths(target: Path) -> Iterable[Path]:
    if target.is_dir():
        return sorted(target.glob("*.gfont"), key=lambda item: item.name.lower())
    return [target]


def _main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="a .gfont file or directory")
    parser.add_argument("--text-file", type=Path, help="report missing characters")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    text = args.text_file.read_text(encoding="utf-8") if args.text_file else None
    records = []
    for path in _font_paths(args.target):
        font = load_gfont(path, load_glyphs=False)
        record = {
            "file": path.name,
            "sha256": __import__("hashlib").sha256(path.read_bytes()).hexdigest().upper(),
            "version": font.version,
            "name": font.name,
            "font_id": font.font_id,
            "description": font.description,
            "em_size": font.em_size,
            "glyphs": len(font.glyphs),
        }
        if text is not None:
            missing = missing_characters(font, text)
            record["missing"] = missing
            record["missing_count"] = len(missing)
        records.append(record)

    if args.json:
        json.dump(records, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        for record in records:
            fields = [
                record["file"],
                f"name={record['name']}",
                f"em={record['em_size']}",
                f"glyphs={record['glyphs']}",
            ]
            if "missing_count" in record:
                fields.append(f"missing={record['missing_count']}:{record['missing']}")
            print(" | ".join(fields))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
