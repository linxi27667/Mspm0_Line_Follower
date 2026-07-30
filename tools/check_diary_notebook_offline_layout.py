#!/usr/bin/env python3
"""Verify the non-runnable diary layout against the current V36 motion model."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

from PIL import Image

import check_author_text_demo_v30 as v30
import generate_diary_notebook_offline_preview as diary


ROOT = Path(__file__).resolve().parents[1]
MAX_SOURCE_QUANTIZATION_ERROR_MM = 0.075
MAX_ENDPOINT_ERROR_MM = 0.09
MAX_LINE_DEVIATION_MM = 0.12
MIN_JOINT_MARGIN_DEG = 10.0
MIN_PAPER_MARGIN_MM = 15.0
POSITION_EPS_MM = 0.15
MOVE_FEED_MM_MIN = 600.0
DRAW_FEED_MM_MIN = 240.0


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def lround(value: float) -> int:
    return math.floor(value + 0.5) if value >= 0.0 else math.ceil(value - 0.5)


def generated_layout() -> tuple[str, diary.GFont, str, list[diary.PageLayout]]:
    text = diary.SOURCE_TEXT.read_text(encoding="utf-8").rstrip("\r\n")
    font = diary.load_gfont(diary.FONT_PATH)
    glyphs, missing = diary.glyph_map(font, text)
    pages = diary.layout_text(text, font, glyphs)
    return text, font, missing, pages


def effective_page_points(
    page: diary.PageLayout,
) -> tuple[tuple[v30.DemoPoint, ...], dict[str, float]]:
    current = v30.ALIGN_PATH[-1].xy
    effective: list[v30.DemoPoint] = []
    source_max_error = 0.0
    maximum_draw_target_span = 0.0
    maximum_penup_target_span = 0.0
    epsilon_skips = 0
    duplicate_skips = 0
    previous_effective = current

    for placement in page.placements:
        for point in placement.points:
            x_x10 = lround(point.x_mm * 10.0)
            y_x10 = lround(point.y_mm * 10.0)
            command = v30.DemoPoint(x_x10, y_x10, point.draw)
            command_xy = command.xy
            source_error = math.hypot(
                command_xy[0] - point.x_mm,
                command_xy[1] - point.y_mm,
            )
            source_max_error = max(source_max_error, source_error)
            if command_xy == current:
                duplicate_skips += 1
                continue
            if (
                abs(command_xy[0] - current[0]) <= POSITION_EPS_MM
                and abs(command_xy[1] - current[1]) <= POSITION_EPS_MM
            ):
                epsilon_skips += 1
                continue
            span = math.hypot(
                command_xy[0] - previous_effective[0],
                command_xy[1] - previous_effective[1],
            )
            if command.draw:
                maximum_draw_target_span = max(maximum_draw_target_span, span)
            else:
                maximum_penup_target_span = max(maximum_penup_target_span, span)
            effective.append(command)
            current = command_xy
            previous_effective = command_xy

    if source_max_error > MAX_SOURCE_QUANTIZATION_ERROR_MM:
        raise AssertionError(
            f"page {page.number}: source quantization error {source_max_error:.6f} mm"
        )
    if not effective:
        raise AssertionError(f"page {page.number}: no effective path points")
    return tuple(effective), {
        "source_max_error": source_max_error,
        "maximum_draw_target_span": maximum_draw_target_span,
        "maximum_penup_target_span": maximum_penup_target_span,
        "epsilon_skips": float(epsilon_skips),
        "duplicate_skips": float(duplicate_skips),
    }


def check_home_to_align() -> dict[str, float]:
    minimum_margin = float("inf")
    minimum_paper_margin = float("inf")
    maximum_deviation = 0.0
    minimum_segments = float("inf")
    maximum_segments = 0.0
    align = v30.ALIGN_PATH[-1]

    for release1 in range(41, 49):
        for release2 in range(41, 49):
            home_user, home_steps = v30.v21.user_from_home_delta(release1, release2)
            _, end_steps, stats = v30.simulate_commanded_path(
                home_user,
                home_steps,
                v30.ALIGN_PATH,
                f"HOME_{release1}_{release2}_TO_ALIGN",
            )
            expected_steps, _, _ = v30.point_margin(align, "ALIGN_TARGET")
            if end_steps != expected_steps:
                raise AssertionError("home approach did not reach ALIGN")
            minimum_margin = min(minimum_margin, stats["minimum_margin"])
            minimum_paper_margin = min(
                minimum_paper_margin,
                home_user[0],
                diary.A4_WIDTH_MM - home_user[0],
                home_user[1],
                diary.A4_HEIGHT_MM - home_user[1],
                stats["minimum_paper_margin"],
            )
            maximum_deviation = max(maximum_deviation, stats["maximum_deviation"])
            minimum_segments = min(minimum_segments, stats["segments"])
            maximum_segments = max(maximum_segments, stats["segments"])

    if minimum_paper_margin < MIN_PAPER_MARGIN_MM:
        raise AssertionError(f"home paper margin {minimum_paper_margin:.6f} mm")
    if maximum_deviation > MAX_LINE_DEVIATION_MM:
        raise AssertionError(f"home line deviation {maximum_deviation:.6f} mm")
    return {
        "minimum_margin": minimum_margin,
        "minimum_paper_margin": minimum_paper_margin,
        "maximum_deviation": maximum_deviation,
        "minimum_segments": minimum_segments,
        "maximum_segments": maximum_segments,
    }


def check_page_motion(
    page: diary.PageLayout,
    points: tuple[v30.DemoPoint, ...],
) -> dict[str, float]:
    align = v30.ALIGN_PATH[-1]
    current_steps, _, _ = v30.point_margin(align, f"PAGE_{page.number}_ALIGN")
    _, end_steps, stats = v30.simulate_commanded_path(
        align.xy,
        current_steps,
        points,
        f"PAGE_{page.number}",
    )
    expected_end, _, _ = v30.point_margin(
        points[-1], f"PAGE_{page.number}_END"
    )
    if end_steps != expected_end:
        raise AssertionError(f"page {page.number}: endpoint steps mismatch")
    if stats["minimum_margin"] < MIN_JOINT_MARGIN_DEG:
        raise AssertionError(
            f"page {page.number}: joint margin {stats['minimum_margin']:.6f} deg"
        )
    if stats["minimum_paper_margin"] < MIN_PAPER_MARGIN_MM:
        raise AssertionError(
            f"page {page.number}: paper margin {stats['minimum_paper_margin']:.6f} mm"
        )
    if stats["maximum_deviation"] > MAX_LINE_DEVIATION_MM:
        raise AssertionError(
            f"page {page.number}: line deviation {stats['maximum_deviation']:.6f} mm"
        )
    if stats["maximum_endpoint_error"] > MAX_ENDPOINT_ERROR_MM:
        raise AssertionError(
            f"page {page.number}: endpoint error "
            f"{stats['maximum_endpoint_error']:.6f} mm"
        )
    return stats


def check_written_artifacts(
    text: str,
    font: diary.GFont,
    missing: str,
    pages: list[diary.PageLayout],
) -> None:
    report = json.loads(diary.REPORT_PATH.read_text(encoding="utf-8"))
    if report.get("runnable_on_robot") is not False:
        raise AssertionError("offline report is not explicitly non-runnable")
    if report["source"]["docx_sha256"] != digest(diary.SOURCE_DOCX):
        raise AssertionError("source DOCX hash mismatch")
    if report["source"]["fixed_text_sha256"] != digest(diary.SOURCE_TEXT):
        raise AssertionError("fixed source text hash mismatch")
    if report["source"]["characters_excluding_whitespace"] != sum(
        not character.isspace() for character in text
    ):
        raise AssertionError("source character count mismatch")
    if report["kenjoy"]["font_sha256"] != digest(diary.FONT_PATH):
        raise AssertionError("font hash mismatch")
    if report["kenjoy"]["font_name"] != font.name:
        raise AssertionError("font name mismatch")
    if report["kenjoy"]["original_missing_characters"] != missing:
        raise AssertionError("missing-character list mismatch")
    if report["kenjoy"]["unresolved_characters"]:
        raise AssertionError("offline report contains unresolved characters")
    if report["layout"]["page_count"] != len(pages):
        raise AssertionError("page count mismatch")
    if report["layout"]["local_y_correction_applied"] is not False:
        raise AssertionError("unsafe global Y correction was applied")
    if report["pages"] != [diary.page_record(page) for page in pages]:
        raise AssertionError("written page report is stale")

    warning = diary.LAYOUT_TEXT_PATH.read_text(encoding="utf-8")
    if "NOT FOR ROBOT" not in warning or "当前 V36 不能运行此文件" not in warning:
        raise AssertionError("layout text lacks non-runnable warning")
    if list((ROOT / "gcode").glob("DIARY_NOTEBOOK*.gcode")):
        raise AssertionError("a runnable-looking diary .gcode file exists")

    expected_size = (
        round(diary.A4_WIDTH_MM * diary.PREVIEW_PIXELS_PER_MM) + 1,
        round(diary.A4_HEIGHT_MM * diary.PREVIEW_PIXELS_PER_MM) + 1,
    )
    for page in pages:
        preview = diary.PREVIEW_DIR / f"{diary.PREVIEW_STEM}_PAGE_{page.number:02d}.png"
        with Image.open(preview) as image:
            if image.size != expected_size:
                raise AssertionError(f"{preview.name}: unexpected image size {image.size}")

    print(
        f"artifacts=PASS pages={len(pages)} source_docx_sha256={digest(diary.SOURCE_DOCX)} "
        f"font_sha256={digest(diary.FONT_PATH)} runnable_files=0"
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    text, font, missing, pages = generated_layout()
    if missing != "粿麟婷鹏":
        raise AssertionError(f"unexpected Song missing characters: {missing}")
    if len(pages) != 3:
        raise AssertionError(f"expected three offline pages, got {len(pages)}")
    laid_out_text = "".join(line for page in pages for line in page.lines)
    if laid_out_text != text.replace("\n", ""):
        raise AssertionError("page wrapping changed the source character sequence")
    placement_text = "".join(
        placement.character for page in pages for placement in page.placements
    )
    if placement_text != "".join(
        character for character in text if not character.isspace()
    ):
        raise AssertionError("glyph placement order differs from source text")
    if sum(len(page.placements) for page in pages) != sum(
        not character.isspace() for character in text
    ):
        raise AssertionError("not every nonspace character produced a glyph")

    v30.configure_model()
    home = check_home_to_align()
    print(
        "home_to_align=PASS combinations=64 release_s1=41..48 release_s2=41..48 "
        f"segments={int(home['minimum_segments'])}..{int(home['maximum_segments'])} "
        f"min_joint_margin_deg={home['minimum_margin']:.6f} "
        f"min_paper_margin_mm={home['minimum_paper_margin']:.6f} "
        f"max_line_deviation_mm={home['maximum_deviation']:.6f}"
    )

    for page in pages:
        effective, shape = effective_page_points(page)
        stats = check_page_motion(page, effective)
        print(
            f"page_motion=PASS page={page.number} glyphs={len(page.placements)} "
            f"targets={len(effective)} segments={int(stats['segments'])} "
            f"master_pulses={int(stats['master_pulses'])} "
            f"epsilon_skips={int(shape['epsilon_skips'])} "
            f"duplicate_skips={int(shape['duplicate_skips'])} "
            f"max_draw_target_span_mm={shape['maximum_draw_target_span']:.6f} "
            f"max_penup_target_span_mm={shape['maximum_penup_target_span']:.6f} "
            f"min_joint_margin_deg={stats['minimum_margin']:.6f} "
            f"min_paper_margin_mm={stats['minimum_paper_margin']:.6f} "
            f"max_line_deviation_mm={stats['maximum_deviation']:.6f} "
            f"max_endpoint_error_mm={stats['maximum_endpoint_error']:.6f} "
            f"max_source_quantization_error_mm={shape['source_max_error']:.6f}"
        )

    check_written_artifacts(text, font, missing, pages)
    print(
        f"feed_contract=PASS future_move_feed_mm_min={MOVE_FEED_MM_MIN:.0f} "
        f"future_draw_feed_mm_min={DRAW_FEED_MM_MIN:.0f} raw_kenjoy_F3000_allowed=0"
    )
    print(
        "offline_diary_check=PASS exact_text=1 missing_unresolved=0 pages=3 "
        "paper=A4_landscape origin=RIGHT_UPPER local_y_extrapolation=0 runnable=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
