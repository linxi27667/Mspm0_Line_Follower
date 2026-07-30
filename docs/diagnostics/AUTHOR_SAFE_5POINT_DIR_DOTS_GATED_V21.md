# Author Safe 5-Point Direction Dots V21

Firmware:

`keil/AUTHOR_SAFE_5POINT_DIR_DOTS_GATED_V21.hex`

Firmware SHA-256:

`317E7A032176389934768DFA41D1F07D6DC21565E148E8F20CE8858413691AAD`

Mechanical Arm Master gate file:

`gcode/AUTHOR_SAFE_5POINT_DIR_DOTS_RUN_V21.gcode`

G-code SHA-256:

`16518E55E269CF3B8631D1223D5BEF19DB5B499BF55D4804EB8B0F61B84ED875`

Build result: 0 errors and 0 warnings with the required project
`keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx`. The known PA8
SysConfig package-model message appears before the successful compile, link,
and HEX generation.

## Purpose

V21 separates fixed geometry/scale error from reversal error. It makes four
isolated rectangle-corner marks, one baseline center mark, and four more
center marks after approaching the same center from west, east, south, and
north. Every travel move is pen-up. No connecting edge is drawn.

The retained machine contract is:

- L1=L2=200 mm and author work offset (-129,+128) mm;
- +X right and +Y up;
- theta limit -0.709247 degrees and psi limit 134.323770 degrees;
- Stage1 43.708318 and Stage2 48.8 steps/degree;
- direction compensation disabled;
- pen 0 degrees down and 90 degrees up;
- 1 mm Cartesian IK segmentation for all travel.

No scale correction is applied in V21. This diagnostic does not validate or
enable full A4 motion.

## Embedded Point Sequence

The firmware contains the only permitted motion list:

```text
A          (120,   5) mark
B          (120, 125) mark
C          (290, 125) mark
D          (290,   5) mark
O_BASE     (205,  65) mark
W_APPROACH (185,  65) no mark
O_FROM_W   (205,  65) mark
E_APPROACH (225,  65) no mark
O_FROM_E   (205,  65) mark
S_APPROACH (205,  45) no mark
O_FROM_S   (205,  65) mark
N_APPROACH (205,  85) no mark
O_FROM_N   (205,  65) mark
```

There are 13 motion targets and 9 pen stamps. The nominal corner distances
are AB=120 mm, BC=170 mm, CD=120 mm, DA=170 mm, and both diagonals are
208.087 mm. The center is stamped five times at the same requested point.

## Gate And Stop Rules

After homing, the firmware raises the pen and waits without moving. It accepts
the setup sequence `G21`, `G90`, `G94`, and `M5`; `M501` starts the embedded
point sequence only after all four setup commands have arrived. `RUN` is an
equivalent manual start command after the same setup.

`STATUS` or `?` is always allowed. `STOP` raises the pen, stops both axes, and
requires reset plus rehome. Any unexpected UART command while moving does the
same. After `DONE`, a second run is rejected and reset plus rehome is required.

The five-line G-code file is only a gate. It contains no X/Y/Z coordinate,
feed, pen-down, G0, or G1 command. Arbitrary G-code motion is disabled.

## Mechanical Arm Master Procedure

1. Flash `AUTHOR_SAFE_5POINT_DIR_DOTS_GATED_V21.hex`.
2. Reset the board and allow the complete two-speed homing and limit release
   cycle to finish. The pen must remain up and both switches must be clear.
3. Tape the full A4 sheet to the flat backing at all four corners. Do not hold
   the paper by hand during motion. Clear the complete arm workspace and keep
   immediate access to motor power.
4. Open Mechanical Arm Master at 115200 8N1 and load
   `AUTHOR_SAFE_5POINT_DIR_DOTS_RUN_V21.gcode`.
5. Press Run exactly once. The host must send one line at a time and wait for
   each `ok` reply.
6. Wait for `DONE`; do not press Run again. Reset and rehome before any later
   motion.

The optional preflight/control commands are:

```powershell
.\tools\point_dots_v21_control.ps1 STATUS -PortName COM7
.\tools\point_dots_v21_control.ps1 START -PortName COM7 -ConfirmPaperFixed
.\tools\point_dots_v21_control.ps1 STOP -PortName COM7
```

The application's Stop button may only stop host transmission. For immediate
mechanical danger, cut motor power.

## Offline Verification

Run:

```powershell
python .\tools\check_author_point_dots_v21.py
```

Verified result:

```text
source contract: PASS, UART-gated single pass
G-code gate: 5 lines, motion words=0, pen-down=0
home release envelope: Stage1 45..52, Stage2 50..57 pulses
motion target counts: [49,120,170,120,85,20,20,20,20,20,20,20,20]
total Cartesian targets: 704
total master pulses: 9203
minimum marked-target joint margin: 3.364751 degrees
maximum endpoint quantization error: 0.039665 mm
maximum target-to-target quantized line deviation: 0.084194 mm
maximum worst-case home-approach deviation: 0.099161 mm
Keil: correct project, 0 errors, 0 warnings
Intel HEX and embedded V21 build ID: PASS
```

## Measurement Return

After the run, label A/B/C/D from the sequence above and return center-to-
center chord measurements in millimetres:

```text
AB, BC, CD, DA, AC, BD
maximum horizontal spread of the five O stamps
maximum vertical spread of the five O stamps
```

Also provide one perpendicular, uncropped photo of the whole A4 sheet and one
close-up of the center O cluster. Do not infer edge bow from these isolated
points; V21 is designed to measure endpoint geometry and direction-dependent
arrival only.
