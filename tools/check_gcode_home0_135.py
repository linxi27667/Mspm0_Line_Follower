"""Mirror the MCU G-code protocol and motion checks for the V7 configuration."""

from __future__ import annotations

import contextlib
import io
import math
import re
import sys
from pathlib import Path

import numpy as np

import check_workspace_square_dircomp as model


DEFAULT_GCODE = Path(
    r"C:\Users\zjl\Desktop\zjl\TI\writer_robot_source\G_Code.txt.gcode"
)
SOURCE_ORIGIN_X = 31.800001
SOURCE_ORIGIN_Y = -25.984985
POSITION_EPSILON_MM = 0.08
WORKSPACE = (0.0, 16.611, -5.700, -0.019)

model.OFFSET_X_MM = np.float32(-35.901242)
model.OFFSET_Y_MM = np.float32(182.889598)
model.THETA_LIMIT_DEG = np.float32(0.0)
model.PSI_LIMIT_DEG = np.float32(135.0)
model.THETA_MIN_DEG = np.float32(1.0)
model.PSI_MIN_DEG = np.float32(136.0)
model.THETA_REV_PSI_STEPS = 0
model.PSI_REV_PSI_STEPS = 0

WORD_RE = re.compile(
    r"([A-Za-z])([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
)


def parse_words(text: str, line_number: int) -> dict[str, float]:
    words: dict[str, float] = {}
    cursor = 0
    while cursor < len(text):
        if text[cursor].isspace():
            cursor += 1
            continue
        match = WORD_RE.match(text, cursor)
        if match is None:
            raise AssertionError(
                f"line {line_number}: parse error at {text[cursor:]!r}"
            )
        letter = match.group(1).upper()
        if letter not in "GMXYZFSP":
            raise AssertionError(f"line {line_number}: unsupported word {letter}")
        if letter in words:
            raise AssertionError(f"line {line_number}: duplicate word {letter}")
        words[letter] = float(match.group(2))
        cursor = match.end()
    return words


def integer_code(value: float, line_number: int, letter: str) -> int:
    rounded = round(value)
    if abs(value - rounded) > 0.001:
        raise AssertionError(f"line {line_number}: non-integer {letter}{value}")
    return int(rounded)


def initial_state() -> model.State:
    stage1_clearance = model.lroundf(model.STAGE1_STEPS_PER_DEG)
    stage2_clearance = model.lroundf(model.STAGE2_STEPS_PER_DEG)
    theta = np.float32(
        model.THETA_LIMIT_DEG
        + np.float32(1 + stage1_clearance) / model.STAGE1_STEPS_PER_DEG
    )
    psi = np.float32(
        model.PSI_LIMIT_DEG
        + np.float32(1 + stage2_clearance) / model.STAGE2_STEPS_PER_DEG
    )
    return model.State(
        model.lroundf(np.float32(theta * model.STAGE1_STEPS_PER_DEG)),
        model.lroundf(np.float32(psi * model.STAGE2_STEPS_PER_DEG)),
        model.lroundf(np.float32(psi * model.STAGE2_STEPS_PER_DEG)),
        0,
        1,
        1,
    )


def checked_move(
    state: model.State,
    target: tuple[float, float],
    label: str,
) -> tuple[model.State, list[tuple[float, float]]]:
    with contextlib.redirect_stdout(io.StringIO()):
        next_state = model.target_state(state, target, label)
        points = model.dda_user_points(state, next_state, label)
    if next_state.bias_steps != 0:
        raise AssertionError(f"{label}: unexpected direction compensation")
    return next_state, points


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_GCODE
    lines = path.read_text(encoding="ascii").splitlines()

    state = initial_state()
    absolute = True
    pen_down = False
    modal_motion = 0
    source_x = 0.0
    source_y = 0.0
    work_origin_x = SOURCE_ORIGIN_X
    work_origin_y = SOURCE_ORIGIN_Y
    feed = 0.0
    power = 0.0
    motion_count = 0
    rapid_count = 0
    draw_count = 0
    stroke_count = 0
    ignored_source_zero_returns = 0
    all_motion_points: list[tuple[float, float]] = []
    pen_points: list[tuple[float, float]] = []
    logical_targets: list[tuple[float, float]] = []
    joint_targets: list[tuple[float, float]] = []

    for line_number, raw_line in enumerate(lines, 1):
        text = raw_line.strip()
        if not text:
            continue
        if len(text) >= 192:
            raise AssertionError(f"line {line_number}: exceeds MCU line buffer")
        words = parse_words(text, line_number)
        has_g = "G" in words
        has_m = "M" in words
        if has_g and has_m:
            raise AssertionError(f"line {line_number}: mixed G/M")

        if "F" in words:
            if words["F"] < 0.0:
                raise AssertionError(f"line {line_number}: negative feed")
            feed = words["F"]
        if "S" in words:
            if words["S"] < 0.0:
                raise AssertionError(f"line {line_number}: negative power")
            power = words["S"]

        if has_m:
            if any(letter in words for letter in "XYZP"):
                raise AssertionError(f"line {line_number}: axis on M code")
            code = integer_code(words["M"], line_number, "M")
            if code == 3:
                if not pen_down:
                    stroke_count += 1
                pen_down = True
            elif code == 5:
                pen_down = False
            elif code != 501:
                raise AssertionError(f"line {line_number}: unsupported M{code}")
            continue

        motion_code = modal_motion
        if has_g:
            code = integer_code(words["G"], line_number, "G")
            if code in (0, 1):
                motion_code = code
                modal_motion = code
            elif code == 4:
                if any(letter in words for letter in "XYZF"):
                    raise AssertionError(f"line {line_number}: bad dwell")
                dwell = words.get("P", 0.0)
                if dwell < 0.0 or dwell * 1000.0 > 60000.0:
                    raise AssertionError(f"line {line_number}: bad dwell value")
                continue
            elif code == 21:
                if any(letter in words for letter in "XYZP"):
                    raise AssertionError(f"line {line_number}: bad G21")
                absolute = True
                modal_motion = 0
                source_x = 0.0
                source_y = 0.0
                work_origin_x = SOURCE_ORIGIN_X
                work_origin_y = SOURCE_ORIGIN_Y
                continue
            elif code in (90, 91):
                if any(letter in words for letter in "XYZP"):
                    raise AssertionError(f"line {line_number}: axis on distance mode")
                absolute = code == 90
                continue
            elif code == 94:
                if any(letter in words for letter in "XYZP"):
                    raise AssertionError(f"line {line_number}: bad G94")
                continue
            else:
                raise AssertionError(f"line {line_number}: unsupported G{code}")

        if "X" in words or "Y" in words:
            if motion_code == 0 and pen_down:
                raise AssertionError(f"line {line_number}: G0 with pen down")
            if motion_code == 1 and not pen_down:
                raise AssertionError(f"line {line_number}: G1 with pen up")

            pending_x = source_x
            pending_y = source_y
            if absolute:
                pending_x = words.get("X", pending_x)
                pending_y = words.get("Y", pending_y)
                source_zero_return = (
                    motion_code == 0
                    and "X" in words
                    and "Y" in words
                    and abs(words["X"]) <= 0.0001
                    and abs(words["Y"]) <= 0.0001
                )
                if source_zero_return:
                    target = (0.0, 0.0)
                    ignored_source_zero_returns += 1
                else:
                    target = (
                        pending_x - work_origin_x,
                        pending_y - work_origin_y,
                    )
            else:
                pending_x += words.get("X", 0.0)
                pending_y += words.get("Y", 0.0)
                current = model.user_from_steps(
                    state.stage1_steps, state.stage2_motor_steps
                )
                target = (
                    current[0] + words.get("X", 0.0),
                    current[1] + words.get("Y", 0.0),
                )

            current = model.user_from_steps(
                state.stage1_steps, state.stage2_motor_steps
            )
            span = max(abs(target[0] - current[0]), abs(target[1] - current[1]))
            if span > POSITION_EPSILON_MM:
                state, points = checked_move(
                    state, target, f"line {line_number} G{motion_code}"
                )
                motion_count += 1
                all_motion_points.extend(points)
                if motion_code == 1:
                    draw_count += 1
                    pen_points.extend(points)
                else:
                    rapid_count += 1
                theta = state.stage1_steps / float(model.STAGE1_STEPS_PER_DEG)
                psi = state.stage2_motor_steps / float(model.STAGE2_STEPS_PER_DEG)
                joint_targets.append((theta, psi))
            logical_targets.append(target)
            source_x = pending_x
            source_y = pending_y
            continue

        if has_g or "Z" in words or "F" in words or "S" in words:
            continue
        raise AssertionError(f"line {line_number}: empty command")

    if pen_down:
        raise AssertionError("program ends with pen down")
    if not pen_points:
        raise AssertionError("program has no pen-down motion")

    target_x = [point[0] for point in logical_targets[:-ignored_source_zero_returns or None]]
    target_y = [point[1] for point in logical_targets[:-ignored_source_zero_returns or None]]
    pen_x = [point[0] for point in pen_points]
    pen_y = [point[1] for point in pen_points]
    theta_values = [point[0] for point in joint_targets]
    psi_values = [point[1] for point in joint_targets]
    beta_values = [psi - theta for theta, psi in joint_targets]
    x_min, x_max, y_min, y_max = WORKSPACE
    logical_bounds = min(target_x), max(target_x), min(target_y), max(target_y)
    if not (
        x_min - 0.001 <= logical_bounds[0] <= logical_bounds[1] <= x_max + 0.001
        and y_min - 0.001 <= logical_bounds[2] <= logical_bounds[3] <= y_max + 0.001
    ):
        raise AssertionError(f"logical drawing bounds outside workspace: {logical_bounds}")

    print(f"PASS: {path}")
    print(
        f"lines={len(lines)} strokes={stroke_count} motions={motion_count} "
        f"G0={rapid_count} G1={draw_count} source_zero_returns={ignored_source_zero_returns}"
    )
    print(
        f"logical target bounds: X={logical_bounds[0]:.3f}..{logical_bounds[1]:.3f} "
        f"Y={logical_bounds[2]:.3f}..{logical_bounds[3]:.3f} mm"
    )
    print(
        f"pen-down quantized DDA: X={min(pen_x):.3f}..{max(pen_x):.3f} "
        f"Y={min(pen_y):.3f}..{max(pen_y):.3f} mm"
    )
    print(
        f"joint targets: theta={min(theta_values):.3f}..{max(theta_values):.3f} "
        f"psi={min(psi_values):.3f}..{max(psi_values):.3f} "
        f"beta={min(beta_values):.3f}..{max(beta_values):.3f} deg"
    )
    print(f"final pen=UP feed={feed:.1f} power={power:.1f}")


if __name__ == "__main__":
    main()
