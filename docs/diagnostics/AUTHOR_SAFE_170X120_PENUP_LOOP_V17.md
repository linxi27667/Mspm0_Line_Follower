# Author Safe 170x120 Pen-Up Loop V17

Firmware:

`keil/AUTHOR_SAFE_170X120_PENUP_LOOP_V17.hex`

SHA-256:

`4959438F8F10DEB24A2C968B30A0849314E900594E99942A83A82A565869181D`

Build result: 0 errors, 0 warnings. The selected official author work frame,
V15 measured limits, joint scales, and pen angles are unchanged from V16.

## Behavior

- Startup raises the pen and performs the normal two-speed limit home.
- After homing, it waits in `WAIT_LOOP`; the outer loop does not auto-start.
- One exact `LOOP` command starts the continuous pen-up loop.
- The approach moves directly to `RECT_BL=(120,5)` using the checked joint
  path.
- The repeating order is `BL -> BR -> TR -> TL -> BL` without a loop limit.
- One exact `STOP`, a safety error, a limit input, or power removal stops it.
- After `STOP`, another home/reset is required before restarting.
- `DRAW`, `NEXT`, G-code, and all other commands are rejected.
- The pen remains at 90 degrees.

## Geometry

```text
author_offset=(-129,+128) mm
X=120..290 mm
Y=5..125 mm
rectangle=170x120 mm
```

V17 intentionally disables the author single-endpoint shortcut for this
diagnostic. Each long edge is expanded into 1 mm Cartesian IK targets so the
continuous pen-tip path follows the requested rectangle instead of a long
joint-interpolation curve. Author endpoint execution must be restored when
the firmware returns to serial G-code mode.

Offline verification covers:

```text
edge_segments=170,120,170,120
targets_per_loop=580
master_pulses_per_loop=7546
minimum_joint_margin=3.364751 deg
maximum_quantized_line_deviation=0.085499 mm
repeat_seam=RECT_BL -> RECT_BR
loop_limit=none
```

## Commands

Mechanical Arm Master must remain closed so COM7 is available.

```powershell
.\tools\author_rect_loop_command.ps1 STATUS
.\tools\author_rect_loop_command.ps1 LOOP -ConfirmContinuousPenUpLoop
.\tools\author_rect_loop_command.ps1 STOP
```

Before sending `LOOP`, the script issues a read-only `STATUS`. It refuses to
start unless the firmware ID is V17, the state is `WAIT_LOOP`, both limits
are clear, and the pen reports UP. It sends `LOOP` exactly once; looping is
performed by the MCU, not by repeated host commands.

Offline verification:

```powershell
python .\tools\check_author_rect_loop_v17.py
```
