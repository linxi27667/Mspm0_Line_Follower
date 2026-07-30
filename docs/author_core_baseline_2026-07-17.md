# Author Core Migration Baseline

Date: 2026-07-17

Correct Keil project:

`keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx`

Pre-migration HEX:

`keil/Objects/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.hex`

SHA-256:

`DEAA8A43DE10ECA73E806A85484F4215DD5F87CE18403145EAAE1E830FA6706F`

The existing `MID/Src/mid_scara.c` already matches the author's absolute
theta/psi inverse equations in `DrawBot-ramps-main/grbl-scara-ramps/scara.c`.
The first migration step therefore enables the author's native work frame
without the measured 2x2 paper matrix. Homing, limits, UART, servo control,
Cartesian 1 mm safety segmentation, and synchronized DDA stepping remain
unchanged.

Author-core HEX SHA-256:

`DAB478D53C0DA5B45A76001C8F7C5DB2CD306DBD8665E10C808789DA5B90FF8D`

## Joint geometry calibration V2

Measured numbered Stage1 taps relative to A1:

`A1=(0,0), A2=(0,7.5), A3=(0.5,15.5), A4=(1,23.5) mm`

Combined with the Stage2 B taps, the fixed-200 mm link fit produced:

- Stage1: 43.708318 steps/degree, RMS point residual 0.181 mm
- Stage2: 50.917449 steps/degree, RMS point residual 0.596 mm
- Physical home theta: -16.887811 degrees
- Physical home psi: 108.286506 degrees
- Physical home beta: 125.174317 degrees
- A1-anchored work offset: X=-126.174610 mm, Y=186.754553 mm

## Author parameter baseline V3

The V2 values above were fitted together from pen-tip Cartesian points. That
fit mixed home angle, work offset, angular step scale, backlash, and linkage
error into one result. It is retained only as a rollback configuration.

The active diagnostic baseline now uses the original DrawBot defaults from
`grbl-scara-ramps/defaults_scara.h` and `grbl-scara-ramps/scara.h`:

- L1/L2: 200/200 mm
- Work offset: X=-135 mm, Y=105 mm
- Stage1/Stage2: 48.8/48.8 steps per degree
- Limit angles: theta=-45.43 degrees, psi=95.67 degrees
- Native absolute theta/psi inverse kinematics
- Paper 2x2 map disabled
- Direction compensation disabled

The MSPM0 GPIO, limit-switch homing, servo, UART, 1 mm Cartesian safety
segmentation, and synchronized step generation remain in use because the
author's AVR/RAMPS register-level drivers cannot run on MSPM0.

The active hard-coded test draws the identical 20 x 20 mm square at
`(32,-26)..(52,-46)` twice clockwise and twice counter-clockwise. This removes
G-code and position/size differences from the direction comparison while also
checking same-direction repeatability.

Offline path check, including the move from nominal home to the first point:

- 341 Cartesian segments checked
- theta: -43.947 to -29.768 degrees
- psi: 97.237 to 116.939 degrees
- out-of-limit points: 0

Author-baseline HEX:

`keil/Objects/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.hex`

SHA-256:

`9496B48646A12D08EA8948E3B17BC063DB06E674D7353C33750A32016628AD8E`
