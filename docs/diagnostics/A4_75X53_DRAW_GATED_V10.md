# A4 75 x 53 Draw Gated V10

Firmware: `keil/A4_75X53_DRAW_GATED_V10.hex`

SHA-256:

`A51DC66C12F11D66722E948424284027A1E704BE2E08E6696F185AAF2C207470`

Build result: 0 errors, 0 warnings. The known PA8 SysConfig package-model
message appears before the successful compile and link.

## Purpose

This diagnostic connects V9 reference points 5, 6, 7, and 8 as one closed
75 x 53 mm rectangle:

`P5 -> P6 -> P7 -> P8 -> P5`

It is the same rotated reference rectangle defined by the V9 probe points; it
is not intended to be aligned with the paper X/Y axes yet.

## Motion Contract

- Startup and homing always hold the pen at 90 degrees (up).
- `NEXT` only positions the pen at P5 while it is up.
- `DRAW` is rejected until P5 has been reached and both limits are clear.
- Accepted `DRAW` moves the servo to 0 degrees, waits 700 ms, draws the four
  edges, returns to P5, raises the pen to 90 degrees, and waits 700 ms.
- The 256 draw segments use 257 precomputed absolute joint-step targets at
  approximately 1 mm Cartesian spacing.
- G-code and Mechanical Arm Master commands are disabled in this firmware.
- Direction compensation is disabled.
- `STOP` raises the pen, stops both motors, invalidates position, and requires
  reboot plus homing.

For imminent contact, cable tension, or unexpected motion, cut motor power.
Do not rely on the UART command as a substitute for the physical power switch.

## Commands

- `STATUS` or `?`: inspect state, next action, limits, and pen state.
- `NEXT`: move to P5 with the pen up; accepted only in `WAIT_NEXT`.
- `DRAW`: draw and close P5-P6-P7-P8-P5; accepted only in `WAIT_DRAW`.
- `STOP`: emergency stop and mandatory rehome.

Close Mechanical Arm Master so COM7 is free. The one-command helper is:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\a4_probe_command.ps1 -ProbeCommand STATUS
powershell -ExecutionPolicy Bypass -File .\tools\a4_probe_command.ps1 -ProbeCommand NEXT
powershell -ExecutionPolicy Bypass -File .\tools\a4_probe_command.ps1 -ProbeCommand DRAW
powershell -ExecutionPolicy Bypass -File .\tools\a4_probe_command.ps1 -ProbeCommand STOP
```

Never paste or batch multiple commands.

## Required Sequence

1. Flash `A4_75X53_DRAW_GATED_V10.hex` and allow homing to finish.
2. Confirm the startup line contains `A4_75X53_DRAW_GATED_V10`,
   `gate1=NEXT`, `gate2=DRAW`, `lim1=0`, `lim2=0`, and `pen=UP`.
3. Send one `STATUS`; require `state=WAIT_NEXT action=NEXT`.
4. Send one `NEXT` and wait for `positioned=P5_TL ... wait=DRAW`.
5. Send one `STATUS`; require `state=WAIT_DRAW action=DRAW`, both limits 0,
   and `pen=UP`.
6. Clear the full linkage sweep and keep the power switch accessible.
7. Send one `DRAW`; do not send another command while drawing.
8. Require all four corner logs and the final `done` log below.

Expected completion:

```text
[A4DRAW] reached=P6_TR point=75/256 ... lim1=0 lim2=0 pen=DOWN
[A4DRAW] reached=P7_BR point=128/256 ... lim1=0 lim2=0 pen=DOWN
[A4DRAW] reached=P8_BL point=203/256 ... lim1=0 lim2=0 pen=DOWN
[A4DRAW] reached=P5_TL_CLOSE point=256/256 ... lim1=0 lim2=0 pen=DOWN
[A4DRAW] A4_75X53_DRAW_GATED_V10 done ... lim1=0 lim2=0 pen=UP
```

## Offline Verification

Run:

```powershell
python .\tools\check_a4_75x53_draw.py
```

Verified results:

- Offline targets: 257
- Draw segments: 256
- Approach master pulses: 531 minimum-home model
- Draw master pulses: 4,225
- Joint range: theta 13.178..44.202 degrees
- Joint range: psi 142.561..174.426 degrees
- Relative angle beta: 117.381..144.820 degrees
- Maximum integer-pulse line deviation per edge:
  0.0905, 0.0501, 0.0836, 0.0787 mm
- Generated path header matches the checker output
- Intel HEX: 2,964 records, 47,368 data bytes, valid checksums and one EOF

This is still a staged workspace diagnostic, not the final A4 G-code writing
firmware.
