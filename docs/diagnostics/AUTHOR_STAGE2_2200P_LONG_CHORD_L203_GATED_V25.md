# Author Stage2 2200-Pulse Long-Chord Calibration V25

Firmware:

`keil/AUTHOR_STAGE2_2200P_LONG_CHORD_L203_GATED_V25.hex`

Firmware SHA-256:

`C7A6433A7F7EF86D3B5CD715699BF871397821286A9F2C675DB8F0BAB496DD20`

Mechanical Arm Master gate file:

`gcode/AUTHOR_STAGE2_2200P_LONG_CHORD_RUN_V25.gcode`

G-code SHA-256:

`16518E55E269CF3B8631D1223D5BEF19DB5B499BF55D4804EB8B0F61B84ED875`

Build result: 0 errors and 0 warnings with the required project
`keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx`. The known PA8
SysConfig package-model message appears before the successful compile, link,
and HEX generation.

## Purpose

V24 moved only Stage1 by 3200 raw pulses. Two independent runs both measured
an A0-to-B chord of approximately 263 mm, with no visible A0-to-A1 closure
error and no Stage2 motor or belt motion. With L1=205 mm, the accepted result
is:

```text
Stage1 angle change:       79.802059 degrees
Stage1 steps/degree:       40.099216
Stage1 switch angle:       -0.773082 degrees
measurement interval:      40.007831..40.190898 steps/degree
```

V25 commits those two dependent Stage1 values and performs the corresponding
long-chord measurement on Stage2. It does not commit a new Stage2 scale; the
existing 48.8 steps/degree remains provisional until the V25 dots are
measured.

## Sequence

1. complete normal two-speed homing and switch release;
2. wait for the UART gate with the pen up;
3. use the 1 mm Cartesian planner to approach user point
   (196.452,184.639) mm;
4. make stationary start mark A0;
5. move Stage2 exactly 2200 raw pulses away from its limit while Stage1 emits
   zero pulses;
6. make stationary endpoint mark B;
7. return Stage2 exactly 2200 raw pulses;
8. make stationary closure mark A1 and stop permanently.

The pen is up during every move. Only the three stationary marks touch the
paper; no arc or chord line is drawn. Each raw leg takes approximately 22
seconds at 100 pulses/second.

## Retained Contract

- L1=205 mm and L2=203 mm;
- author work offset (-129,+128) mm;
- +X right and +Y up;
- theta limit -0.773082 degrees and psi limit 134.323770 degrees;
- Stage1 40.099216 steps/degree and provisional Stage2 48.8 steps/degree;
- direction compensation disabled;
- pen 0 degrees down and 90 degrees up;
- one UART-gated pass and reset/rehome required afterward.

## Offline Integer Result

```text
quantized start steps:       Stage1=2567, Stage2=6870
quantized end steps:         Stage1=2567, Stage2=9070
quantized return steps:      Stage1=2567, Stage2=6870
Stage1 raw-leg pulses:       0
Stage2 pulses each raw leg:  2200

nominal start:               (196.452058,184.638657) mm
nominal endpoint:            (241.125014,35.549982) mm
nominal source-model chord:  155.637739 mm
candidate physical chord:    149.251850..164.571981 mm
candidate paper margin:      24.444654 mm minimum
candidate joint margin:      5.176471 degrees minimum
integer return closure:      0 mm
```

The physical guard covers the full Stage1 measurement interval
40.007831..40.190898 and the deliberately broad provisional Stage2 interval
46..51 steps/degree. The Stage2 reference is converted correctly around the
known 135-degree pose:

```text
physical_psi = 135 + (target_steps - 6588) / candidate_scale
physical_psi_limit = 135 - 33 / candidate_scale
```

All 64 supported final home-release combinations were checked: Stage1 total
release delta 41..48 pulses and Stage2 50..57 pulses. Every approach uses
169..170 Cartesian targets and reaches the same integer start target. The
worst offline quantized approach-line deviation is 0.085397 mm.

## Mechanical Arm Master Procedure

1. Do not run V24 again. Reset the board so it performs a fresh home cycle.
2. Flash `AUTHOR_STAGE2_2200P_LONG_CHORD_L203_GATED_V25.hex`.
3. Reset again and wait for the complete homing and switch-release cycle.
4. Confirm RTT contains build ID
   `AUTHOR_STAGE2_2200P_LONG_CHORD_L203_GATED_V25`, `lim1=0`, `lim2=0`, and
   pen up.
5. Tape the full A4 sheet flat at four points. Do not hold it by hand.
6. Open Mechanical Arm Master at 115200 8N1 and load
   `AUTHOR_STAGE2_2200P_LONG_CHORD_RUN_V25.gcode`.
7. Press Run exactly once, then wait for
   `ok DONE ... pulses=2200 marks=3 stage1_delta=0`.
8. Do not press Run again. Reset and rehome before any later motion.

Optional serial control:

```powershell
.\tools\stage2_long_chord_v25_control.ps1 STATUS -PortName COM7
.\tools\stage2_long_chord_v25_control.ps1 START -PortName COM7 -ConfirmPaperFixed
.\tools\stage2_long_chord_v25_control.ps1 STOP -PortName COM7
```

For immediate mechanical danger, cut motor power rather than relying on a
host application's Stop button.

## Measurement Return

Measure dot center to dot center. A0 is the first start mark, B is the far
mark, and A1 is the return mark at A0.

```text
A0-to-B chord = ___ mm
A0-to-A1 closure = ___ mm
optional Stage2 angle change = ___ degrees
reading uncertainty = plus/minus ___ mm
```

If A0 and A1 visually merge, report the maximum closure-cluster diameter.

The final Stage2 scale is calculated from measured chord C using L2=203 mm:

```text
delta_psi_deg = 2 * asin(C / 406) * 180 / pi
new_stage2_steps_per_degree = 2200 / delta_psi_deg
```

The Stage2 switch angle must then be recomputed from the original 33-pulse
absolute search:

```text
new_psi_limit_deg = 135 - 33 / new_stage2_steps_per_degree
```

Do not edit only the Stage2 steps/degree value without this dependent limit
update.

## Offline Verification

Run:

```powershell
python .\tools\check_stage2_long_chord_cal_v25.py
```

The checker validates the source contract, gate file, every integer approach
and raw-arc pulse, the full continuous candidate-scale rectangle, joint and
paper margins, correct Keil project, clean build, Intel HEX structure,
embedded V25 Build ID, and SHA-256 digest.
