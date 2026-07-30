# Author Stage2 1600-Pulse Confirmation V26

Firmware:

`keil/AUTHOR_STAGE2_1600P_CONFIRM_L203_GATED_V26.hex`

Firmware SHA-256:

`930BF3D253DBEC1DDAFCAC05026BC3EFBA0D49E1FBE36DD0CF65003966AA1171`

Mechanical Arm Master gate file:

`gcode/AUTHOR_STAGE2_1600P_CONFIRM_RUN_V26.gcode`

G-code SHA-256:

`16518E55E269CF3B8631D1223D5BEF19DB5B499BF55D4804EB8B0F61B84ED875`

Build result: 0 errors and 0 warnings with the required project
`keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx`. The known PA8
SysConfig package-model message appears before the successful compile, link,
and HEX generation.

## Purpose

V25 moved Stage2 by 2200 raw pulses. The measured A0-to-B chord was 183 mm,
and A0/A1 could not be visually separated. With L2=203 mm, that result gives:

```text
Stage2 angle change:       53.582204 degrees
provisional steps/degree:  41.058408
provisional switch angle:  134.196267 degrees
183 +/- 0.5 mm interval:   40.937581..41.179866 steps/degree
```

The V25 measurement lies outside its original 46..51 candidate interval. At
41.058408 steps/degree, its endpoint was approximately Y=2.2 mm, so V25 must
not be run again. V26 uses fewer pulses, a newly searched start point, and a
much wider 39..43 candidate interval to confirm the result with substantially
larger physical margins.

## Sequence

1. complete normal two-speed homing and switch release;
2. wait for the UART gate with the pen up;
3. use the 1 mm Cartesian planner to approach user point
   (215.108,174.387) mm;
4. make stationary start mark A0;
5. move Stage2 exactly 1600 raw pulses away from its limit while Stage1 emits
   zero pulses;
6. make stationary endpoint mark B;
7. return Stage2 exactly 1600 raw pulses;
8. make stationary closure mark A1 and stop permanently.

The pen is up during every move. Only the three stationary marks touch the
paper; no arc or chord line is drawn. Each raw leg takes approximately 16
seconds at 100 pulses/second.

## Active Provisional Contract

- L1=205 mm and L2=203 mm;
- author work offset (-129,+128) mm;
- +X right and +Y up;
- theta limit -0.773082 degrees and provisional psi limit 134.196267 degrees;
- Stage1 40.099216 steps/degree and provisional Stage2 41.058408 steps/degree;
- direction compensation disabled;
- pen 0 degrees down and 90 degrees up;
- one UART-gated pass and reset/rehome required afterward.

## Offline Integer Result

```text
quantized start steps:       Stage1=2668, Stage2=5983
quantized end steps:         Stage1=2668, Stage2=7583
quantized return steps:      Stage1=2668, Stage2=5983
Stage1 raw-leg pulses:       0
Stage2 pulses each raw leg:  1600

nominal physical start:      (215.101960,174.394830) mm
nominal physical endpoint:   (249.692833,43.465499) mm
nominal expected chord:      135.421631 mm
candidate physical chord:    129.528716..142.269287 mm
candidate paper margin:      33.976861 mm minimum
candidate joint margin:      10.000000 degrees minimum
integer return closure:      0 mm
```

The physical guard covers Stage1 40.007831..40.190898 and Stage2 39..43
steps/degree. Because 135 times the provisional Stage2 scale is not an
integer, the candidate mapping is anchored at its rounded 135-degree logical
step coordinate:

```text
round(135 * 41.058408) = 5543 steps
physical_psi = 135 + (target_steps - 5543) / candidate_scale
physical_psi_limit = 135 - 33 / candidate_scale
```

All 64 supported final home-release combinations were checked: Stage1 total
release delta 41..48 pulses and Stage2 42..49 pulses. Every approach uses
159..160 Cartesian targets and reaches the same integer start target. The
worst offline quantized approach-line deviation is 0.100778 mm.

## Mechanical Arm Master Procedure

1. Do not run V25 again.
2. Flash `AUTHOR_STAGE2_1600P_CONFIRM_L203_GATED_V26.hex`.
3. Reset and wait for the complete homing and switch-release cycle.
4. Confirm RTT contains build ID
   `AUTHOR_STAGE2_1600P_CONFIRM_L203_GATED_V26`, `lim1=0`, `lim2=0`, and pen
   up.
5. Tape the full A4 sheet flat at four points. Do not hold it by hand.
6. Load `AUTHOR_STAGE2_1600P_CONFIRM_RUN_V26.gcode` in Mechanical Arm Master
   at 115200 8N1.
7. Press Run exactly once, then wait for
   `ok DONE ... pulses=1600 marks=3 stage1_delta=0`.
8. Do not press Run again. Reset and rehome before any later motion.

Optional serial control:

```powershell
.\tools\stage2_confirm_v26_control.ps1 STATUS -PortName COM7
.\tools\stage2_confirm_v26_control.ps1 START -PortName COM7 -ConfirmPaperFixed
.\tools\stage2_confirm_v26_control.ps1 STOP -PortName COM7
```

For immediate mechanical danger, cut motor power rather than relying on a
host application's Stop button.

## Measurement Return

Measure dot center to dot center. A0 is the first start mark, B is the far
mark, and A1 is the return mark at A0.

```text
A0-to-B chord = ___ mm
A0-to-A1 closure = ___ mm
reading uncertainty = plus/minus ___ mm
```

The expected A0-to-B chord is approximately 135.42 mm. If A0 and A1 visually
merge, report the maximum closure-cluster diameter or state that they cannot
be visually separated.

The confirmed Stage2 scale is calculated from measured chord C:

```text
delta_psi_deg = 2 * asin(C / 406) * 180 / pi
confirmed_stage2_steps_per_degree = 1600 / delta_psi_deg
confirmed_psi_limit_deg = 135 - 33 / confirmed_stage2_steps_per_degree
```

## Offline Verification

Run:

```powershell
python .\tools\check_stage2_confirm_v26.py
```

The checker validates the source contract, gate file, every integer approach
and raw-arc pulse, the full continuous candidate-scale rectangle, joint and
paper margins, correct Keil project, clean build, Intel HEX structure,
embedded V26 Build ID, and SHA-256 digest.
