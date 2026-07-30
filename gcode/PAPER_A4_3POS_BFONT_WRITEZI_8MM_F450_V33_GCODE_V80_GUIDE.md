# V80 8 mm writing speed test at F450

- Firmware: `PAPER_A4_STANDARD_GCODE_AMASS_PLANNER_V33`
- Paper map: `A4_BASE_QUADRATIC_XSCALE_NO_SBOW_CAL_V8`
- Content: three copies of WRITE ZI at left, middle, and right
- Font: pinned B gfont with unmodified source paths
- Visible height: 8 mm
- Feed: F450
- Pen-up tangent approach: 5 mm
- Reference: `PAPER_A4_3POS_BFONT_WRITEZI_8MM_V33_CAL_GCODE_V77` at F300
- Geometry and pen commands: byte-for-byte equivalent after filtering comments and feed

Safety audit:

- Writing-sequence minimum joint margin: `32.420046 deg`
- Required minimum margin: `15.0 deg`

Compare against the V77 result for corner overshoot, open joins, missing strokes,
position drift, and any difference between the left, middle, and right copies.
