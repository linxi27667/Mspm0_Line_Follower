# Author M700 V15 Calibration Result - 2026-07-19

Firmware:

`keil/AUTHOR_M700_HOME_CAL_GATED_V15.hex`

## Measured Result

The author 0/135 pose was established manually with both switches clear. V15
then performed one absolute search and two repeat approaches, all pen-up at
100 pulses/second.

```text
initial_s1=31 initial_s2=33
theta_limit=-0.709247 deg
psi_limit=134.323770 deg
repeat1_s1=30 repeat1_s2=33
repeat2_s1=30 repeat2_s2=33
diff_s1=0 diff_s2=0 tolerance=4
repeat_ok=1 calibration_valid=1
lim1=0 lim2=0 pen=UP
author_a4_candidate=0
```

The final release distances recorded by RTT were 52 Stage1 pulses and 57
Stage2 pulses. They correspond to the post-calibration pose:

```text
theta_home=0.480458 deg
psi_home=135.491803 deg
```

## Full Author A4 Decision

The current official firmware contract is the unshifted author work frame:

```text
machine = work + (-129, +128) mm
paper X=0..297 mm
paper Y=0..210 mm
```

With one degree of limit clearance, full A4 requires:

```text
theta_limit <= -19.22 deg
psi_limit <= 93.36 deg
```

The fixed switches instead measured -0.71 and 134.32 degrees. The missing
joint envelope is therefore:

```text
Stage1: 18.51 deg, approximately 809 pulses
Stage2: 40.96 deg, approximately 1999 pulses
```

Consequently, full unshifted author A4 is physically unavailable without
moving the switches or changing the installation geometry. Increasing a
software range cannot make those positions safe.

## Safe Sub-Rectangles

`tools/analyze_author_a4_measured_limits.py` checks the official frame using
integer-pulse IK, joint limits, link angle, and a dense 0.1 mm verification
grid.

Theoretical boundary, with 0.25 degrees beyond the one-degree hard clearance:

```text
maximum A4-ratio rectangle:
X=111.5..297.0 mm
Y=0.0..131.0 mm
size=185.5x131.0 mm
minimum extra margin=0.352 deg
```

Recommended operating boundary, with an additional 2.0-degree margin to
cover measured reversal backlash and setup uncertainty:

```text
maximum A4-ratio rectangle:
X=116.0..296.5 mm
Y=0.0..127.5 mm
size=180.5x127.5 mm
minimum extra margin=2.012 deg
```

This is a sub-region of the author's A4 coordinate system, not a translated
or redefined A4 origin. No motion firmware for this region has been enabled
by V15. The follow-up `AUTHOR_SAFE_170X120_PENUP_GATED_V16` firmware uses an
inset 170x120 mm rectangle and remains UART-gated and pen-up, starting with
small +X and +Y probes before visiting any outer corner.
