# Author Safe 170x120 Pen-Up Gated V16

Firmware:

`keil/AUTHOR_SAFE_170X120_PENUP_GATED_V16.hex`

SHA-256:

`D5446847C71B0F21AEEB286A12363C12F29B6C2E42B96EEF65524B24BDBA61B6`

Build result: 0 errors, 0 warnings. The known PA8 SysConfig package-model
message occurs before the successful compile and link.

## Contract

V16 uses the current official author frame without a work translation:

```text
raw = work + (-129, +128) mm
+X = paper right
+Y = paper up
```

It uses the V15 measured fixed-switch angles:

```text
theta_limit=-0.709247 deg
psi_limit=134.323770 deg
Stage1=43.708318 steps/degree
Stage2=48.8 steps/degree
```

Full 297x210 mm A4 remains disabled because the switches cannot reach its BL
and TL joint angles. The V16 outer rectangle is an inset safe sub-region of
the official A4 coordinates:

```text
X=120..290 mm
Y=5..125 mm
size=170x120 mm
```

Every target and every synchronized integer-pulse path was checked offline.
The minimum target and inter-target joint margin is 3.364751 degrees beyond
the firmware hard safety line.

## Behavior

- Startup raises the pen, then performs the normal two-speed limit home.
- After homing, no probe point moves automatically.
- Only one exact `NEXT` advances one point.
- `STATUS` is read-only.
- `STOP` stops the motors and requires another home before continuing.
- `DRAW`, G-code, and all other commands are rejected.
- The pen remains at 90 degrees for the complete probe.
- Direction compensation remains disabled.

Keep the physical power switch available. UART `STOP` is not a replacement
for cutting motor power when motion direction, cable clearance, or mechanism
behavior is unexpected.

## Point Sequence

```text
1  REF_150_20    (150,  20)
2  X_PLUS_20     (170,  20)
3  REF_AFTER_X   (150,  20)
4  Y_PLUS_20     (150,  40)
5  REF_AFTER_Y   (150,  20)
6  RECT_BL       (120,   5)
7  RECT_BR       (290,   5)
8  RECT_TR       (290, 125)
9  RECT_TL       (120, 125)
10 RECT_CLOSE    (120,   5)
11 REF_CLOSE     (150,  20)
```

Points 1-5 verify the author paper-axis meaning before any outer corner is
visited. The longest outer move can take about 15 seconds at the configured
probe speed.

## Required Procedure

1. Close Mechanical Arm Master so it cannot own COM7.
2. Ensure the pen and both arms have clearance for automatic homing.
3. Flash V16 and allow homing to finish.
4. Require RTT to show the V16 build ID, homing success, `WAIT_NEXT`,
   `lim1=0 lim2=0`, and `pen=UP`.
5. Send `STATUS` with the dedicated script.
6. Send exactly one confirmed `NEXT`, observe the endpoint, and wait for
   `REACHED` before considering the next point.

```powershell
.\tools\author_safe_probe_command.ps1 STATUS
.\tools\author_safe_probe_command.ps1 NEXT -ConfirmPenUpClearance
.\tools\author_safe_probe_command.ps1 STOP
```

For `NEXT`, the script first queries `STATUS`. It sends no movement command
unless the firmware ID is V16, the state is `WAIT_NEXT`, both limits are
clear, and the pen reports UP.

Offline verification:

```powershell
python .\tools\check_author_safe_probe_v16.py
```
