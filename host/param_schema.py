"""Shared parameter schema — single source of truth for tunable parameters.

This module drives:
  * firmware range clamping (via generated constants in user_tuning.h)
  * Python protocol (host/protocol.py PARAMS is derived from here)
  * browser UI controls (min/max/step rendered by templates/index.html)

The default values MUST match the values in APP/Inc/user_tuning.h.
A unit test (tests/test_param_schema.py) verifies this consistency.

Only the 8 remotely-tunable parameters live here. Firmware-local parameters
(motor speed PID, gyro PID, limits, calibration thresholds) remain solely in
user_tuning.h and are never exposed to the host protocol.
"""

from __future__ import annotations

from typing import Any


# Each entry maps a protocol parameter name to its firmware macro and bounds.
# Order matters: optimizer searches KP/KD/GDAMP/RATHR first, then VBASE/VSTR/VCUR.
PARAM_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "KP",
        "macro": "USER_LINE_PID_KP",
        "min": 0.0, "max": 50.0, "default": 3.5, "step": 0.1,
        "desc": "循迹比例增益", "kind": "float",
    },
    {
        "name": "KI",
        "macro": "USER_LINE_PID_KI",
        "min": 0.0, "max": 5.0, "default": 0.0, "step": 0.05,
        "desc": "循迹积分增益", "kind": "float",
    },
    {
        "name": "KD",
        "macro": "USER_LINE_PID_KD",
        "min": 0.0, "max": 20.0, "default": 1.5, "step": 0.1,
        "desc": "循迹微分增益", "kind": "float",
    },
    {
        "name": "GDAMP",
        "macro": "USER_LINE_FOLLOW_GYRO_DAMP",
        "min": 0.0, "max": 1.0, "default": 0.25, "step": 0.01,
        "desc": "陀螺仪阻尼系数", "kind": "float",
    },
    {
        "name": "VBASE",
        "macro": "USER_TRACK_BASE_SPEED",
        "min": 0, "max": 100, "default": 28, "step": 1,
        "desc": "基础PWM百分比", "kind": "int",
    },
    {
        "name": "VSTR",
        "macro": "USER_TRACK_SPEED_STRAIGHT",
        "min": 0, "max": 100, "default": 30, "step": 1,
        "desc": "直道PWM百分比", "kind": "int",
    },
    {
        "name": "VCUR",
        "macro": "USER_TRACK_SPEED_CURVE",
        "min": 0, "max": 100, "default": 26, "step": 1,
        "desc": "弯道PWM百分比", "kind": "int",
    },
    {
        "name": "RATHR",
        "macro": "USER_RIGHT_ANGLE_THRESHOLD",
        "min": 0.5, "max": 10.0, "default": 4.0, "step": 0.1,
        "desc": "方形拐角最少黑通道", "kind": "float",
    },
]

# Dict view for consumers that need O(1) lookup by name.
PARAMS: dict[str, dict[str, Any]] = {p["name"]: p for p in PARAM_SCHEMA}

# Telemetry field abbreviation -> protocol parameter name.
TELEMETRY_PARAM_FIELDS: dict[str, str] = {
    "kp": "KP",
    "ki": "KI",
    "kd": "KD",
    "gd": "GDAMP",
    "vb": "VBASE",
    "vs": "VSTR",
    "vc": "VCUR",
    "rt": "RATHR",
}

# Parameter groups for the local optimizer (search order).
OPTIMIZER_GROUP_GAINS = ["KP", "KD", "GDAMP", "RATHR"]
OPTIMIZER_GROUP_SPEED = ["VBASE", "VSTR", "VCUR"]
# Parameters the optimizer must never touch automatically.
OPTIMIZER_LOCKED = ["KI"]


def parse_user_tuning_defaults(header_text: str) -> dict[str, float]:
    """Parse #define values from user_tuning.h text.

    Returns a {macro: value} dict for all USER_* macros found.
    """
    import re
    defaults: dict[str, float] = {}
    pattern = re.compile(
        r'^\s*#define\s+(USER_[A-Z0-9_]+)\s+([0-9]+\.?[0-9]*)f?\s*(?:/\*.*)?$',
        re.MULTILINE,
    )
    for match in pattern.finditer(header_text):
        macro = match.group(1)
        value = float(match.group(2))
        defaults[macro] = value
    return defaults
