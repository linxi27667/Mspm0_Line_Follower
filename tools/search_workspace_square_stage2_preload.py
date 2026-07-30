"""Find the safest 5 mm square placement for the 28-step preload test."""

from __future__ import annotations

import contextlib
import io

import check_workspace_square_stage2_preload as check


def envelope_for(x0: float, y_top: float) -> tuple[float, float, float, float]:
    x1 = x0 + 5.0
    y_bottom = y_top - 5.0
    cw = ((x0, y_top), (x1, y_top), (x1, y_bottom), (x0, y_bottom), (x0, y_top))
    ccw = ((x0, y_top), (x0, y_bottom), (x1, y_bottom), (x1, y_top), (x0, y_top))
    state = check.initial_state()
    points: list[tuple[float, float]] = []

    with contextlib.redirect_stdout(io.StringIO()):
        for path in (cw, cw, ccw, ccw):
            state, _, _ = check.run_target(state, path[0], "approach")
            for point in path[1:]:
                state, preload_points, main_points = check.run_target(
                    state, point, "edge"
                )
                points.extend(preload_points)
                points.extend(main_points)

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), max(xs), min(ys), max(ys)


def main() -> None:
    candidates = []
    for x_index in range(20, 112):
        x0 = x_index / 10.0
        for y_index in range(2, 69):
            y_top = -y_index / 100.0
            try:
                envelope = envelope_for(x0, y_top)
            except AssertionError:
                continue
            margins = (
                envelope[0] - check.WORKSPACE_X_MIN,
                check.WORKSPACE_X_MAX - envelope[1],
                envelope[2] - check.WORKSPACE_Y_MIN,
                check.WORKSPACE_Y_MAX - envelope[3],
            )
            minimum_margin = min(margins)
            if minimum_margin >= 0.0:
                candidates.append((minimum_margin, x0, y_top, envelope, margins))

    for minimum_margin, x0, y_top, envelope, margins in sorted(
        candidates, reverse=True
    )[:20]:
        print(
            f"min_margin={minimum_margin:.3f} square=({x0:.2f},{y_top:.2f})"
            f"..({x0 + 5.0:.2f},{y_top - 5.0:.2f}) "
            f"envelope=({envelope[0]:.3f}..{envelope[1]:.3f},"
            f"{envelope[2]:.3f}..{envelope[3]:.3f}) "
            f"margins={tuple(round(value, 3) for value in margins)}"
        )


if __name__ == "__main__":
    main()
