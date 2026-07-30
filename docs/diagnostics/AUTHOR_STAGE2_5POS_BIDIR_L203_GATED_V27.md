# Author Stage2 Five-Position Bidirectional Diagnostic V27

Firmware:

`keil/AUTHOR_STAGE2_5POS_BIDIR_L203_GATED_V27.hex`

Firmware SHA-256:

`5815041B35E5232D4B103CF4F048B1B03B2C4658C1E52542578F92CF1E4964CA`

Mechanical Arm Master gate file:

`gcode/AUTHOR_STAGE2_5POS_BIDIR_RUN_V27.gcode`

G-code SHA-256:

`16518E55E269CF3B8631D1223D5BEF19DB5B499BF55D4804EB8B0F61B84ED875`

Build result: 0 errors and 0 warnings with the required project
`keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx`. The known PA8
SysConfig package-model message appears before the successful compile, link,
and HEX generation.

## Purpose

The V25 2200-pulse chord measured 183 mm, implying 41.058408 steps/degree.
The corrected V26 1600-pulse chord measured 138.5 mm, implying 40.108458
steps/degree. Both returned to their start mark, but the two scales differ by
2.34 percent and cannot be averaged safely.

The author's forward kinematics uses a fixed L2 circle for Stage2, so V27
marks several pulse positions during one home cycle and one continuous
outbound/return sequence. This separates scale error from position-dependent
mechanical displacement, mark-center error, and direction hysteresis.

V27 deliberately retains the provisional 41.058408 source scale and the
broad 39..43 physical guard. It does not declare either V25 or V26 final.

## Sequence And Labels

After a pen-up Cartesian approach to (215.108,174.387) mm, V27 marks these
integer Stage2 positions while Stage1 is locked:

```text
mark 1: A_out     0 pulses
mark 2: B_out   400 pulses
mark 3: C_out   800 pulses
mark 4: D_out  1200 pulses
mark 5: E_turn 1600 pulses
mark 6: D_ret  1200 pulses
mark 7: C_ret   800 pulses
mark 8: B_ret   400 pulses
mark 9: A_ret     0 pulses
```

Every leg is exactly 400 raw Stage2 pulses. Stage1 emits zero pulses during
all eight legs. The pen is up during every move and only touches the paper at
the nine stationary marks. The final terminal checks require:

```text
Stage1 raw delta:  0 pulses
Stage2 raw total:  3200 pulses
final position:    0 pulses
marks completed:   9
```

## Offline Result

```text
quantized start steps:       Stage1=2668, Stage2=5983
quantized turn steps:        Stage1=2668, Stage2=7583
quantized return steps:      Stage1=2668, Stage2=5983
candidate paper margin:      33.976861 mm minimum
candidate joint margin:      10.000000 degrees minimum
integer pair separation:     0 mm
```

Expected cumulative chords from A at the provisional scale:

```text
A-B,  400 pulses:   34.475295 mm
A-C,  800 pulses:   68.701557 mm
A-D, 1200 pulses:  102.431553 mm
A-E, 1600 pulses:  135.421631 mm
```

With the full Stage2 candidate range 39..43 steps/degree:

```text
A-B:  32.922124..36.290151 mm
A-C:  65.627414..72.289777 mm
A-D:  97.900464..107.710678 mm
A-E: 129.528716..142.269287 mm
```

All 64 supported final home-release combinations were checked. Every
approach uses 159..160 Cartesian targets and reaches the same integer start.
The maximum quantized approach-line deviation is 0.100778 mm.

## Mechanical Arm Master Procedure

1. Do not run V25 or V26 again.
2. Flash `AUTHOR_STAGE2_5POS_BIDIR_L203_GATED_V27.hex`.
3. Reset and wait for the complete homing and switch-release cycle.
4. Confirm RTT contains build ID
   `AUTHOR_STAGE2_5POS_BIDIR_L203_GATED_V27`, `lim1=0`, `lim2=0`, and pen up.
5. Tape the full A4 sheet flat at four points. Do not hold it by hand.
6. Load `AUTHOR_STAGE2_5POS_BIDIR_RUN_V27.gcode` in Mechanical Arm Master at
   115200 8N1.
7. Press Run exactly once. The raw motion and marking sequence takes roughly
   50 seconds after the approach.
8. Wait for `ok DONE ... leg_pulses=400 max_position=1600 raw_total=3200
   positions=5 marks=9 stage1_delta=0`.
9. Do not press Run again. Reset and rehome before any later motion.

Optional serial control:

```powershell
.\tools\stage2_5pos_bidir_v27_control.ps1 STATUS -PortName COM7
.\tools\stage2_5pos_bidir_v27_control.ps1 START -PortName COM7 -ConfirmPaperFixed
.\tools\stage2_5pos_bidir_v27_control.ps1 STOP -PortName COM7
```

For immediate mechanical danger, cut motor power rather than relying on a
host application's Stop button.

## Measurements To Return

The paper should show five point clusters A through E. Measure dot center to
dot center.

```text
Adjacent 400-pulse chords:
AB = ___ mm
BC = ___ mm
CD = ___ mm
DE = ___ mm

Cumulative chords from A:
AC = ___ mm
AD = ___ mm
AE = ___ mm

Outbound/return cluster separation:
A_out to A_ret = ___ mm
B_out to B_ret = ___ mm
C_out to C_ret = ___ mm
D_out to D_ret = ___ mm
```

If a forward/return pair cannot be visually separated, report 0 or the
maximum visible cluster diameter. A straight-on photo of the five clusters
with their A/B/C/D/E labels is also useful.

## Actual Result - 2026-07-20

The user confirmed that every cumulative return measurement uses the original
outbound A mark as its fixed reference:

```text
AB / AB1 = 34.5 / 37 mm
AC / AC1 = 71 / 73 mm
AD / AD1 = 105 / 107 mm
AE       = 138 mm
```

The direct paired-mark separations were:

```text
AA1 = BB1 = CC1 = DD1 = 2 mm
```

Every return mark was on the E side of its outbound partner. This separates a
nearly fixed Stage2 reversal offset from the Stage2 scale. A 2 mm chord on the
203 mm Stage2 link is 0.564480 degree, or 22.645 pulses at the accepted
40.115790 steps/degree scale. The cumulative-chord fit independently estimated
about 25.5 pulses; the difference is consistent with millimetre-level manual
measurement resolution.

The accepted source calibration is therefore:

```text
Stage2 scale:       40.115790 steps/degree
Stage2 limit angle: 134.177381 degrees
```

This result does not enable production direction compensation. V28 performs a
single isolated 23-pulse return-takeup validation with Stage1 locked and the
pen raised during all motion.

## Offline Verification

Run:

```powershell
python .\tools\check_stage2_5pos_bidir_v27.py
```

The checker validates the source contract, gate file, every home approach,
the complete 39..43 candidate-scale arc, the exact nine-position sequence,
all eight 400-pulse legs, direction pairing, paper and joint margins, correct
Keil project, clean build, Intel HEX structure, embedded V27 Build ID, and
SHA-256 digest.
