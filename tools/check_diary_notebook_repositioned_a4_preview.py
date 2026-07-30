#!/usr/bin/env python3
"""Verify the translated-paper, one-page A4 diary preview offline."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from PIL import Image

import check_author_text_demo_v30 as v30
import check_diary_notebook_offline_layout as common
import generate_diary_notebook_offline_preview as base
import generate_diary_notebook_repositioned_a4_preview as full


ROOT = Path(__file__).resolve().parents[1]
MIN_JOINT_MARGIN_DEG = 10.0
MAX_SOURCE_QUANTIZATION_ERROR_MM = 0.075
MAX_ENDPOINT_ERROR_MM = 0.09
MAX_LINE_DEVIATION_MM = 0.12
POSITION_EPS_MM = 0.15
MAX_ROUTED_PENUP_SPAN_MM = 180.0


def lround(value: float) -> int:
    return math.floor(value + 0.5) if value >= 0.0 else math.ceil(value - 0.5)


def point_margin(x_mm: float, y_mm: float) -> float:
    model = v30.v21.base
    theta, psi = model.inverse(x_mm, y_mm)
    stage1 = model.lroundf(theta * model.STAGE1_STEPS_PER_DEG)
    stage2 = model.lroundf(psi * model.STAGE2_STEPS_PER_DEG)
    return model.require_hard_safe(stage1, stage2, "FULL_A4_GRID")


def check_full_usable_rectangle() -> float:
    minimum_margin = float("inf")
    point_count = 0
    for paper_x in range(15, 283):
        for paper_y in range(15, 196):
            command_x, command_y = full.paper_to_command(paper_x, paper_y)
            margin = point_margin(command_x, command_y)
            minimum_margin = min(minimum_margin, margin)
            point_count += 1
    if minimum_margin < MIN_JOINT_MARGIN_DEG:
        raise AssertionError(f"translated A4 grid margin {minimum_margin:.6f} deg")
    print(
        f"translated_a4_grid=PASS points={point_count} paper_x=15..282 "
        f"paper_y=15..195 command_shift=(139,-68) "
        f"min_joint_margin_deg={minimum_margin:.6f}"
    )
    return minimum_margin


def route_command_path(
    page: base.PageLayout,
) -> tuple[tuple[v30.DemoPoint, ...], dict[str, float]]:
    current = v30.ALIGN_PATH[-1].xy
    routed: list[v30.DemoPoint] = []
    maximum_source_error = 0.0
    maximum_raw_penup_span = 0.0
    maximum_routed_penup_span = 0.0
    maximum_draw_span = 0.0
    inserted_waypoints = 0
    epsilon_skips = 0
    duplicate_skips = 0

    for placement in page.placements:
        for point in placement.points:
            exact_command = full.paper_to_command(point.x_mm, point.y_mm)
            target = v30.DemoPoint(
                lround(exact_command[0] * 10.0),
                lround(exact_command[1] * 10.0),
                point.draw,
            )
            target_xy = target.xy
            source_error = math.hypot(
                target_xy[0] - exact_command[0],
                target_xy[1] - exact_command[1],
            )
            maximum_source_error = max(maximum_source_error, source_error)
            if target_xy == current:
                duplicate_skips += 1
                continue
            if (
                abs(target_xy[0] - current[0]) <= POSITION_EPS_MM
                and abs(target_xy[1] - current[1]) <= POSITION_EPS_MM
            ):
                epsilon_skips += 1
                continue

            span = math.hypot(target_xy[0] - current[0], target_xy[1] - current[1])
            if target.draw:
                maximum_draw_span = max(maximum_draw_span, span)
                if span > MAX_ROUTED_PENUP_SPAN_MM:
                    raise AssertionError(f"draw target span cannot be routed: {span:.6f} mm")
            else:
                maximum_raw_penup_span = max(maximum_raw_penup_span, span)
                route_segments = max(1, math.ceil(span / MAX_ROUTED_PENUP_SPAN_MM))
                start = current
                for route_index in range(1, route_segments):
                    ratio = route_index / route_segments
                    waypoint = v30.DemoPoint(
                        lround((start[0] + (target_xy[0] - start[0]) * ratio) * 10.0),
                        lround((start[1] + (target_xy[1] - start[1]) * ratio) * 10.0),
                        False,
                    )
                    waypoint_span = math.hypot(
                        waypoint.xy[0] - current[0], waypoint.xy[1] - current[1]
                    )
                    maximum_routed_penup_span = max(
                        maximum_routed_penup_span, waypoint_span
                    )
                    routed.append(waypoint)
                    current = waypoint.xy
                    inserted_waypoints += 1
                final_span = math.hypot(
                    target_xy[0] - current[0], target_xy[1] - current[1]
                )
                maximum_routed_penup_span = max(
                    maximum_routed_penup_span, final_span
                )

            routed.append(target)
            current = target_xy

    if maximum_source_error > MAX_SOURCE_QUANTIZATION_ERROR_MM:
        raise AssertionError(f"source quantization error {maximum_source_error:.6f} mm")
    if maximum_routed_penup_span > MAX_ROUTED_PENUP_SPAN_MM + 0.11:
        raise AssertionError(
            f"routed pen-up span {maximum_routed_penup_span:.6f} mm"
        )
    return tuple(routed), {
        "maximum_source_error": maximum_source_error,
        "maximum_raw_penup_span": maximum_raw_penup_span,
        "maximum_routed_penup_span": maximum_routed_penup_span,
        "maximum_draw_span": maximum_draw_span,
        "inserted_waypoints": float(inserted_waypoints),
        "epsilon_skips": float(epsilon_skips),
        "duplicate_skips": float(duplicate_skips),
    }


def check_routed_motion(
    points: tuple[v30.DemoPoint, ...], route: dict[str, float]
) -> dict[str, float]:
    align = v30.ALIGN_PATH[-1]
    current_steps, _, _ = v30.point_margin(align, "FULL_A4_ALIGN")
    _, end_steps, stats = v30.simulate_commanded_path(
        align.xy,
        current_steps,
        points,
        "FULL_A4_TEXT",
    )
    expected_end, _, _ = v30.point_margin(points[-1], "FULL_A4_END")
    if end_steps != expected_end:
        raise AssertionError("full A4 endpoint steps mismatch")
    if stats["minimum_margin"] < MIN_JOINT_MARGIN_DEG:
        raise AssertionError(
            f"full A4 path joint margin {stats['minimum_margin']:.6f} deg"
        )
    if stats["maximum_deviation"] > MAX_LINE_DEVIATION_MM:
        raise AssertionError(
            f"full A4 line deviation {stats['maximum_deviation']:.6f} mm"
        )
    if stats["maximum_endpoint_error"] > MAX_ENDPOINT_ERROR_MM:
        raise AssertionError(
            f"full A4 endpoint error {stats['maximum_endpoint_error']:.6f} mm"
        )

    minimum_endpoint_paper_margin = float("inf")
    for point in points:
        paper_x, paper_y = full.command_to_paper(*point.xy)
        minimum_endpoint_paper_margin = min(
            minimum_endpoint_paper_margin,
            paper_x,
            base.A4_WIDTH_MM - paper_x,
            paper_y,
            base.A4_HEIGHT_MM - paper_y,
        )
    conservative_dda_paper_margin = (
        minimum_endpoint_paper_margin - stats["maximum_deviation"]
    )
    if conservative_dda_paper_margin < 14.8:
        raise AssertionError(
            f"full A4 conservative paper margin {conservative_dda_paper_margin:.6f} mm"
        )
    stats = dict(stats)
    stats["minimum_endpoint_paper_margin"] = minimum_endpoint_paper_margin
    stats["conservative_dda_paper_margin"] = conservative_dda_paper_margin
    stats.update(route)
    return stats


def check_artifacts(
    text: str,
    font: base.GFont,
    missing: str,
    page: base.PageLayout,
) -> None:
    report = json.loads(full.REPORT_PATH.read_text(encoding="utf-8"))
    if report["runnable_on_robot"] is not False:
        raise AssertionError("repositioned A4 report is not non-runnable")
    if report["source_docx_sha256"] != base.digest(base.SOURCE_DOCX):
        raise AssertionError("source DOCX hash mismatch")
    if report["source_text_sha256"] != base.digest(base.SOURCE_TEXT):
        raise AssertionError("source text hash mismatch")
    if report["font_sha256"] != base.digest(base.FONT_PATH) or report["font_name"] != font.name:
        raise AssertionError("font identity mismatch")
    if report["missing_characters_replaced_by_disclosed_composites"] != missing:
        raise AssertionError("missing-character report mismatch")
    if report["unresolved_characters"]:
        raise AssertionError("unresolved characters remain")
    if report["layout"]["lines"] != page.lines:
        raise AssertionError("written line layout is stale")
    if report["alignment"]["new_cross_on_paper_mm"] != [11.0, 88.0]:
        raise AssertionError("paper alignment cross changed")
    if report["alignment"]["command_shift_mm"] != [139.0, -68.0]:
        raise AssertionError("paper/command translation changed")
    if report["layout"]["local_y_correction_applied"] is not False:
        raise AssertionError("unsafe global Y correction was applied")
    warning = full.LAYOUT_TEXT_PATH.read_text(encoding="utf-8")
    if "NOT FOR ROBOT" not in warning or "当前V36不能运行" not in warning:
        raise AssertionError("non-runnable warning missing")
    if list((ROOT / "gcode").glob("DIARY_NOTEBOOK_REPOSITIONED*.gcode")):
        raise AssertionError("runnable-looking repositioned diary G-code exists")
    with Image.open(full.PREVIEW_PATH) as image:
        expected = (
            round(base.A4_WIDTH_MM * full.PIXELS_PER_MM) + 1,
            round(base.A4_HEIGHT_MM * full.PIXELS_PER_MM) + 1,
        )
        if image.size != expected:
            raise AssertionError(f"preview size changed: {image.size}")
    placement_text = "".join(
        placement.character for placement in page.placements
    )
    if placement_text != "".join(
        character for character in text if not character.isspace()
    ):
        raise AssertionError("glyph sequence differs from source")
    print(
        f"artifacts=PASS lines={len(page.lines)} glyphs={len(page.placements)} "
        f"source_docx_sha256={base.digest(base.SOURCE_DOCX)} runnable_files=0"
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    text, font, missing, page = full.generate()
    if missing != "粿麟婷鹏":
        raise AssertionError(f"unexpected missing characters: {missing}")
    v30.configure_model()
    rectangle_margin = check_full_usable_rectangle()
    home = common.check_home_to_align()
    print(
        "home_to_align=PASS combinations=64 "
        f"min_joint_margin_deg={home['minimum_margin']:.6f} "
        f"min_paper_margin_old_contract_mm={home['minimum_paper_margin']:.6f} "
        f"max_line_deviation_mm={home['maximum_deviation']:.6f}"
    )
    points, route = route_command_path(page)
    stats = check_routed_motion(points, route)
    print(
        f"repositioned_text_motion=PASS targets={len(points)} "
        f"segments={int(stats['segments'])} master_pulses={int(stats['master_pulses'])} "
        f"inserted_penup_waypoints={int(stats['inserted_waypoints'])} "
        f"max_raw_penup_span_mm={stats['maximum_raw_penup_span']:.6f} "
        f"max_routed_penup_span_mm={stats['maximum_routed_penup_span']:.6f} "
        f"max_draw_span_mm={stats['maximum_draw_span']:.6f} "
        f"min_joint_margin_deg={stats['minimum_margin']:.6f} "
        f"full_rectangle_min_joint_margin_deg={rectangle_margin:.6f} "
        f"endpoint_paper_margin_mm={stats['minimum_endpoint_paper_margin']:.6f} "
        f"conservative_dda_paper_margin_mm={stats['conservative_dda_paper_margin']:.6f} "
        f"max_line_deviation_mm={stats['maximum_deviation']:.6f} "
        f"max_endpoint_error_mm={stats['maximum_endpoint_error']:.6f} "
        f"max_source_quantization_error_mm={stats['maximum_source_error']:.6f}"
    )
    check_artifacts(text, font, missing, page)
    print(
        "repositioned_a4_check=PASS paper=A4_landscape usable=15mm_inset "
        "pages=1 lines=11 align_machine=(150,20) align_paper=(11,88) "
        "command_shift=(139,-68) exact_text=1 local_y_extrapolation=0 runnable=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
