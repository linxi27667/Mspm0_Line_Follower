# V79 concentric-circle test

- Firmware: `PAPER_A4_STANDARD_GCODE_AMASS_PLANNER_V33`
- Paper map: `A4_BASE_QUADRATIC_XSCALE_NO_SBOW_CAL_V8`
- A4 center: X=105.0 mm, Y=148.5 mm
- Diameters, inner to outer: 20, 40, 60, 80 mm
- Direction: CCW; start point: top
- Feed: F300
- Pen-up tangent approach: 5 mm per circle
- Coordinate frame: standard physical A4 paper; no offline prewarp

Safety audit:

- Drawing-sequence minimum joint margin: `40.587734 deg`
- Required minimum margin: `15.0 deg`

Inspect whether all rings share one center, remain circular, close at the top,
and keep uniform radial spacing. Measure the horizontal and vertical diameters
of the D80 ring if it appears oval.
