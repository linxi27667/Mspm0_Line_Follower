# Direction Hysteresis Compensation - 2026-07-17

## Evidence

Diagnostic 20 was run twice without moving the paper or re-homing. All eight
points repeated within 0.5 mm, ruling out cumulative step loss as the primary
cause.

Measured swapped-direction row vectors:

- Stage1 block: bottom `(5, 1)` mm, top `(8.5, 1)` mm
- Stage2 block: bottom `(7.5, -1)` mm, top `(5, 1.3)` mm

The direction-dependent spans are `(1.75, 0)` mm for a Stage1 direction
change and `(-1.25, 1.15)` mm for a Stage2 direction change. Diagnostics 19
and 20 consistently attribute the dominant error to Stage2 linkage
hysteresis.

## Conservative Model

The first firmware experiment compensates Stage2 only:

- A Stage1 logical direction reversal changes the Stage2 motor bias by 30
  steps in the measured cross-coupling direction.
- Any actual Stage2 motor direction reversal adds 28 take-up steps in the new
  motor direction.
- Stage1 self-compensation is intentionally disabled because its measured
  diagonal term changed sign between diagnostics 19 and 20.

Logical theta/psi positions remain separate from the Stage2 motor position and
bias. Zero-step segments do not change direction history. The final homing
pull-off establishes both direction states as logical positive.

The compensated, quantized theta/psi path is checked again against joint and
beta limits before every DDA segment. The configured bias guard is 64 steps;
the reachable states from the real homing state are `-28`, `0`, `2`, and `30`
steps.

## Verification

- Correct Keil project: `keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx`
- Compile/link/HEX: 0 errors, 0 warnings
- Candidate parameters: `theta_rev=15`, `stage2_motor_rev=21`
- Test 20: 186 two-level segmented IK points, bias -21..15 steps, no safety errors
- 262-line character file: 264 two-level segmented IK points, bias -21..15 steps, no safety errors
- Modal axis-only regression: 5 XY motions checked, including inherited G0/G1
- G-code serial HEX SHA-256: `C301E9EC7B0DC0AD2F0155028A4AE9D53211A41E083A36B7F2480D9F295685E3`
- Direct nested-square HEX SHA-256: `504DF539997AA15A0332B1C3C5106CD93D1C14F09B2E24487FAB6FFF74F3E514`

## First Compensated Result

With the initial `theta_rev=30`, `stage2_motor_rev=28` build, diagnostic 20
measured:

- Stage1 block: bottom `(7, -1)` mm, top `(4, 0)` mm
- Stage2 block: bottom `(6, 0)` mm, top `(4, 0)` mm

Stage2 Y-direction closure improved, but the Stage1 block changed from
under-compensation to over-compensation. Because the controlled Stage1 paths
also reverse the actual Stage2 motor, this run cannot separate the 30-step
and 28-step contributions by itself.

Float32 simulation of the exact UART 20 mm and motion 1 mm segmentation shows
that the eight tap biases were `0, 30, 30, -28, 30, -28, -28, 0`. The four
measured row vectors therefore identify `C`, `C+D`, `C+D`, and `D`
respectively, where `C` is the theta-reversal cross term and `D` is the actual
Stage2 reversal term.

A least-squares fit that minimizes the top/bottom direction difference in
each block gives `C=15.40`, `D=21.13`. The next build uses the conservative
integer values `theta_rev=15`, `stage2_motor_rev=21`. Its reachable bias states
are `-21`, `-6`, `0`, and `15` steps.

The `15/21` validation run measured:

- Stage1 block: bottom `(6, -2)` mm, top `(5.5, -1)` mm
- Stage2 block: bottom `(6, -1)` mm, top `(5, 0)` mm

The top/bottom residuals are now `(0.5, -1)` mm and `(1, -1)` mm, down from
multi-millimetre direction errors. Their similar residual direction in both
spatial blocks indicates static paper mapping and measurement resolution are
now comparable to the remaining hysteresis. Freeze `15/21` for the next
continuous-stroke grid instead of fitting another bias pair to these rounded
measurements.

The existing SysConfig pre-build still reports that PA8 is unavailable in its
incorrect VSSOP-28 package model. This build reuses the already validated
generated PA8/TIMA0 configuration. The warning does not affect this motion-only
experiment, but SysConfig must be repaired before future pinmux regeneration.

## Next Test

The active mode is `WRITER_TEST_MODE_NESTED_SQUARE_DIRECT`; it bypasses UART
and G-code completely. After homing it draws exactly one pass of each path:

- Outer clockwise: `(4,-2) -> (24,-2) -> (24,-22) -> (4,-22) -> (4,-2)`
- Inner counter-clockwise: `(9,-7) -> (9,-17) -> (19,-17) -> (19,-7) -> (9,-7)`

Both use `F200`, with 5 mm nominal clearance between frames. Put fresh paper
in place before flashing because the test starts automatically after reset and
homing. Measure all four corners, edge straightness, and both closure vectors.
