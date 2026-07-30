# A4 297 x 210 Axis Draw Gated V11

Firmware: `keil/A4_297X210_AXIS_DRAW_GATED_V11.hex`

SHA-256:

`7B1265E0C9C2B1788A1A070B04622D2559E6F69D88ACF2EBB6992F3EA459AF2E`

Build result: 0 errors, 0 warnings. The known PA8 SysConfig package-model
message appears before the successful compile, link, and HEX generation.

## What Changed From V6 And V10

- Joint calibration is unchanged: Stage1 43.708318 steps/degree and Stage2
  48.8 steps/degree.
- Home calibration is unchanged: theta 0 degrees and psi 135 degrees at the
  dual-limit reference, followed by the existing pull-off.
- Servo convention is unchanged: 0 degrees down and 90 degrees up.
- Direction compensation remains disabled.
- V6 drew a small rectangle aligned with the logical X/Y axes.
- V10 connected the intentionally rotated V9 joint-envelope points 5-8, so
  its 75 x 53 mm rectangle was rotated approximately 40 degrees.
- V11 removes the rotated envelope basis and draws a full 297 x 210 mm A4
  boundary parallel to the V6 X/Y axes.

## Workspace Placement

The selected full-A4 rectangle maximizes joint-limit margin while preserving
the V6 axis directions:

- Machine X: 0..297 mm
- Machine Y: 43..253 mm
- Current logged user X: 35.901..332.901 mm
- Current logged user Y: -139.890..70.110 mm

After `NEXT`, the raised pen is at the A4 top-left corner. Place the paper so:

- its top-left corner is under the pen;
- the 297 mm top edge extends in the V6 positive-X direction;
- the 210 mm side extends in the V6 negative-Y direction.

Do not send `DRAW` until the entire paper, cable path, linkage sweep, and gear
sweep are clear. This workspace is shifted from the former 10 x 5 mm test
area; an A4 sheet left at the old location will not cover the new boundary.

## Motion Contract

- Startup and homing hold the pen at 90 degrees (up).
- `NEXT` only positions at the A4 top-left corner with the pen up.
- `DRAW` is rejected until top-left is reached and both limits are clear.
- Accepted `DRAW` lowers to 0 degrees, waits 700 ms, draws
  `TL -> TR -> BR -> BL -> TL`, raises to 90 degrees, and waits 700 ms.
- The boundary contains 1,015 offline-IK absolute joint targets at 1 mm
  spacing and 1,014 draw segments.
- G-code is disabled.
- `STOP` raises the pen, stops both motors, invalidates position, and requires
  reboot plus homing.

For imminent contact, cable tension, or unexpected motion, cut motor power.
Do not rely on UART `STOP` instead of the physical power switch.

## Commands

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\a4_probe_command.ps1 -ProbeCommand STATUS
powershell -ExecutionPolicy Bypass -File .\tools\a4_probe_command.ps1 -ProbeCommand NEXT
powershell -ExecutionPolicy Bypass -File .\tools\a4_probe_command.ps1 -ProbeCommand DRAW
powershell -ExecutionPolicy Bypass -File .\tools\a4_probe_command.ps1 -ProbeCommand STOP
```

Never paste or batch commands. The required order is:

1. Flash V11 and allow homing to finish.
2. Require `A4_297X210_AXIS_DRAW_GATED_V11`, `axis=V6_XY`, `lim1=0`,
   `lim2=0`, and `pen=UP` in RTT.
3. Send `STATUS`; require `state=WAIT_NEXT action=NEXT`.
4. Send one `NEXT`; wait for `positioned=A4_TL ... wait=DRAW`.
5. Adjust and verify the A4 paper and full mechanical sweep.
6. Send `STATUS`; require `state=WAIT_DRAW action=DRAW`, both limits 0,
   and `pen=UP`.
7. Send one `DRAW`. Do not send another command while drawing.
8. Monitor all four corner logs and final completion. The full perimeter may
   take several minutes.

Expected completion:

```text
[A4DRAW] reached=A4_TR point=297/1014 ... lim1=0 lim2=0 pen=DOWN
[A4DRAW] reached=A4_BR point=507/1014 ... lim1=0 lim2=0 pen=DOWN
[A4DRAW] reached=A4_BL point=804/1014 ... lim1=0 lim2=0 pen=DOWN
[A4DRAW] reached=A4_TL_CLOSE point=1014/1014 ... lim1=0 lim2=0 pen=DOWN
[A4DRAW] A4_297X210_AXIS_DRAW_GATED_V11 done ... lim1=0 lim2=0 pen=UP
```

## Offline Verification

Run:

```powershell
python .\tools\check_a4_297x210_axis_draw.py
```

Verified results:

- Full interior integer-mm grid: 298 x 211 points passed
- Minimum joint-limit margin: 4.635794 degrees
- Boundary offline targets: 1,015
- Boundary draw segments: 1,014
- Approach master pulses: 1,670 minimum-home model
- Draw master pulses: 13,918
- Theta: 6.177..130.364 degrees
- Psi: 140.758..231.721 degrees
- Relative angle beta: 25.475..167.660 degrees
- Maximum integer-pulse line deviation per edge:
  0.0725, 0.0677, 0.0863, 0.0458 mm
- Generated path header matches the checker output
- Intel HEX: 3,167 records, 50,624 data bytes, valid checksums and one EOF

This validates the full A4 boundary and joint envelope. Paper-axis origin and
G-code mapping should only be finalized after the physical boundary is
confirmed.
