# Author Safe 5-Point Unequal-Link Dots V22

Firmware:

`keil/AUTHOR_SAFE_5POINT_DIR_DOTS_L205_L203_GATED_V22.hex`

Firmware SHA-256:

`D6F50D1FC34BE7A38D21141BF0436E562C5A269E22895D9D2298B515DBFA336B`

Mechanical Arm Master gate file:

`gcode/AUTHOR_SAFE_5POINT_DIR_DOTS_L205_L203_RUN_V22.gcode`

G-code SHA-256:

`16518E55E269CF3B8631D1223D5BEF19DB5B499BF55D4804EB8B0F61B84ED875`

Build result: 0 errors and 0 warnings with the required project
`keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx`. The known PA8
SysConfig package-model message appears before the successful compile, link,
and HEX generation.

## Purpose

V22 formally tests the measured unequal effective lengths L1=205 mm and
L2=203 mm. It retains the V21 isolated-point pattern so the resulting six
corner chords and center arrival spread can be compared directly with V21.

V22 changes only the link-length model and the inverse formula required to
support unequal links. It does not change the joint scales, electrical limit
angles, work offset, direction compensation, point coordinates, or pen timing.

## Unequal-Link IK Correction

The author source used squared K terms:

```text
K1=L1^2+L2^2*cos(q2)
K2=L2^2*sin(q2)
```

Their common scale cancels when L1 equals L2, but the expression is not a
general unequal-link inverse. With L1=205 and L2=203 it produced an IK/FK
round-trip error of approximately 1.85 mm and V21 correctly rejected the
first move.

V22 uses the general two-link terms while retaining the author's coordinate
and swapped-atan2 convention:

```text
K1=L1+L2*cos(q2)
K2=L2*sin(q2)
```

The maximum float32 IK/FK round-trip error across all V22 targets is
0.000031457 mm.

## Retained Contract

- L1=205 mm and L2=203 mm;
- author work offset (-129,+128) mm;
- +X right and +Y up;
- theta limit -0.709247 degrees and psi limit 134.323770 degrees;
- Stage1 43.708318 and Stage2 48.8 steps/degree;
- direction compensation disabled;
- pen 0 degrees down and 90 degrees up;
- 1 mm Cartesian IK segmentation;
- one UART-gated pass with no automatic motion after homing.

## Point Sequence

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

Nominal distances remain AB=120 mm, BC=170 mm, CD=120 mm, DA=170 mm, and
AC=BD=208.087 mm. The center is stamped five times.

## Mechanical Arm Master Procedure

1. Flash `AUTHOR_SAFE_5POINT_DIR_DOTS_L205_L203_GATED_V22.hex`. Do not flash
   the changing build output under `keil/Objects`.
2. Reset and wait for the complete two-speed homing and limit-release cycle.
3. Confirm the RTT build ID
   `AUTHOR_SAFE_5POINT_DIR_DOTS_L205_L203_GATED_V22`, L1=20500, L2=20300,
   `lim1=0`, `lim2=0`, and pen up.
4. Tape the full A4 sheet at all four corners. Do not hold it by hand.
5. Open Mechanical Arm Master at 115200 8N1 and load
   `AUTHOR_SAFE_5POINT_DIR_DOTS_L205_L203_RUN_V22.gcode`.
6. Press Run exactly once and wait for `DONE`.
7. Do not run a second pass. Reset and rehome before any later motion.

Optional preflight and stop commands:

```powershell
.\tools\point_dots_v22_control.ps1 STATUS -PortName COM7
.\tools\point_dots_v22_control.ps1 START -PortName COM7 -ConfirmPaperFixed
.\tools\point_dots_v22_control.ps1 STOP -PortName COM7
```

For immediate mechanical danger, cut motor power rather than relying on a
host application's Stop button.

## Offline Verification

Run:

```powershell
python .\tools\check_author_point_dots_v22.py
```

Verified result:

```text
source contract: PASS, L1=205, L2=203, general unequal-link IK
G-code gate: 5 lines, motion words=0, pen-down=0
IK/FK maximum round-trip error: 0.000031457 mm
home release envelope: Stage1 45..52, Stage2 50..57 pulses
move segments: [52,120,170,120,85,20,20,20,20,20,20,20,20]
total Cartesian targets: 707
total master pulses: 9178
minimum marked-target joint margin: 4.635242 degrees
maximum endpoint quantization error: 0.049328 mm
maximum target-to-target line deviation: 0.081542 mm
maximum worst-case home-approach deviation: 0.103025 mm
Keil: correct project, 0 errors, 0 warnings
Intel HEX and embedded V22 build ID: PASS
```

## Measurement Return

Return center-to-center measurements in millimetres:

```text
AB, BC, CD, DA, AC, BD
maximum horizontal spread of the five O stamps
maximum vertical spread of the five O stamps
```

Also provide one perpendicular full-sheet photo and one center-cluster
close-up. Compare these values directly with the V21 result:

```text
AB=126 BC=202 CD=146 DA=188 AC=228 BD=246 O=1x1 mm
```
