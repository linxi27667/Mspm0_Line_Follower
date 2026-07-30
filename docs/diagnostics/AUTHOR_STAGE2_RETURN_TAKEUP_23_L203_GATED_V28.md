# Author Stage2 23-Pulse Return-Takeup Validation V28

Firmware:

`keil/AUTHOR_STAGE2_RETURN_TAKEUP_23_L203_GATED_V28.hex`

Firmware SHA-256:

`F944FC50448C75607D0577F397E3CBA0567BF6C53D800EE31887E11FAB6B3F06`

Mechanical Arm Master gate file:

`gcode/AUTHOR_STAGE2_RETURN_TAKEUP_23_RUN_V28.gcode`

Gate-file SHA-256:

`16518E55E269CF3B8631D1223D5BEF19DB5B499BF55D4804EB8B0F61B84ED875`

Build result: 0 errors and 0 warnings with the required project
`keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx`. The known PA8
SysConfig package-model message occurs before the successful compilation and
does not change the generated pin configuration.

## Purpose

V27 measured `AA1=BB1=CC1=DD1=2 mm`, with every return mark displaced toward
E. On an L2=203 mm circle this is 0.564480 degree or 22.645 pulses at the
accepted Stage2 scale. V28 rounds this to 23 pulses and tests it in isolation.

This is not production direction compensation. The global direction
compensation and independent preload switches remain disabled. Stage1 is
locked during the raw test, every move is pen-up, and the pen only makes nine
stationary dots.

## Active Calibration

```text
L1 / L2:            205 / 203 mm
Stage1 scale:       40.099216 steps/degree
Stage2 scale:       40.115790 steps/degree
theta limit:        -0.773082 degrees
psi limit:          134.177381 degrees
machine offset:     (-129,+128) mm
direction comp:     disabled
independent preload: disabled
```

## Sequence

The logical labels remain:

```text
A -> B -> C -> D -> E -> D1 -> C1 -> B1 -> A1
0   400  800 1200 1600  1200   800   400    0 logical pulses
```

The raw Stage2 motor offsets are:

```text
0, 400, 800, 1200, 1600, 1177, 777, 377, -23 pulses
```

Therefore the eight raw legs are:

```text
400, 400, 400, 400, 423, 400, 400, 400 pulses
```

Only the first return leg contains the 23 extra pulses. The offset is then
retained for all remaining return marks. Stage1 must emit zero pulses and the
Stage2 raw total must be exactly 3223 pulses.

## Offline Verification

The verifier checks all 64 supported final home-release combinations, the
complete integer sequence, the full 39..43 Stage2 candidate-scale range, the
correct Keil project, the gate file, and the generated HEX:

```powershell
python .\tools\check_stage2_return_takeup_v28.py
```

Verified results:

```text
quantized start steps:          Stage1=2668, Stage2=5880
start coordinate:               (216.798,171.867) mm
Stage1 raw test delta:          0 pulses
Stage2 raw test total:          3223 pulses
final Stage2 motor offset:      -23 pulses
maximum approach deviation:     0.105294 mm
minimum candidate paper margin: 31.848045 mm
minimum candidate joint margin: 10.023256 degrees
23-pulse rigid displacement:    2.031347 mm
predicted residual vs 2 mm:     0.031347 mm
```

## Run Procedure

1. Do not run V25, V26, or V27 again.
2. Flash `AUTHOR_STAGE2_RETURN_TAKEUP_23_L203_GATED_V28.hex`.
3. Reset and wait for the complete home and switch-release cycle.
4. Confirm the RTT build ID is
   `AUTHOR_STAGE2_RETURN_TAKEUP_23_L203_GATED_V28`, both limits are clear, the
   pen is up, and UART state is `WAIT_RUN`.
5. Use a blank A4 sheet and tape it flat. Do not reuse the V27 dots and do not
   hold the sheet by hand.
6. Load `AUTHOR_STAGE2_RETURN_TAKEUP_23_RUN_V28.gcode` in Mechanical Arm
   Master at 115200 8N1 and press Run exactly once.
7. Wait for `ok DONE` with `takeup=23`, `raw_total=3223`, `marks=9`, and
   `stage1_delta=0`.
8. Do not press Run again. Reset and rehome before any later motion.

For immediate mechanical danger, cut motor power rather than relying on the
host application's Stop button.

## Measurements To Return

Measure direct dot-center separation and side for:

```text
AA1 = ___ mm, return point toward A/E
BB1 = ___ mm, return point toward A/E
CC1 = ___ mm, return point toward A/E
DD1 = ___ mm, return point toward A/E
```

If a pair visually overlaps, report 0 or its maximum visible cluster diameter.
The intended result is overlap within approximately 0.5 mm. A residual on the
E side means 23 pulses are insufficient; a residual on the A side means they
are excessive. Even a successful V28 does not by itself authorize production
compensation because continuous pen drag and two-axis Cartesian motion remain
separate variables.

## Backup

`backups/AUTHOR_STAGE2_RETURN_TAKEUP_23_L203_GATED_V28_20260720.zip`

SHA-256:

`2BC78026469BE78E28CA312F704A8EF350C00AACDE474352CCD88DB186CB191C`
