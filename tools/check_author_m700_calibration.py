"""Verify the gated author-style M700 calibration firmware contract."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOTION_HEADER = ROOT / "APP" / "Inc" / "app_writer_motion.h"
HOME_HEADER = ROOT / "TASK" / "writer_home.h"
HOME_SOURCE = ROOT / "TASK" / "writer_home.c"
TEST_HEADER = ROOT / "TASK" / "writer_test.h"
TEST_SOURCE = ROOT / "TASK" / "writer_test.c"
MAIN_SOURCE = ROOT / "main.c"
COMMAND_SCRIPT = ROOT / "tools" / "m700_calibration_command.ps1"
BUILD_LOG = ROOT / "keil" / "AUTHOR_M700_HOME_CAL_GATED_V15_build.log"
KEIL_HTML_LOG = (
    ROOT
    / "keil"
    / "Objects"
    / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.build_log.htm"
)
HEX_PATH = ROOT / "keil" / "AUTHOR_M700_HOME_CAL_GATED_V15.hex"

BUILD_ID = b"AUTHOR_M700_HOME_CAL_GATED_V15"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}: missing {needle!r}")


def check_source_contract() -> None:
    motion = MOTION_HEADER.read_text(encoding="ascii")
    home_h = HOME_HEADER.read_text(encoding="ascii")
    home_c = HOME_SOURCE.read_text(encoding="ascii")
    test_h = TEST_HEADER.read_text(encoding="ascii")
    test_c = TEST_SOURCE.read_text(encoding="ascii")
    main_c = MAIN_SOURCE.read_text(encoding="ascii")
    command_script = COMMAND_SCRIPT.read_text(encoding="ascii")

    require(
        test_h,
        "#define WRITER_TEST_MODE             WRITER_TEST_MODE_AUTHOR_M700_CALIB",
        "selected mode",
    )
    require(
        motion,
        "#define APP_WRITER_A4_ENVELOPE_PROBE_ENABLE  (0u)",
        "A4 probe lockout",
    )
    require(
        motion,
        "#define APP_WRITER_STAGE1_STEPS_PER_DEG     (43.708318f)",
        "Stage1 scale",
    )
    require(
        motion,
        "#define APP_WRITER_STAGE2_STEPS_PER_DEG     (48.8f)",
        "Stage2 scale",
    )
    require(home_h, BUILD_ID.decode("ascii"), "build id")
    require(home_c, "WRITER_HOME_M700_SEARCH_MAX_DEG          (60.0f)", "travel guard")
    require(home_c, "WRITER_HOME_M700_REPEAT_CYCLES           (2u)", "repeat count")
    require(home_c, 'strcmp(command, "M700") == 0', "M700 command")
    require(home_c, 'strcmp(command, "DRAW") == 0', "DRAW rejection")
    require(home_c, 'command[0] == \'G\'', "G-code rejection")
    require(test_c, "WriterHome_M700_Process_Frame", "UART route")
    require(
        main_c,
        "(WRITER_TEST_MODE == WRITER_TEST_MODE_AUTHOR_M700_CALIB)",
        "automatic-home bypass",
    )
    require(
        command_script,
        '[ValidateSet("STATUS", "CAL", "M700", "STOP")]',
        "command whitelist",
    )
    require(
        command_script,
        "$startsCalibration -and -not $ConfirmKnownPose",
        "known-pose command gate",
    )
    require(
        command_script,
        '$port.Write("$CalibrationCommand`r`n")',
        "single framed UART write",
    )
    print(
        "source_contract=PASS mode=AUTHOR_M700_CALIB auto_motion=0 "
        "gcode=0 draw=0 pen=UP"
    )


def check_build_log() -> None:
    text = BUILD_LOG.read_text(encoding="utf-8", errors="replace")
    html = KEIL_HTML_LOG.read_text(encoding="utf-8", errors="replace")
    require(
        html,
        'gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx',
        "correct Keil project",
    )
    require(text, "0 Error(s), 0 Warning(s).", "clean build")
    if "Target not created" in text:
        raise AssertionError("build log reports that the target was not created")
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
            raise AssertionError(f"line {line_number}: missing Intel HEX prefix")
        record = bytes.fromhex(line[1:])
        if sum(record) & 0xFF:
            raise AssertionError(f"line {line_number}: checksum mismatch")
        length = record[0]
        address = int.from_bytes(record[1:3], "big")
        record_type = record[3]
        data = record[4 : 4 + length]
        if len(data) != length:
            raise AssertionError(f"line {line_number}: truncated record")
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
            f"invalid Intel HEX memory/eof memory={len(memory)} eof={eof_records}"
        )
    low = min(memory)
    high = max(memory)
    image = bytes(memory.get(address, 0xFF) for address in range(low, high + 1))
    return image, records, len(memory)


def check_hex() -> None:
    image, records, data_bytes = parse_ihex(HEX_PATH)
    if BUILD_ID not in image:
        raise AssertionError("firmware does not contain the V15 build id")
    digest = hashlib.sha256(HEX_PATH.read_bytes()).hexdigest().upper()
    print(
        f"intel_hex=PASS records={records} data_bytes={data_bytes} "
        f"build_id=PASS sha256={digest}"
    )


def main() -> None:
    check_source_contract()
    check_build_log()
    check_hex()


if __name__ == "__main__":
    main()
