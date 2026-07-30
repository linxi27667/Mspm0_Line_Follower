# Author Safe 170x120 Draw Gated V18

Firmware:

`keil/AUTHOR_SAFE_170X120_DRAW_GATED_V18.hex`

SHA-256:

`5C42FA22CAD66C439F25F368B8589F6B4DB9C9B9DEA6570F593ADD86BBBE3295`

Build result: 0 errors, 0 warnings with the required project
`keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx`. The known PA8
SysConfig package-model message appears before the successful compile, link,
and HEX generation.

V18 has been built and verified offline. It has not been flashed by this
build procedure.

## Fixed Contract

- Link lengths: L1=200 mm and L2=200 mm.
- Effective author-frame offset: (-129,+128) mm.
- Paper axes: +X right and +Y up.
- Measured electrical limits: theta=-0.709247 degrees and
  psi=134.323770 degrees.
- Joint scales: Stage1=43.708318 and Stage2=48.8 steps/degree.
- Direction compensation: disabled.
- Pen: 0 degrees down and 90 degrees up.
- Rectangle: X=120..290 mm and Y=5..125 mm, or 170 x 120 mm.
- Full A4 remains disabled.

## Safety State Machine

1. Startup raises the pen and performs the normal two-speed limit home.
2. The firmware waits in `WAIT_NEXT`; no rectangle motion starts by itself.
3. One exact `NEXT` moves directly to `RECT_BL=(120,5)` with the pen up.
4. The firmware waits in `WAIT_DRAW`; no pen-down action starts by itself.
5. One exact `DRAW_CW` or `DRAW_CCW` lowers the pen, waits 700 ms, draws
   exactly one closed rectangle, raises the pen, waits 700 ms, and enters
   `DONE`.
6. `DONE`, `STOPPED`, and `ERROR` cannot start another rectangle. Reset and
   rehome are required before the other direction is tested.
7. `LOOP`, plain `DRAW`, `G...`, `M...`, and every unsupported command are
   rejected.
8. `STOP`, an active limit, a rejected path, a timeout, or an incomplete
   endpoint raises the pen, stops motion, invalidates position, and requires
   reset plus rehome.

For imminent contact, cable tension, or unexpected movement, cut motor power.
UART `STOP` is not a substitute for the physical power switch.

## Direction Definition

With +X right and +Y up:

```text
DRAW_CW:  BL -> TL -> TR -> BR -> BL
DRAW_CCW: BL -> BR -> TR -> TL -> BL
```

Both directions begin and close at the same integer joint target:
Stage1=682 and Stage2=7645 steps.

## Commands

Close Mechanical Arm Master so COM7 is free. Never paste or batch multiple
commands.

Read-only status and emergency stop:

```powershell
.\tools\author_rect_draw_command.ps1 STATUS
.\tools\author_rect_draw_command.ps1 STOP
```

Pen-up approach:

```powershell
.\tools\author_rect_draw_command.ps1 NEXT -ConfirmPenUpClearance
```

Choose exactly one direction after `STATUS` reports `state=WAIT_DRAW`,
`target=RECT_BL`, `lim1=0`, `lim2=0`, and `pen=UP`:

```powershell
.\tools\author_rect_draw_command.ps1 DRAW_CW -ConfirmSinglePassPenDown
.\tools\author_rect_draw_command.ps1 DRAW_CCW -ConfirmSinglePassPenDown
```

The helper sends a read-only `STATUS` preflight before `NEXT`, `DRAW_CW`, or
`DRAW_CCW`. It refuses motion unless the build ID, state, limits, pen state,
and draw start point match V18.

## Required Physical Sequence

Run CW and CCW as separate experiments:

1. Flash V18, reset, and allow homing to finish.
2. Require build ID `AUTHOR_SAFE_170X120_DRAW_GATED_V18` and send `STATUS`.
3. Require `state=WAIT_NEXT`, both limits clear, and `pen=UP`.
4. Clear the full linkage and cable sweep, then send one confirmed `NEXT`.
5. Wait for `POSITIONED ... state=WAIT_DRAW`; send `STATUS` again.
6. Place paper and confirm the BL pen contact point, four-edge sweep, cable
   path, and physical power-switch access.
7. Send exactly one confirmed direction command. Send no other command while
   drawing unless emergency `STOP` is required.
8. Require all four `reached=` logs followed by `ok DONE ... edges=4 ...
   pen=UP`.
9. Power-cycle or reset and rehome before testing the opposite direction.

## Measurement Record

For each independent CW and CCW sheet, record:

| Measurement | Nominal |
| --- | ---: |
| Bottom edge | 170.000 mm |
| Right edge | 120.000 mm |
| Top edge | 170.000 mm |
| Left edge | 120.000 mm |
| BL-to-TR diagonal | 208.087 mm |
| BR-to-TL diagonal | 208.087 mm |
| Start-to-close error | 0.000 mm |

Also overlay or register the two sheets in the same coordinate convention and
record corresponding-corner CW/CCW separation. Keep raw measurements; do not
infer A4 reachability from this rectangle alone.

## Offline Verification

Run:

```powershell
python .\tools\check_author_rect_draw_v18.py
```

Verified results:

```text
CW:  edge segments 120,170,120,170; 580 IK targets; 7550 master pulses
     minimum joint margin 3.364751 degrees
     maximum integer-pulse line deviation 0.083374 mm
CCW: edge segments 170,120,170,120; 580 IK targets; 7546 master pulses
     minimum joint margin 3.364751 degrees
     maximum integer-pulse line deviation 0.085499 mm
Both: integer-step closure error (Stage1,Stage2)=(0,0)
```

The offline checker also validates the measured-limit approach path, source
contract, host preflight gates, correct Keil project, clean build, Intel HEX
checksums, and embedded V18 build ID.
