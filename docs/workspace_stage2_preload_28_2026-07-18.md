# Stage2 Independent Preload Test - 2026-07-18

## Why V2 Did Not Change the Drawing

The complete V2 RTT log confirms the correct firmware ran and completed:

- Mode: `WORKSPACE_MIXED_SCALE_5MM_DIRCOMP_15_21_V2`
- Homing: `ok=1`, final `lim1=0 lim2=0`
- Scale: `spd1=4371 spd2=4880`
- Compensation: `dircomp=1 theta_rev=15 psi_rev=21`
- Completion: `done passes=4 lim1=0 lim2=0 pen=UP`

At each relevant square corner both logical joints reversed together. The two
V2 Stage2 bias terms therefore cancelled from 15/21 to a net six steps. RTT
shows only `bias=0->-6` and `bias=-6->0`. V2 also combined those six steps
with the main synchronized DDA block instead of taking up slack before the
line began. The unchanged paper result is therefore expected and does not
invalidate the measured Stage2 backlash.

## V3 Controlled Variable

Build ID: `WORKSPACE_STAGE2_PRELOAD_28_4P5MM_V3`

- Stage1 reversal cross term: `0`
- Stage2 reversal term: `28 steps` (`0.574 degree`)
- Preload: enabled as a separate Stage2-only block at `100 Hz`
- Main DDA: contains logical Stage1/Stage2 deltas only
- Stage scales remain `43.708318 / 48.8 steps/degree`
- No G-code or UART input is used
- Pass order remains `CW, CW, CCW, CCW`

The state machine keeps logical psi, physical Stage2 motor steps, and bias
separate. On reversal it executes:

1. `PRELOAD`: Stage1=0, Stage2=`+/-28`, logical pose unchanged.
2. `MAIN`: synchronized DDA using only the requested logical step differences.
3. Commit the logical target only after both phases complete.

An incomplete/timeout preload or main phase marks motion unavailable. The test
then raises the pen through its existing failure path.

## Safe Diagnostic Path

A 5 mm square plus the full rigid-motion equivalent of the 28-step preload
cannot retain the previous 0.3 mm safety margin inside the measured
`Y=-5.700..-0.019 mm` character workspace. V3 therefore uses a 4.5 mm square:

- `X=3.00..7.50 mm`
- `Y=-5.36..-0.86 mm`

The complete integer-pulse preload and DDA sequence was simulated, including
all nine preload events. All logical, compensated, joint, and beta checks pass.
Under the conservative assumption that all preload pulses become rigid arm
motion, the complete pen-down envelope is:

- `X=1.001..7.530 mm`
- `Y=-5.408..-0.312 mm`
- Bottom margin: `0.292 mm`
- Top margin: `0.293 mm`

Verifier: `../tools/check_workspace_square_stage2_preload.py`

## Build

Required project:
`keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx`

- Keil: `0 Errors, 0 Warnings`
- HEX: `keil/WORKSPACE_STAGE2_PRELOAD_28_4P5MM_V3.hex`
- SHA-256: `76BF3D5940941BE19D4742FF0D40770590F4A7216EFCE5DA46F11D16EBC0DBE9`
- Intel HEX: 2,961 records, 47,334 data bytes, all checksums valid

The known PA8 SysConfig package-model message remains before compilation. It
does not change the validated generated pin configuration.

## Actual V3 Result - Rejected

The paper result falsified the independent 28-step deadband model. Clockwise
passes became substantially smaller while counter-clockwise passes became
substantially larger. The preload pulses were not absorbed as mechanical dead
travel; a large fraction became real pen-tip motion.

Do not use `WORKSPACE_STAGE2_PRELOAD_28_4P5MM_V3.hex` again. Do not try a
larger value or merely reverse the sign. The earlier direction-dependent
square separation must not be interpreted as a literal 28-step motor deadband.
Likely remaining causes include load-dependent compliance, pen drag, a loose
transmission element, Stage1 behavior, or a direction-dependent Cartesian
mapping error.

## Safe Rollback

Build ID: `WORKSPACE_NO_DIRCOMP_4P5MM_ROLLBACK_V4`

- Direction compensation: disabled
- Theta/psi compensation: `0/0`
- Independent preload: disabled
- Same 4.5 mm coordinates and pass order as V3
- Offline bias states: `[0]`
- Rigid pen-down envelope: `X=2.956..7.530, Y=-5.408..-0.812 mm`
- Keil: `0 Errors, 0 Warnings`
- HEX: `keil/WORKSPACE_NO_DIRCOMP_4P5MM_ROLLBACK_V4.hex`
- SHA-256: `454DD944D17AFF4F58B4571ADD21CA4AB71B55EE7F8979E035C94409AC0D44F8`

The next measurement must isolate real output dead travel with the pen raised
and Stage1/Stage2 tested separately. Continuous pen-down squares are not a
valid way to identify a motor deadband because they mix transmission play,
elastic deflection, pen drag, and Cartesian coupling.
