# Workspace Mixed-Scale 5 mm Square - 2026-07-18

## Baseline Result

Firmware: `WORKSPACE_MIXED_SCALE_5MM_V1`

- Stage1: `43.708318 steps/degree`
- Stage2: `48.8 steps/degree`
- Direction compensation: disabled
- Path: identical 5 x 5 mm square, `CW, CW, CCW, CCW`
- The visible RTT tail reached `done passes=4` and showed `lim1=0`; the full
  startup-to-done text was not exported, so retain the next run as a log file.

The paper photo was calibrated against the adjacent 1 mm ruler marks. The
local scale is approximately `16.93 px/mm`; photo perspective and stroke width
limit absolute measurements to roughly `+/-0.2..0.4 mm`.

- Same-direction repeats merge into one stroke: resolvable error `<=0.2 mm`.
- CW/CCW centerline separation along edge middles: about `0.27..0.78 mm`.
- Maximum CW/CCW separation: about `1.2..1.3 mm` at the lower-left photo corner.
- The upper-right photo corner has the clearest turn hook; the start/closure
  corner closes within approximately one stroke width.
- Two direction-dependent fitted edge sets, listed as photo top/right/bottom/left:
  - Set A: `5.62, 5.56, 5.96, 5.34 mm`
  - Set B: `5.81, 5.56, 5.06, 5.84 mm`

The stable same-direction overlap and stable opposite-direction split identify
reversal hysteresis/backlash as the primary error. They do not support random
step loss as the primary cause. Keep the two joint scales frozen for the next
test.

Diagnostic images:

- `diagnostics/workspace_square_photo_crop.png`
- `diagnostics/workspace_square_photo_threshold.png`
- `diagnostics/workspace_square_photo_skeleton.png`

Measurement tool: `../tools/analyze_square_photo.py`

## Next Firmware

Firmware: `WORKSPACE_MIXED_SCALE_5MM_DIRCOMP_15_21_V2`

Only the already measured Stage2 hysteresis model is enabled:

- Stage1-reversal cross term: `15 Stage2 steps`
- Stage2 motor reversal term: `21 Stage2 steps`
- Bias guard: `64 steps`
- Coordinates, pass order, feed, home, joint scales, geometry, servo angles,
  and limit-switch behavior are unchanged.

The exact integer-step sequence was checked offline with the MCU direction
history and compensation algorithm. This square reaches only bias states
`-6` and `0`. All logical and compensated theta/psi/beta targets pass. Under
the conservative rigid-link assumption that every compensation step becomes
real motion, the complete pen-down DDA envelope is:

- `X=5.018..10.552 mm`
- `Y=-5.339..-0.258 mm`

This remains inside the measured character workspace
`X=0..16.611 mm, Y=-5.700..-0.019 mm`.

Build result from the required Keil project: `0 Errors, 0 Warnings`.

- HEX: `keil/WORKSPACE_MIXED_SCALE_5MM_DIRCOMP_15_21_V2.hex`
- SHA-256: `623770A78BFFC71F7E391D57906848CD52602CAAEDE6B4B3FA71696C7EA65513`
- Intel HEX: 2,862 records, 45,742 data bytes, all checksums valid, valid EOF.

Offline verifier: `../tools/check_workspace_square_dircomp.py`
