"""Verify the measured-limit, author-frame V16 pen-up probe."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
MOTION_HEADER = ROOT / "APP" / "Inc" / "app_writer_motion.h"
TEST_HEADER = ROOT / "TASK" / "writer_test.h"
PROBE_HEADER = ROOT / "TASK" / "a4_joint_probe.h"
PROBE_SOURCE = ROOT / "TASK" / "a4_joint_probe.c"
PATH_HEADER = ROOT / "TASK" / "author_coordinate_probe_path.h"
MAIN_SOURCE = ROOT / "main.c"
COMMAND_SCRIPT = ROOT / "tools" / "author_safe_probe_command.ps1"
BUILD_LOG = ROOT / "keil" / "AUTHOR_SAFE_170X120_PENUP_GATED_V16_build.log"
KEIL_HTML_LOG = (
    ROOT
    / "keil"
    / "Objects"
    / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.build_log.htm"
)
HEX_PATH = ROOT / "keil" / "AUTHOR_SAFE_170X120_PENUP_GATED_V16.hex"

BUILD_ID = b"AUTHOR_SAFE_170X120_PENUP_GATED_V16"
L1_MM = np.float32(200.0)
L2_MM = np.float32(200.0)
OFFSET_X_MM = np.float32(-129.0)
OFFSET_Y_MM = np.float32(128.0)
THETA_LIMIT_DEG = np.float32(-0.709247)
PSI_LIMIT_DEG = np.float32(134.323770)
STAGE1_STEPS_PER_DEG = np.float32(43.708318)
STAGE2_STEPS_PER_DEG = np.float32(48.8)
THETA_MIN_DEG = np.float32(THETA_LIMIT_DEG + np.float32(1.0))
PSI_MIN_DEG = np.float32(PSI_LIMIT_DEG + np.float32(1.0))
THETA_MAX_DEG = np.float32(135.0)
PSI_MAX_DEG = np.float32(255.0)
BETA_MIN_DEG = np.float32(1.0)
BETA_MAX_DEG = np.float32(179.0)
OPERATING_MARGIN_DEG = 2.0

POINTS = (
    ("REF_150_20", 150.0, 20.0),
    ("X_PLUS_20", 170.0, 20.0),
    ("REF_AFTER_X", 150.0, 20.0),
    ("Y_PLUS_20", 150.0, 40.0),
    ("REF_AFTER_Y", 150.0, 20.0),
    ("RECT_BL", 120.0, 5.0),
    ("RECT_BR", 290.0, 5.0),
    ("RECT_TR", 290.0, 125.0),
    ("RECT_TL", 120.0, 125.0),
    ("RECT_CLOSE", 120.0, 5.0),
    ("REF_CLOSE", 150.0, 20.0),
)


@dataclass(frozen=True)
class Target:
    name: str
    work_x_x10: int
    work_y_x10: int
    raw_x_x10: int
    raw_y_x10: int
    stage1_steps: int
    stage2_steps: int


def lroundf(value: np.float32) -> int:
    number = float(value)
    if number >= 0.0:
        return math.floor(number + 0.5)
    return math.ceil(number - 0.5)


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}: missing {needle!r}")


def inverse(work_x_mm: float, work_y_mm: float) -> tuple[np.float32, np.float32]:
    raw_x = np.float32(np.float32(work_x_mm) + OFFSET_X_MM)
    raw_y = np.float32(np.float32(work_y_mm) + OFFSET_Y_MM)
    standard_x = np.float32(-raw_x)
    standard_y = raw_y
    radius_sq = np.float32(standard_x * standard_x + standard_y * standard_y)
    l1_sq = np.float32(L1_MM * L1_MM)
    l2_sq = np.float32(L2_MM * L2_MM)
    c2 = np.float32(
        (radius_sq - l1_sq - l2_sq) /
        np.float32(2.0 * L1_MM * L2_MM)
    )
    if c2 < np.float32(-1.0) or c2 > np.float32(1.0):
        raise AssertionError(f"unreachable point ({work_x_mm},{work_y_mm})")
    s2 = np.sqrt(np.float32(1.0) - np.float32(c2 * c2), dtype=np.float32)
    k1 = np.float32(l1_sq + l2_sq * c2)
    k2 = np.float32(l2_sq * s2)
    theta = np.float32(
        np.arctan2(k1, k2) - np.arctan2(standard_x, standard_y)
    )
    psi = np.float32(theta + np.arctan2(s2, c2))
    to_deg = np.float32(180.0 / math.pi)
    return np.float32(theta * to_deg), np.float32(psi * to_deg)


def pose_margin(stage1_steps: int, stage2_steps: int) -> float:
    theta = stage1_steps / float(STAGE1_STEPS_PER_DEG)
    psi = stage2_steps / float(STAGE2_STEPS_PER_DEG)
    beta = psi - theta
    return min(
        theta - float(THETA_MIN_DEG),
        float(THETA_MAX_DEG) - theta,
        psi - float(PSI_MIN_DEG),
        float(PSI_MAX_DEG) - psi,
        beta - float(BETA_MIN_DEG),
        float(BETA_MAX_DEG) - beta,
    )


def require_hard_safe(stage1_steps: int, stage2_steps: int, label: str) -> float:
    margin = pose_margin(stage1_steps, stage2_steps)
    theta = stage1_steps / float(STAGE1_STEPS_PER_DEG)
    psi = stage2_steps / float(STAGE2_STEPS_PER_DEG)
    if margin < -1.0e-6 or psi <= theta:
        raise AssertionError(
            f"{label}: unsafe s1={stage1_steps} s2={stage2_steps} "
            f"theta={theta:.6f} psi={psi:.6f} margin={margin:.6f}"
        )
    return margin


def target_for(name: str, work_x_mm: float, work_y_mm: float) -> Target:
    theta, psi = inverse(work_x_mm, work_y_mm)
    stage1 = lroundf(np.float32(theta * STAGE1_STEPS_PER_DEG))
    stage2 = lroundf(np.float32(psi * STAGE2_STEPS_PER_DEG))
    margin = require_hard_safe(stage1, stage2, name)
    if margin < OPERATING_MARGIN_DEG:
        raise AssertionError(
            f"{name}: target margin {margin:.6f} below {OPERATING_MARGIN_DEG}"
        )

    quantized_theta = stage1 / float(STAGE1_STEPS_PER_DEG)
    quantized_psi = stage2 / float(STAGE2_STEPS_PER_DEG)
    theta_rad = np.float32(quantized_theta * math.pi / 180.0)
    psi_rad = np.float32(quantized_psi * math.pi / 180.0)
    fk_x = np.float32(
        -np.cos(theta_rad, dtype=np.float32) * L1_MM
        - np.cos(psi_rad, dtype=np.float32) * L2_MM
    )
    fk_y = np.float32(
        np.sin(theta_rad, dtype=np.float32) * L1_MM
        + np.sin(psi_rad, dtype=np.float32) * L2_MM
    )
    expected_raw_x = np.float32(np.float32(work_x_mm) + OFFSET_X_MM)
    expected_raw_y = np.float32(np.float32(work_y_mm) + OFFSET_Y_MM)
    fk_error = math.hypot(
        float(fk_x - expected_raw_x), float(fk_y - expected_raw_y)
    )
    if fk_error > 0.09:
        raise AssertionError(f"{name}: quantized FK error {fk_error:.6f} mm")

    return Target(
        name=name,
        work_x_x10=lroundf(np.float32(work_x_mm * 10.0)),
        work_y_x10=lroundf(np.float32(work_y_mm * 10.0)),
        raw_x_x10=lroundf(np.float32(float(expected_raw_x) * 10.0)),
        raw_y_x10=lroundf(np.float32(float(expected_raw_y) * 10.0)),
        stage1_steps=stage1,
        stage2_steps=stage2,
    )


def parse_header_targets(text: str) -> list[Target]:
    pattern = re.compile(
        r'\{"([A-Z0-9_]+)",\s*(-?\d+),\s*(-?\d+),\s*'
        r'(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\},'
    )
    return [
        Target(match.group(1), *(int(match.group(i)) for i in range(2, 8)))
        for match in pattern.finditer(text)
    ]


def check_dda(
    start: tuple[int, int],
    end: tuple[int, int],
    label: str,
    required_margin: float,
) -> tuple[int, float]:
    delta1 = end[0] - start[0]
    delta2 = end[1] - start[1]
    steps1 = abs(delta1)
    steps2 = abs(delta2)
    master = max(steps1, steps2)
    if master == 0:
        return 0, require_hard_safe(start[0], start[1], label)

    direction1 = 1 if delta1 > 0 else -1
    direction2 = 1 if delta2 > 0 else -1
    current1, current2 = start
    error1 = master // 2
    error2 = master // 2
    minimum_margin = require_hard_safe(current1, current2, f"{label}/start")
    for tick in range(master):
        error1 += steps1
        if error1 >= master:
            error1 -= master
            current1 += direction1
        error2 += steps2
        if error2 >= master:
            error2 -= master
            current2 += direction2
        margin = require_hard_safe(
            current1, current2, f"{label}/tick{tick + 1}"
        )
        minimum_margin = min(minimum_margin, margin)
    if (current1, current2) != end:
        raise AssertionError(f"{label}: DDA endpoint mismatch")
    if minimum_margin < required_margin - 1.0e-6:
        raise AssertionError(
            f"{label}: path margin {minimum_margin:.6f} below {required_margin}"
        )
    return master, minimum_margin


def check_source_and_path() -> None:
    motion = MOTION_HEADER.read_text(encoding="ascii")
    test_h = TEST_HEADER.read_text(encoding="ascii")
    probe_h = PROBE_HEADER.read_text(encoding="ascii")
    probe_c = PROBE_SOURCE.read_text(encoding="ascii")
    path_h = PATH_HEADER.read_text(encoding="ascii")
    main_c = MAIN_SOURCE.read_text(encoding="ascii")
    command = COMMAND_SCRIPT.read_text(encoding="ascii")

    require(
        test_h,
        "#define WRITER_TEST_MODE             WRITER_TEST_MODE_A4_JOINT_PROBE",
        "selected mode",
    )
    for needle in (
        "#define APP_WRITER_MACHINE_OFFSET_X_MM      (-129.0f)",
        "#define APP_WRITER_MACHINE_OFFSET_Y_MM      (128.0f)",
        "#define APP_WRITER_THETA_LIMIT_DEG          (-0.709247f)",
        "#define APP_WRITER_PSI_LIMIT_DEG            (134.323770f)",
        "#define APP_WRITER_STAGE1_STEPS_PER_DEG     (43.708318f)",
        "#define APP_WRITER_STAGE2_STEPS_PER_DEG     (48.8f)",
        "#define APP_WRITER_A4_ENVELOPE_PROBE_ENABLE  (1u)",
    ):
        require(motion, needle, "motion contract")
    require(probe_h, BUILD_ID.decode("ascii"), "build id")
    require(probe_h, "A4_JOINT_PROBE_OPERATING_MARGIN_DEG (2.0f)", "margin")
    require(probe_c, "no_auto_probe_motion=1", "UART gate")
    require(probe_c, "full_A4=DISABLED", "full A4 lockout")
    require(probe_c, 'strcmp(command, "DRAW") == 0', "DRAW rejection")
    require(
        main_c,
        "(WRITER_TEST_MODE == WRITER_TEST_MODE_AUTHOR_M700_CALIB)",
        "V16 automatic home enabled",
    )
    require(
        command,
        '[ValidateSet("STATUS", "NEXT", "STOP")]',
        "command whitelist",
    )
    require(
        command,
        '$ProbeCommand -eq "NEXT") -and -not $ConfirmPenUpClearance',
        "NEXT confirmation gate",
    )
    require(
        command,
        'id=AUTHOR_SAFE_170X120_PENUP_GATED_V16',
        "firmware ID preflight",
    )
    require(command, '$preflight -notmatch "state=WAIT_NEXT"', "state preflight")

    targets = [target_for(*point) for point in POINTS]
    header_targets = parse_header_targets(path_h)
    if header_targets != targets:
        raise AssertionError(
            f"path header mismatch\nexpected={targets}\nactual={header_targets}"
        )

    minimum_release_home = (
        lroundf(np.float32(THETA_LIMIT_DEG * STAGE1_STEPS_PER_DEG))
        + 1
        + lroundf(STAGE1_STEPS_PER_DEG),
        lroundf(np.float32(PSI_LIMIT_DEG * STAGE2_STEPS_PER_DEG))
        + 1
        + lroundf(STAGE2_STEPS_PER_DEG),
    )
    observed_home = (
        lroundf(np.float32(THETA_LIMIT_DEG * STAGE1_STEPS_PER_DEG)) + 52,
        lroundf(np.float32(PSI_LIMIT_DEG * STAGE2_STEPS_PER_DEG)) + 57,
    )
    first = (targets[0].stage1_steps, targets[0].stage2_steps)
    minimum_pulses, minimum_margin = check_dda(
        minimum_release_home, first, "minimum_home_to_first", 0.0
    )
    observed_pulses, observed_margin = check_dda(
        observed_home, first, "observed_home_to_first", 0.0
    )

    total_pulses = observed_pulses
    path_minimum = float("inf")
    prior = first
    for index, target in enumerate(targets[1:], start=2):
        current = (target.stage1_steps, target.stage2_steps)
        pulses, margin = check_dda(
            prior, current, f"target_{index}", OPERATING_MARGIN_DEG
        )
        total_pulses += pulses
        path_minimum = min(path_minimum, margin)
        prior = current

    target_margins = [
        pose_margin(target.stage1_steps, target.stage2_steps)
        for target in targets
    ]
    print(
        "source_contract=PASS mode=AUTHOR_SAFE_170X120_PENUP_GATED_V16 "
        "author_offset=-129,128 full_A4=0 gcode=0 draw=0 pen=UP"
    )
    print(
        f"path_header=PASS targets={len(targets)} "
        f"target_min_margin_deg={min(target_margins):.6f} "
        f"intertarget_min_margin_deg={path_minimum:.6f}"
    )
    print(
        f"home_paths=PASS minimum_release_pulses={minimum_pulses} "
        f"minimum_margin_deg={minimum_margin:.6f} "
        f"observed_release_pulses={observed_pulses} "
        f"observed_margin_deg={observed_margin:.6f} "
        f"total_master_pulses={total_pulses}"
    )


def check_build_log() -> None:
    text = BUILD_LOG.read_text(encoding="utf-8", errors="replace")
    html = KEIL_HTML_LOG.read_text(encoding="utf-8", errors="replace")
    require(
        html,
        "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx",
        "correct Keil project",
    )
    require(text, "0 Error(s), 0 Warning(s).", "clean build")
    if "Target not created" in text:
        raise AssertionError("build log reports target not created")
    print("keil_build=PASS errors=0 warnings=0")


def parse_ihex(path: Path) -> tuple[bytes, int, int]:
    memory: dict[int, int] = {}
    base = 0
    records = 0
    eof_records = 0
    for line_number, raw_line in enumerate(
        path.read_text(encoding="ascii").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            raise AssertionError(f"line {line_number}: missing HEX prefix")
        record = bytes.fromhex(line[1:])
        if sum(record) & 0xFF:
            raise AssertionError(f"line {line_number}: checksum mismatch")
        length = record[0]
        address = int.from_bytes(record[1:3], "big")
        record_type = record[3]
        data = record[4 : 4 + length]
        records += 1
        if record_type == 0x00:
            for index, value in enumerate(data):
                memory[base + address + index] = value
        elif record_type == 0x01:
            eof_records += 1
        elif record_type == 0x02:
            base = int.from_bytes(data, "big") << 4
        elif record_type == 0x04:
            base = int.from_bytes(data, "big") << 16
    if not memory or eof_records != 1:
        raise AssertionError(
            f"invalid HEX memory={len(memory)} eof={eof_records}"
        )
    low = min(memory)
    high = max(memory)
    image = bytes(memory.get(address, 0xFF) for address in range(low, high + 1))
    return image, records, len(memory)


def check_hex() -> None:
    image, records, data_bytes = parse_ihex(HEX_PATH)
    if BUILD_ID not in image:
        raise AssertionError("V16 build id missing from firmware")
    digest = hashlib.sha256(HEX_PATH.read_bytes()).hexdigest().upper()
    print(
        f"intel_hex=PASS records={records} data_bytes={data_bytes} "
        f"build_id=PASS sha256={digest}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    check_source_and_path()
    if not args.source_only:
        check_build_log()
        check_hex()


if __name__ == "__main__":
    main()
