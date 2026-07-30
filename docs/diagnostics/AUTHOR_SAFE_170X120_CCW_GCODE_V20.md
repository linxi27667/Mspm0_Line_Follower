# Author Safe 170x120 CCW G-code V20

Firmware:

`keil/AUTHOR_SAFE_170X120_CCW_GCODE_V20.hex`

Firmware SHA-256:

`3FF5C82B894A5FA573A5F83E6A7D87213185EA2F65A7765B45243857F14A4F9F`

G-code:

`gcode/AUTHOR_SAFE_170X120_CCW_SINGLE_V20.gcode`

G-code SHA-256:

`7F0CB49B7E5460D0FE85D30F61D41F19731DBE94F6F956607CCE2F47D1FA957C`

Build result: 0 errors, 0 warnings with the required project
`keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx`. The known PA8
SysConfig package-model message appears before the successful compile, link,
and HEX generation.

## Purpose

V20 is the matched counterclockwise comparison for the measured V19 CW
rectangle. It keeps the same coordinates, feed, author work frame, homing
limits, joint scales, and one-millimetre target spacing. Only the boundary
order and the firmware gate direction change.

V20 retains the verified hardware contract:

- author work frame offset (-129,+128) mm;
- +X right and +Y up;
- theta limit -0.709247 degrees and psi limit 134.323770 degrees;
- Stage1 43.708318 and Stage2 48.8 steps/degree;
- direction compensation disabled;
- pen 0 degrees down and 90 degrees up.

## Restricted Program

The G-code contains exactly 590 nonblank lines:

```text
setup: G21, G90, G94, F200, S1000, G0Z0, M5
approach: one G0 to A/BL=(120,5), pen up
draw: M3, then 580 one-millimetre G1 targets
order: A/BL -> D/BR -> C/TR -> B/TL -> A/BL
finish: M5
```

The firmware enforces the same CCW order independently of the file. It
rejects and locks motion after an invalid edge, skipped point, repeated run,
early pen command, arbitrary rapid target, or unsupported command. Any
rejection raises the pen, stops motion, invalidates the position, and requires
reset plus rehome. `STOP` remains available while motion is busy.

V19 rejects this CCW file, and V20 rejects the V19 CW file. The firmware and
G-code must always be used as a matching pair.

## Mechanical Arm Master Procedure

1. Flash `AUTHOR_SAFE_170X120_CCW_GCODE_V20.hex`.
2. Reset and allow the normal two-speed homing cycle to finish.
3. Keep Mechanical Arm Master closed and verify readiness:

   ```powershell
   .\tools\gcode_v20_control.ps1 STATUS
   ```

   Require ID `AUTHOR_SAFE_170X120_CCW_GCODE_V20`, `phase=WAIT_APPROACH`,
   `busy=0`, `lim1=0`, `lim2=0`, and `pen=UP`.
4. Close the status script, open Mechanical Arm Master, select COM7 at
   115200 8N1, and load `AUTHOR_SAFE_170X120_CCW_SINGLE_V20.gcode`.
5. Use a fresh full A4 sheet in the same physical placement as the V19 CW
   sheet. Keep immediate access to motor power.
6. Press Run exactly once. The host must wait for `ok` before sending the next
   line.
7. After completion, label the sheet `V20 CCW`. Do not press Run again; reset
   and rehome before any later motion.

The application's Stop button may only stop host transmission. For immediate
mechanical danger, cut motor power. If COM7 is free, the firmware emergency
command is:

```powershell
.\tools\gcode_v20_control.ps1 STOP
```

## Offline Verification

Run:

```powershell
python .\tools\check_author_rect_gcode_v20.py
```

Verified result:

```text
source contract: PASS, restricted CCW single pass
protocol: 590 lines, G0=1, G1=580, M3=1, M5=2
draw master pulses: 7547
minimum joint margin: 3.364751 degrees
maximum quantized line deviation: 0.083374 mm
integer-step closure error: (0,0)
final pen: UP
Keil: correct project, 0 errors, 0 warnings
Intel HEX and embedded V20 build ID: PASS
```

This test does not validate full A4 and must not be used for the final Chinese
character G-code.

## CCW Measurement Return

Measure corner-to-corner chords directly on the paper in millimetres:

```text
AB, BC, CD, DA, AC, BD
BC bow magnitude and inward/outward direction
CD bow magnitude and inward/outward direction
DA bow magnitude and inward/outward direction
AB bow magnitude and inward/outward direction
A left tail length and closure offset
```
