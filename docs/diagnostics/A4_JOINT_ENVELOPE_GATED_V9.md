# A4 Joint Envelope Gated V9

Firmware: `keil/A4_JOINT_ENVELOPE_GATED_V9.hex`

SHA-256:

`2B24AF6921E0E85A14D3A081C7536F6FB324F295D10CF40C0ACC2D60356A3306`

Build result: 0 errors, 0 warnings.

## Safety Contract

- The pen remains at 90 degrees (up) for the entire test.
- G-code is disabled.
- No motion starts until one `NEXT` command is received.
- One `NEXT` starts exactly one predefined waypoint.
- Wait for the RTT `reached=` line and inspect the mechanism before sending
  another `NEXT`.
- Never stream or paste multiple `NEXT` commands.
- `STOP` stops both steppers, invalidates the position, and requires a reboot
  and homing cycle.
- For imminent contact, cable tension, or unexpected motion, cut motor power.
  The UART command is not a substitute for the physical power switch.

Clear the full arm sweep before starting. Keep hands, tools, cables, and loose
paper outside the linkage and gear paths.

## Commands

- `STATUS` or `?`: report state and the next waypoint.
- `NEXT`: execute one waypoint.
- `STOP`: stop immediately; reboot and home before any further motion.

The helper sends exactly one command on COM7:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\a4_probe_command.ps1 -ProbeCommand STATUS
powershell -ExecutionPolicy Bypass -File .\tools\a4_probe_command.ps1 -ProbeCommand NEXT
powershell -ExecutionPolicy Bypass -File .\tools\a4_probe_command.ps1 -ProbeCommand STOP
```

Close Mechanical Arm Master before using the helper so COM7 is not occupied.

## Waypoint Gates

- 1-4: 50 x 35 mm reference rectangle
- 5-8: 75 x 53 mm reference rectangle
- 9-12: 150 x 106 mm reference rectangle
- 13-16: 220 x 155 mm reference rectangle
- 17-20: full 297 x 210 mm A4 reference rectangle
- 21: safe park pose (`theta=20`, `psi=150` degrees)

The reference rectangles are used only to derive safe joint combinations.
They are not yet calibrated to the physical paper corners.

## Expected RTT

At startup:

```text
mode=A4_JOINT_ENVELOPE_GATED_V9 source=UART_GATED command=NEXT pen=UP
A4_JOINT_ENVELOPE_GATED_V9 ready gated=NEXT waypoints=21 no_gcode pen=UP
```

After each accepted move:

```text
[A4PROBE] reached=N/21 name=... theta=... psi=... beta=... lim1=0 lim2=0 pen=UP
```

After waypoint 21:

```text
A4_JOINT_ENVELOPE_GATED_V9 done waypoints=21 lim1=0 lim2=0 pen=UP
```

Stop at the first stage that shows collision risk, cable tension, belt slip,
loss of position, or an unexpected limit state. Record the last successful
waypoint and provide the complete RTT log before continuing.
