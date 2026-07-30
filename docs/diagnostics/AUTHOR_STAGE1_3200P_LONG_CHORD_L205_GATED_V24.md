# Author Stage1 3200-Pulse Long-Chord Calibration V24

Firmware:

`keil/AUTHOR_STAGE1_3200P_LONG_CHORD_L205_GATED_V24.hex`

Firmware SHA-256:

`1A8031834390D16EF77FBFEBFE1A6D6CACEE31C4B81500726BC54D3E71D2BFA5`

Mechanical Arm Master gate file:

`gcode/AUTHOR_STAGE1_3200P_LONG_CHORD_RUN_V24.gcode`

G-code SHA-256:

`16518E55E269CF3B8631D1223D5BEF19DB5B499BF55D4804EB8B0F61B84ED875`

Build result: 0 errors and 0 warnings with the required project
`keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx`. The known PA8
SysConfig package-model message appears before the successful compile, link,
and HEX generation.

## Purpose

V23 measured an 81 mm chord with an estimated reading uncertainty below
0.5 mm. Using L1=205 mm, that gives a provisional Stage1 result of
42.828178 steps/degree and an uncertainty interval of
42.561897..43.097743 steps/degree.

V24 increases the raw Stage1 leg from 976 to 3200 pulses. The expected chord
is approximately 249 mm, reducing the same 0.5 mm ruler uncertainty from
about 0.63 percent to about 0.24 percent in the Stage1 scale.

V24 intentionally retains the existing 43.708318 steps/degree source value.
It does not commit the provisional calibration. The provisional minimum and
maximum scales are used as additional physical-path guards before motion.

## Sequence

1. complete normal two-speed homing and switch release;
2. wait for the UART gate with the pen up;
3. use the 1 mm Cartesian planner to approach user point
   (94.314,19.091) mm;
4. make stationary start mark A0;
5. move Stage1 exactly 3200 raw pulses away from its limit while Stage2 emits
   zero pulses;
6. make stationary endpoint mark B;
7. return Stage1 exactly 3200 raw pulses;
8. make stationary closure mark A1 and stop permanently.

The pen is up during all motion. Only the three stationary marks touch paper;
no arc or chord line is drawn. Each raw leg takes approximately 32 seconds at
100 pulses/second, so the complete test normally takes more than one minute.

## Retained Contract

- L1=205 mm and L2=203 mm;
- author work offset (-129,+128) mm;
- +X right and +Y up;
- theta limit -0.709247 degrees and psi limit 134.323770 degrees;
- Stage1 source scale remains 43.708318 steps/degree;
- Stage2 scale remains 48.8 steps/degree;
- direction compensation disabled;
- pen 0 degrees down and 90 degrees up;
- one UART-gated pass and reset/rehome required afterward.

## Offline Integer Result

```text
quantized start steps:       Stage1=401, Stage2=7110
quantized end steps:         Stage1=3601, Stage2=7110
quantized return steps:      Stage1=401, Stage2=7110
Stage1 pulses each raw leg:  3200
Stage2 raw-leg pulses:       0

nominal source-model chord:  244.488404 mm
candidate physical chord:    247.457435..250.115913 mm
candidate paper margin:      19.502319 mm minimum
candidate joint margin:      9.013679 degrees minimum
integer return closure:      0 mm
```

All 64 supported final home-release combinations were checked: Stage1 total
release delta 45..52 pulses and Stage2 50..57 pulses. Every approach uses 26
Cartesian targets, remains inside hard joint limits, and reaches the same
integer start target. The worst offline quantized approach-line deviation is
0.104872 mm.

## Mechanical Arm Master Procedure

1. Flash `AUTHOR_STAGE1_3200P_LONG_CHORD_L205_GATED_V24.hex`. Do not flash the
   changing output under `keil/Objects`.
2. Reset and wait for the complete homing and limit-release cycle.
3. Confirm RTT contains build ID
   `AUTHOR_STAGE1_3200P_LONG_CHORD_L205_GATED_V24`, `lim1=0`, `lim2=0`, and
   pen up.
4. Tape the full A4 sheet flat at four points. Do not hold it by hand.
5. Open Mechanical Arm Master at 115200 8N1 and load
   `AUTHOR_STAGE1_3200P_LONG_CHORD_RUN_V24.gcode`.
6. Press Run exactly once. The two long raw legs each take about 32 seconds.
7. Wait for `ok DONE ... pulses=3200 marks=3 stage2_delta=0`.
8. Do not press Run again. Reset and rehome before any later motion.

Optional serial control:

```powershell
.\tools\stage1_long_chord_v24_control.ps1 STATUS -PortName COM7
.\tools\stage1_long_chord_v24_control.ps1 START -PortName COM7 -ConfirmPaperFixed
.\tools\stage1_long_chord_v24_control.ps1 STOP -PortName COM7
```

For immediate mechanical danger, cut motor power rather than relying on a
host application's Stop button.

## Measurement Return

Measure center to center. A 0.1 mm reading is preferred, but a nearest-1 mm
reading is still useful with this long chord.

```text
A0-to-B chord = ___ mm
A0-to-A1 closure = ___ mm
optional Stage1 angle change = ___ degrees
reading uncertainty = plus/minus ___ mm
```

Use A0, the first start mark, for the chord. If A0 and A1 visually merge,
report the maximum closure-cluster diameter and provide a close-up photo.

The final Stage1 scale is calculated from measured chord C using L1=205 mm:

```text
delta_theta_deg = 2 * asin(C / 410) * 180 / pi
new_stage1_steps_per_degree = 3200 / delta_theta_deg
```

After the long-chord result is accepted, the V15 Stage1 limit angle must be
recomputed consistently from its original 31-pulse absolute search:

```text
new_theta_limit_deg = -31 / new_stage1_steps_per_degree
```

Do not edit only the steps/degree value without this dependent limit update.

## Offline Verification

Run:

```powershell
python .\tools\check_stage1_long_chord_cal_v24.py
```

The checker validates the source contract, gate file, every integer approach
and raw-arc pulse at the nominal and provisional boundary scales, joint and
paper bounds, correct Keil project, clean build, Intel HEX checksums, embedded
V24 Build ID, and SHA-256 digest.
