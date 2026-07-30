# Author Safe 170x120 CW G-code V19

Firmware:

`keil/AUTHOR_SAFE_170X120_CW_GCODE_V19.hex`

Firmware SHA-256:

`CCCC2E0F495C8B5A2025DA4584566C824EBA2017FE2A4CB782ED46904E811A08`

G-code:

`gcode/AUTHOR_SAFE_170X120_CW_SINGLE_V19.gcode`

G-code SHA-256:

`8BFD3B7515E229E66E9B6CBF0061D1D031543C43071E5522D7290F82A286FD59`

Build result: 0 errors, 0 warnings with the required project
`keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx`. The known PA8
SysConfig package-model message appears before the successful compile, link,
and HEX generation.

## Purpose

V19 lets Mechanical Arm Master send one offline-checked 170 x 120 mm CW
rectangle by pressing Run. It is deliberately not a general G-code firmware.
The current V18 firmware cannot run this file and will reject every G/M line.

V19 retains the verified hardware contract:

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
approach: one G0 to BL=(120,5), pen up
draw: M3, then 580 one-millimetre G1 targets
order: BL -> TL -> TR -> BR -> BL
finish: M5
```

The firmware enforces the same order independently of the file. It rejects
and locks motion after any of the following:

- a rapid target other than BL;
- relative mode or a non-CW edge;
- a G1 point more than 1.01 mm from the preceding point;
- a point off the four verified boundary lines;
- early pen down, early pen up, skipped corner, repeated run, or arbitrary
  motion;
- a path/limit/motion error.

Any rejection raises the pen, stops motion, invalidates the position, and
requires reset plus rehome. `STOP` remains available even while motion is
busy. The physical power switch remains the primary emergency stop.

## Mechanical Arm Master Procedure

1. Flash `AUTHOR_SAFE_170X120_CW_GCODE_V19.hex`.
2. Reset and allow the normal two-speed homing cycle to finish.
3. Keep Mechanical Arm Master closed and verify readiness:

   ```powershell
   .\tools\gcode_v19_control.ps1 STATUS
   ```

   Require the V19 ID, `phase=WAIT_APPROACH`, `busy=0`, `lim1=0`, `lim2=0`,
   and `pen=UP`.
4. Close the status script, open Mechanical Arm Master, select COM7 at
   115200 8N1, and load `AUTHOR_SAFE_170X120_CW_SINGLE_V19.gcode`.
5. Confirm paper position, full linkage/cable clearance, and immediate access
   to motor power.
6. Press Run exactly once. The host must send one line only after receiving
   `ok` for the preceding line.
7. Do not press Run again after completion. Reset and rehome before another
   sheet.

The application's Stop button may only stop host transmission. For mechanical
danger, cut power. If COM7 is free, the firmware emergency command is:

```powershell
.\tools\gcode_v19_control.ps1 STOP
```

## Offline Verification

Run:

```powershell
python .\tools\check_author_rect_gcode_v19.py
```

Verified result:

```text
protocol errors=0
G0=1, G1=580, M3=1, M5=2
draw master pulses=7547
minimum joint margin=3.364751 degrees
maximum quantized line deviation=0.083374 mm
integer-step closure error=(0,0)
final pen=UP
```

This V19 rectangle does not validate full A4 and is not the firmware for
`2.0.gcode` or the final Chinese-character program.
