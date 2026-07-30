# Author M700 Home Calibration Gated V15

Firmware:

`keil/AUTHOR_M700_HOME_CAL_GATED_V15.hex`

SHA-256:

`D52595B9120DEAD363ABD06B703ECBF3F2FDB7A97A3B36BAC689D9032968D63B`

Build result: 0 errors, 0 warnings. The known PA8 SysConfig package-model
message occurs before the successful compile and link.

## Purpose

This firmware reproduces the author's M700 calibration concept without any
G-code or drawing behavior. The manually established reference pose is:

- author theta = 0 degrees;
- author psi = 135 degrees;
- the large arm is parallel to the motor-base side;
- the included arm angle is 45 degrees;
- both limit inputs are clear.

The first search measures the absolute limit angles from that known pose. Two
additional limit approaches measure switch repeatability. All motion is pen-up.

## Safety Contract

- Startup performs no motor motion.
- Only exact `CAL` or `M700` starts calibration.
- `STATUS` is read-only.
- `STOP` stops both motors and requires repositioning at 0/135 before reboot.
- `DRAW`, `NEXT`, every G-code command, and every other M-code are rejected.
- Search speed is 100 pulses/second.
- Each joint search is limited to 60 degrees and 35 seconds.
- Each axis stops independently when its own limit becomes active.
- Every approach requires both limits to remain stable.
- The pen remains at 90 degrees throughout the test.

For imminent contact, unexpected direction, cable tension, or collision, cut
motor power. UART `STOP` is an additional control, not a substitute for the
physical power switch.

## Required Setup

1. Cut motor power before positioning the arms by hand.
2. Place the mechanism in the author's illustrated 0/135 calibration pose.
3. Confirm the large arm is parallel to the motor-base side.
4. Confirm the large/small arm included angle is 45 degrees.
5. Confirm neither switch is pressed.
6. Flash V15 and power the controller.
7. Do not use Mechanical Arm Master or send G-code.
8. Require the following RTT values before sending any motion command:

```text
mode=AUTHOR_M700_HOME_CAL_GATED_V15
no_auto_motion=1 no_gcode=1 no_draw=1 pen=UP
known_pose theta=0 psi=13500 beta=13500
spd1=4371 spd2=4880
lim1=0 lim2=0
```

Send `STATUS` first. Send exactly one `CAL` only after the physical pose and
RTT values are confirmed.

Use only the dedicated command script for this calibration:

```powershell
.\tools\m700_calibration_command.ps1 STATUS
.\tools\m700_calibration_command.ps1 CAL -ConfirmKnownPose
.\tools\m700_calibration_command.ps1 STOP
```

The script accepts only `STATUS`, `CAL`, `M700`, or `STOP`. It refuses to send
`CAL` or `M700` without the explicit known-pose confirmation and never retries
a command automatically.

## Result

A successful stable calibration ends with:

```text
[M700CAL] result ... repeat_ok=1 author_a4_candidate=0|1 ... pen=UP
[M700CAL] AUTHOR_M700_HOME_CAL_GATED_V15 done calibration_valid=1 ... pen=UP
```

`author_a4_candidate=1` requires one degree of clearance beyond the official
A4 limiting corners with the current measured joint scales:

- theta limit <= -19.22 degrees;
- psi limit <= 93.36 degrees.

This flag is only an initial envelope decision. A full 1 mm grid, every
quantized joint target, every synchronized DDA pulse, and the approach path
must still pass offline validation before an A4 probe firmware is built.

Offline verification:

```powershell
python .\tools\check_author_m700_calibration.py
```

The completed 2026-07-19 hardware result and reachable author-frame analysis
are recorded in `AUTHOR_M700_HOME_CAL_V15_RESULT_20260719.md`.
