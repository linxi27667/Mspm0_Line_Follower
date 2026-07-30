# PAPER_A4_STANDARD_GCODE_JUNCTION_PLANNER_V32

## Purpose

This firmware keeps the validated V31 coordinate contract, standard G-code
parser, paper map, homing angles, steps per degree, and disabled direction
compensation. It changes only continuous queued motion timing.

## Motion-planner change

- Each queued joint block now stores its maximum entry rate and planned
  entry/exit rates.
- A joint reversal is treated as an exact-stop-style junction at 40 Hz.
- Non-reversing joint-space corners receive progressively lower junction
  rates as the angle increases.
- Every queue append runs a reverse pass for deceleration feasibility and a
  forward pass for acceleration feasibility.
- Each executing block calculates its braking distance from its actual
  current rate and planned exit rate.
- The former rule that decelerated only during the final 40 steps of an empty
  queue is removed.
- Direction/backlash compensation remains disabled.
- AMASS-style low-rate pulse smoothing is not included in this first physical
  validation build.

## Build

- Firmware ID: `PAPER_A4_STANDARD_GCODE_JUNCTION_PLANNER_V32`
- HEX: `keil/PAPER_A4_STANDARD_GCODE_JUNCTION_PLANNER_V32.hex`
- Keil result: `0 Error(s), 0 Warning(s).`
- SHA-256:
  `DE500D8FD1E638C5328553D5E85858442B29ADDCB79485AA7155D60FB3F19A00`

## First physical comparison

1. Flash the V32 HEX and let automatic homing finish.
2. Confirm the startup/stop response contains the V32 firmware ID.
3. Use a fresh sheet of paper.
4. Send the unchanged standard G-code
   `gcode/PAPER_A4_STANDARD_BFONT_6MM_NO_SBOW_VERIFY_GCODE_V68.gcode`,
   one line at a time, waiting for `ok` after every line.
5. Compare against the previous V68 sample, concentrating on horizontal
   stroke length and whether vertical strokes meet their neighboring
   horizontal strokes.

Using the unchanged V68 path keeps font geometry, coordinates, feed, and
paper mapping fixed, so the physical difference isolates the new motion
planner.

## Validation

Run:

```powershell
python tools/check_firmware_junction_planner_v32.py
```

The checker verifies the source contract, clean Keil build, representative
junction-rate decisions, Intel HEX checksum records, embedded firmware ID,
and final HEX digest.
