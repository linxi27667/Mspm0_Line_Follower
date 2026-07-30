# Author Stage1 976-Pulse Chord Calibration V23

Firmware:

`keil/AUTHOR_STAGE1_976P_CHORD_L205_GATED_V23.hex`

Firmware SHA-256:

`1692047EC8611AA5084B21108568D225787F5447DB948412823CEA2FA379B383`

Mechanical Arm Master gate file:

`gcode/AUTHOR_STAGE1_976P_CHORD_RUN_V23.gcode`

G-code SHA-256:

`16518E55E269CF3B8631D1223D5BEF19DB5B499BF55D4804EB8B0F61B84ED875`

Build result: 0 errors and 0 warnings with the required project
`keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx`. The known PA8
SysConfig package-model message appears before the successful compile, link,
and HEX generation.

## Purpose

V23 measures the Stage1 arm scale from a large two-point chord. Angle readings
are optional cross-checks and are not needed for the final calculation.

The sequence is:

1. complete normal two-speed homing and switch release;
2. wait for the UART gate with the pen up;
3. use the 1 mm Cartesian planner to approach user point (205,65) mm;
4. make stationary start mark A0;
5. move Stage1 exactly 976 raw pulses away from its limit while Stage2 emits
   zero pulses;
6. make stationary endpoint mark B;
7. return Stage1 exactly 976 raw pulses;
8. make stationary closure mark A1 and stop permanently.

The pen is up during all motion. Only the three stationary marks touch paper;
no arc or chord line is drawn.

## Retained Contract

- L1=205 mm and L2=203 mm;
- author work offset (-129,+128) mm;
- +X right and +Y up;
- theta limit -0.709247 degrees and psi limit 134.323770 degrees;
- Stage1 candidate scale 43.708318 steps/degree;
- Stage2 scale 48.8 steps/degree;
- direction compensation disabled;
- pen 0 degrees down and 90 degrees up;
- 1 mm Cartesian IK approach;
- one UART-gated pass and reset/rehome required afterward.

## Offline Integer Result

```text
quantized start steps:       Stage1=2296, Stage2=8365
quantized end steps:         Stage1=3272, Stage2=8365
quantized return steps:      Stage1=2296, Stage2=8365
Stage1 pulses each raw leg:  976
Stage2 raw-leg pulses:       0
model angle change:          22.329846386 degrees
model start:                 (205.014130, 65.009705) mm
model end:                   (276.182953, 100.191284) mm
model chord:                 79.389829 mm
raw-arc paper margin:        20.817047 mm minimum
raw-arc joint margin:        36.090161 degrees minimum
integer return closure:      0 mm
```

All 64 supported final home-release combinations were checked: Stage1 total
release delta 45..52 pulses and Stage2 50..57 pulses. Every approach uses 137
Cartesian targets, remains inside hard joint limits, and reaches the same
integer start target. The worst offline quantized line deviation is
0.102482 mm.

## Mechanical Arm Master Procedure

1. Flash `AUTHOR_STAGE1_976P_CHORD_L205_GATED_V23.hex`. Do not flash the
   changing output under `keil/Objects`.
2. Reset and wait for the complete homing and limit-release cycle.
3. Confirm RTT contains build ID
   `AUTHOR_STAGE1_976P_CHORD_L205_GATED_V23`, `lim1=0`, `lim2=0`, and pen up.
4. Tape the full A4 sheet flat at four points. Do not hold it by hand.
5. Open Mechanical Arm Master at 115200 8N1 and load
   `AUTHOR_STAGE1_976P_CHORD_RUN_V23.gcode`.
6. Press Run exactly once. Wait for `ok DONE ... marks=3 stage2_delta=0`.
7. Do not press Run again. Reset and rehome before any later motion.

Optional serial control:

```powershell
.\tools\stage1_chord_v23_control.ps1 STATUS -PortName COM7
.\tools\stage1_chord_v23_control.ps1 START -PortName COM7 -ConfirmPaperFixed
.\tools\stage1_chord_v23_control.ps1 STOP -PortName COM7
```

For immediate mechanical danger, cut motor power rather than relying on a
host application's Stop button.

## Measurement Return

Measure center to center, preferably to 0.1 mm:

```text
A0-to-B chord = ___ mm
A0-to-A1 closure = ___ mm
optional Stage1 angle change = ___ degrees
```

Use A0, the first start mark, for the chord. If A0 and A1 are visibly
separate, an overhead video or close-up can identify their order. Also report
the practical reading uncertainty, for example plus or minus 0.2 mm.

The Stage1 scale is calculated from the measured chord C using L1=205 mm:

```text
delta_theta_deg = 2 * asin(C / 410) * 180 / pi
new_stage1_steps_per_degree = 976 / delta_theta_deg
```

The Stage2 link length does not enter this chord formula because Stage2 is
held at a fixed absolute angle throughout the raw Stage1 leg.

## Offline Verification

Run:

```powershell
python .\tools\check_stage1_chord_cal_v23.py
```

The checker validates the source contract, gate file, every integer approach
and raw-arc pulse, joint and paper bounds, correct Keil project, clean build,
Intel HEX checksums, embedded V23 Build ID, and SHA-256 digest.
