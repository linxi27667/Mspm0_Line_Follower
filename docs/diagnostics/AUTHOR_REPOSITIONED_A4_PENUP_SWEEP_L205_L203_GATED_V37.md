# AUTHOR_REPOSITIONED_A4_PENUP_SWEEP_L205_L203_GATED_V37

Date: 2026-07-21

## Purpose

V37 is a pen-up-only hardware clearance test for the repositioned landscape-A4
layout.  It does not write text and it does not enable ordinary G-code.

## Paper contract

- Landscape A4: 297 mm left-to-right, 210 mm bottom-to-top.
- Paper origin: lower-left; +X right, +Y up.
- Command mapping: `command_xy = paper_xy + (139,-68) mm`.
- The existing M801 machine target remains `(150,20) mm`.
- Draw the paper alignment cross at `(11,88) mm`: 11 mm from the left edge and
  88 mm from the bottom edge.
- After M801 finishes, move and fix the paper so that this cross is under the
  raised pen tip.
- Planned text/sweep inset: paper `[15,15]..[282,195] mm`.

## Offline kinematic audit

The full 15 mm inset rectangle was sampled at every integer millimetre, for
48,508 points.  The planned one-page diary integer-pulse path was also sampled
at every emitted DDA pulse, for 266,680 pulse positions.

Full inset rectangle:

- Combined joint/pose margin: at least `11.506315 deg`.
- Elbow angle beta: `36.319806..157.655766 deg`.
- Distance from beta=0 singularity: at least `36.319806 deg`.
- Distance from beta=180 singularity: at least `22.344234 deg`.
- Inner radial-singularity gap: at least `77.077181 mm`.
- Outer radial-singularity gap: at least `20.321816 mm`.
- Minimum `abs(sin(beta))`: `0.380170340` (never zero).
- Maximum Jacobian condition number: `5.063563`.

Planned one-page diary pulse path:

- Combined joint/pose margin: at least `12.495137 deg`.
- Distance from beta=0/180 singularities: at least
  `49.633281/24.263843 deg`.
- Inner/outer radial-singularity gaps: at least
  `83.768912/37.675557 mm`.
- Minimum `abs(sin(beta))`: `0.410939124`.
- Maximum Jacobian condition number: `4.652182`.

Conclusion: under the current `L1=205 mm`, `L2=203 mm`, offset, joint-limit and
integer-pulse model, the selected A4 inset does not touch an IK dead zone,
radial singularity, Jacobian singularity, or joint hard limit.

This conclusion does not prove physical clearance from the table, paper clips,
pen holder, cables or self-collision because those bodies are not represented
in the kinematic model.  V37 is the required pen-up physical-clearance test.

## V37 sweep

- Gate sequence: M801 ALIGN, then M808 PENUP_SWEEP.
- Sweep targets: 11.
- Pen-down targets: 0.
- The executor contains no `App_Servo_Pen_Down` call.
- Sweep rows visit the bottom, middle and top of the 15 mm inset, then return to
  the alignment cross.
- Maximum target-to-target span: `161.003882 mm`.
- Integer-pulse samples: 16,194.
- Minimum sweep joint margin: `11.506315 deg`.
- Maximum DDA line deviation: `0.100418 mm`.
- Maximum quantized endpoint error: `0.043446 mm`.
- Conservative inset after DDA deviation: `14.899582 mm`.
- Path CRC32: `A36AE1A5`.

The home-release-to-M801 approach has a minimum hard-limit margin of
`0.022463 deg`.  This is the existing switch-release start geometry, not the A4
sweep region and not a singularity.  The paper is positioned only after M801.

## Build and artifacts

- Correct Keil project:
  `keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx`
- Build: `0 Error(s), 0 Warning(s)`.
- HEX: `keil/AUTHOR_REPOSITIONED_A4_PENUP_SWEEP_L205_L203_GATED_V37.hex`
- HEX SHA-256:
  `499E33BC5D0705BDC36199776040A0336914156A69CCD2C087BF7F27410F3B38`
- ALIGN gate:
  `gcode/AUTHOR_REPOSITIONED_A4_PENUP_ALIGN_RUN_V37.gcode`
- SWEEP gate:
  `gcode/AUTHOR_REPOSITIONED_A4_PENUP_SWEEP_RUN_V37.gcode`
- Checker: `tools/check_author_repositioned_a4_penup_v37.py`
- Full-area singularity report:
  `docs/diagnostics/DIARY_NOTEBOOK_REPOSITIONED_A4_SINGULARITY_AUDIT_20260721.json`

## Hardware procedure

1. Keep the pen raised; removing the pen for the first sweep is acceptable.
2. Flash the V37 HEX and let the normal homing sequence finish.
3. Send only the V37 ALIGN gate.  Wait for `STAGE_DONE`, state `WAIT_SWEEP`.
4. Place/fix landscape A4 so its `(11,88) mm` cross is exactly under the raised
   pen tip.  Check arm, cable and fixture clearance by sight.
5. Send only the V37 PENUP_SWEEP gate and watch the entire motion.  Use `STOP`
   or the physical emergency stop immediately if any real obstacle is close.
6. Report whether all three rows and the return to the cross completed without
   collision, limit activation, abnormal sound or lost motion.

Do not send M808 before positioning the paper.  Do not run `2.0.gcode`, do not
switch to unrestricted `GCODE_SERIAL`, and do not use a V36 TEXT gate with this
firmware.
