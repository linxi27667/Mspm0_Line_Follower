"""Measure the photographed 5 mm square against the nearby ruler ticks."""

from pathlib import Path

import cv2
import numpy as np


IMAGE_PATH = Path(
    r"C:\Users\zjl\Documents\xwechat_files\wxid_ggj9bqut1ii122_6820"
    r"\temp\RWTemp\2026-07\9e20f478899dc29eb19741386f9343c8"
    r"\c54b3217fc65a7cc29341793d624f22d.jpg"
)
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "diagnostics"


def _line_from_points(points: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
    vx, vy, x0, y0 = cv2.fitLine(
        points.astype(np.float32), cv2.DIST_L1, 0, 0.01, 0.01
    ).reshape(4)
    tangent = np.array([float(vx), float(vy)])
    tangent /= np.linalg.norm(tangent)
    normal = np.array([-tangent[1], tangent[0]])
    point = np.array([float(x0), float(y0)])
    return normal, float(normal @ point), point


def _intersect(
    first: tuple[np.ndarray, float, np.ndarray],
    second: tuple[np.ndarray, float, np.ndarray],
) -> np.ndarray:
    matrix = np.vstack([first[0], second[0]])
    rhs = np.array([first[1], second[1]])
    return np.linalg.solve(matrix, rhs)


def _fit_edge_bands(
    points: np.ndarray,
    edge_center: tuple[float, float],
    tangent: tuple[float, float],
    half_length: float,
    half_width: float,
    shape_center: np.ndarray,
) -> tuple[
    tuple[np.ndarray, float, np.ndarray],
    tuple[np.ndarray, float, np.ndarray],
    float,
]:
    center = np.array(edge_center)
    direction = np.array(tangent, dtype=float)
    direction /= np.linalg.norm(direction)
    normal = np.array([-direction[1], direction[0]])
    along = (points - center) @ direction
    across = (points - center) @ normal
    selected = points[
        (np.abs(along) <= half_length) & (np.abs(across) <= half_width)
    ]
    projected = ((selected - center) @ normal).astype(np.float32).reshape(-1, 1)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.01)
    _, labels, _ = cv2.kmeans(
        projected,
        2,
        None,
        criteria,
        20,
        cv2.KMEANS_PP_CENTERS,
    )
    fitted = []
    for label in range(2):
        cluster_points = selected[labels.reshape(-1) == label]
        fitted.append(_line_from_points(cluster_points))

    distances = [abs(line[0] @ shape_center - line[1]) for line in fitted]
    outer_index = int(np.argmax(distances))
    inner_index = 1 - outer_index
    separation = abs(distances[outer_index] - distances[inner_index])
    return fitted[outer_index], fitted[inner_index], float(separation)


def main() -> None:
    image = cv2.imread(str(IMAGE_PATH), cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit(f"Cannot read {IMAGE_PATH}")

    # Includes the square and ruler ticks at the same image depth.
    crop = image[675:990, 250:650]
    enlarged = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    black = cv2.inRange(gray, 0, 90)
    black_enlarged = cv2.resize(
        black, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUTPUT_DIR / "workspace_square_photo_crop.png"), enlarged)
    cv2.imwrite(str(OUTPUT_DIR / "workspace_square_photo_threshold.png"), black_enlarged)

    # Hough segments provide an objective local ruler scale and candidate
    # centerlines for the photographed strokes.
    edges = cv2.Canny(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 40, 120)
    ruler_roi = edges[700:1050, 250:540]
    ruler_lines = cv2.HoughLinesP(
        ruler_roi,
        1,
        np.pi / 1800.0,
        threshold=25,
        minLineLength=25,
        maxLineGap=5,
    )
    ruler_candidates: list[tuple[float, float, tuple[int, int, int, int]]] = []
    if ruler_lines is not None:
        for raw in ruler_lines.reshape(-1, 4):
            x1, y1, x2, y2 = (int(value) for value in raw)
            x1 += 250
            x2 += 250
            y1 += 700
            y2 += 700
            dx = x2 - x1
            dy = y2 - y1
            length = float(np.hypot(dx, dy))
            angle = float(np.degrees(np.arctan2(dy, dx)))
            if angle < -90.0:
                angle += 180.0
            if angle > 90.0:
                angle -= 180.0
            if -30.0 <= angle <= -5.0 and 25.0 <= length <= 150.0:
                ruler_candidates.append((angle, length, (x1, y1, x2, y2)))

    print(f"image={image.shape[1]}x{image.shape[0]}")
    print("ruler candidate lines (angle_deg, length_px, endpoints):")
    for item in sorted(ruler_candidates, key=lambda value: value[2][1])[:80]:
        print(f"  {item[0]:7.2f} {item[1]:7.2f} {item[2]}")

    mean_angle = float(np.median([item[0] for item in ruler_candidates]))
    radians = np.radians(mean_angle)
    normal = np.array([-np.sin(radians), np.cos(radians)])
    positions = []
    for _, _, (x1, y1, x2, y2) in ruler_candidates:
        midpoint = np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0])
        positions.append(float(midpoint @ normal))
    positions.sort()
    clusters: list[list[float]] = []
    for position in positions:
        if not clusters or position - float(np.mean(clusters[-1])) > 6.0:
            clusters.append([position])
        else:
            clusters[-1].append(position)
    centers = [float(np.mean(cluster)) for cluster in clusters]
    print(f"ruler mean tick angle={mean_angle:.3f} deg")
    print("ruler projected tick clusters:")
    print("  " + ", ".join(f"{center:.2f}" for center in centers))
    print("ruler cluster spacings:")
    print(
        "  "
        + ", ".join(
            f"{centers[index + 1] - centers[index]:.2f}"
            for index in range(len(centers) - 1)
        )
    )

    shape_gray = cv2.cvtColor(image[680:920, 370:570], cv2.COLOR_BGR2GRAY)
    shape_mask = cv2.inRange(shape_gray, 0, 105)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(shape_mask, 8)
    components = []
    for index in range(1, count):
        x, y, width, height, area = (int(value) for value in stats[index])
        if area >= 10:
            components.append((area, (x + 370, y + 680, width, height)))
    print("shape-region components (area, global bbox):")
    for component in sorted(components, reverse=True)[:20]:
        print(f"  {component}")

    shape_edges = cv2.Canny(shape_gray, 40, 120)
    shape_lines = cv2.HoughLinesP(
        shape_edges,
        1,
        np.pi / 1800.0,
        threshold=12,
        minLineLength=15,
        maxLineGap=6,
    )
    print("shape candidate lines (angle_deg, length_px, endpoints):")
    if shape_lines is not None:
        line_items = []
        for raw in shape_lines.reshape(-1, 4):
            x1, y1, x2, y2 = (int(value) for value in raw)
            x1 += 370
            x2 += 370
            y1 += 680
            y2 += 680
            dx = x2 - x1
            dy = y2 - y1
            length = float(np.hypot(dx, dy))
            angle = float(np.degrees(np.arctan2(dy, dx)))
            if angle < -90.0:
                angle += 180.0
            if angle > 90.0:
                angle -= 180.0
            line_items.append((angle, length, (x1, y1, x2, y2)))
        for item in sorted(line_items, key=lambda value: (-value[1], value[0])):
            print(f"  {item[0]:7.2f} {item[1]:7.2f} {item[2]}")

    largest_label = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    shape_points_yx = np.column_stack(np.nonzero(labels == largest_label))
    shape_points = shape_points_yx[:, ::-1].astype(float) + np.array([370.0, 680.0])

    component_mask = np.uint8(labels == largest_label) * 255
    skeleton = np.zeros_like(component_mask)
    work = component_mask.copy()
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    while cv2.countNonZero(work):
        opened = cv2.morphologyEx(work, cv2.MORPH_OPEN, element)
        skeleton = cv2.bitwise_or(skeleton, cv2.subtract(work, opened))
        work = cv2.erode(work, element)
    cv2.imwrite(
        str(OUTPUT_DIR / "workspace_square_photo_skeleton.png"),
        cv2.resize(skeleton, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST),
    )
    skeleton_points_yx = np.column_stack(np.nonzero(skeleton))
    skeleton_points = (
        skeleton_points_yx[:, ::-1].astype(float) + np.array([370.0, 680.0])
    )
    skeleton_lines = cv2.HoughLinesP(
        skeleton,
        1,
        np.pi / 1800.0,
        threshold=8,
        minLineLength=15,
        maxLineGap=5,
    )
    print("shape skeleton lines (angle_deg, length_px, endpoints):")
    if skeleton_lines is not None:
        skeleton_items = []
        for raw in skeleton_lines.reshape(-1, 4):
            x1, y1, x2, y2 = (int(value) for value in raw)
            x1 += 370
            x2 += 370
            y1 += 680
            y2 += 680
            dx = x2 - x1
            dy = y2 - y1
            length = float(np.hypot(dx, dy))
            angle = float(np.degrees(np.arctan2(dy, dx)))
            if angle < -90.0:
                angle += 180.0
            if angle > 90.0:
                angle -= 180.0
            skeleton_items.append((angle, length, (x1, y1, x2, y2)))
        for item in sorted(skeleton_items, key=lambda value: (-value[1], value[0])):
            print(f"  {item[0]:7.2f} {item[1]:7.2f} {item[2]}")
    shape_center = np.array([463.0, 800.0])
    edge_specs = {
        "top": ((461.0, 758.0), (0.82, -0.57), 31.0, 18.0),
        "right": ((505.0, 780.0), (0.25, 0.97), 28.0, 16.0),
        "bottom": ((477.0, 840.0), (0.81, -0.59), 28.0, 18.0),
        "left": ((432.0, 824.0), (0.33, 0.94), 27.0, 16.0),
    }
    fitted_edges = {
        name: _fit_edge_bands(
            skeleton_points,
            center,
            tangent,
            half_length,
            half_width,
            shape_center,
        )
        for name, (center, tangent, half_length, half_width) in edge_specs.items()
    }
    pixels_per_mm = float(np.median(np.diff(centers)))
    print(f"local ruler scale={pixels_per_mm:.3f} px/mm")
    print("centerline separations:")
    for name, (_, _, separation) in fitted_edges.items():
        print(
            f"  {name:6s}: {separation:6.2f} px = "
            f"{separation / pixels_per_mm:5.2f} mm"
        )

    for band_index, band_name in ((0, "outer"), (1, "inner")):
        lines = {name: value[band_index] for name, value in fitted_edges.items()}
        vertices = {
            "top_left": _intersect(lines["top"], lines["left"]),
            "top_right": _intersect(lines["top"], lines["right"]),
            "bottom_right": _intersect(lines["bottom"], lines["right"]),
            "bottom_left": _intersect(lines["bottom"], lines["left"]),
        }
        lengths = {
            "top": np.linalg.norm(vertices["top_right"] - vertices["top_left"]),
            "right": np.linalg.norm(vertices["bottom_right"] - vertices["top_right"]),
            "bottom": np.linalg.norm(vertices["bottom_right"] - vertices["bottom_left"]),
            "left": np.linalg.norm(vertices["bottom_left"] - vertices["top_left"]),
        }
        print(f"{band_name} fitted vertices:")
        for name, vertex in vertices.items():
            print(f"  {name:12s}: ({vertex[0]:7.2f}, {vertex[1]:7.2f})")
        print(f"{band_name} fitted side lengths:")
        for name, length in lengths.items():
            print(
                f"  {name:6s}: {length:6.2f} px = "
                f"{length / pixels_per_mm:5.2f} mm"
            )

    distance_to_ink = cv2.distanceTransform(255 - component_mask, cv2.DIST_L2, 5)

    def loop_metrics(bits: tuple[int, int, int, int]):
        names = ("top", "right", "bottom", "left")
        lines = {
            name: fitted_edges[name][bit]
            for name, bit in zip(names, bits, strict=True)
        }
        vertices = (
            _intersect(lines["top"], lines["left"]),
            _intersect(lines["top"], lines["right"]),
            _intersect(lines["bottom"], lines["right"]),
            _intersect(lines["bottom"], lines["left"]),
        )
        lengths = np.array(
            [
                np.linalg.norm(vertices[1] - vertices[0]),
                np.linalg.norm(vertices[2] - vertices[1]),
                np.linalg.norm(vertices[2] - vertices[3]),
                np.linalg.norm(vertices[3] - vertices[0]),
            ]
        )
        ink_distances = []
        for vertex in vertices:
            local_x = int(round(vertex[0] - 370.0))
            local_y = int(round(vertex[1] - 680.0))
            if (
                0 <= local_x < distance_to_ink.shape[1]
                and 0 <= local_y < distance_to_ink.shape[0]
            ):
                ink_distances.append(float(distance_to_ink[local_y, local_x]))
            else:
                ink_distances.append(100.0)
        target = 5.0 * pixels_per_mm
        score = (
            float(np.mean(ink_distances))
            + 0.15 * float(np.mean(np.abs(lengths - target)))
            + 0.08 * float(np.std(lengths))
        )
        return score, vertices, lengths, ink_distances

    print("complementary loop pair candidates:")
    loop_pairs = []
    for value in range(8):
        bits = tuple((value >> shift) & 1 for shift in range(4))
        complement = tuple(1 - bit for bit in bits)
        first = loop_metrics(bits)
        second = loop_metrics(complement)
        score = first[0] + second[0]
        loop_pairs.append((score, bits, complement, first, second))
    for score, bits, complement, first, second in sorted(loop_pairs):
        first_mm = first[2] / pixels_per_mm
        second_mm = second[2] / pixels_per_mm
        print(
            f"  score={score:6.2f} bits={bits}/{complement} "
            f"lengths_mm={np.round(first_mm, 2).tolist()} / "
            f"{np.round(second_mm, 2).tolist()} "
            f"ink_dist={np.round(first[3], 1)} / {np.round(second[3], 1)}"
        )

    best = min(loop_pairs, key=lambda item: item[0])
    print("best loop-pair vertices:")
    for label, metrics in (("A", best[3]), ("B", best[4])):
        print(f"  loop {label}:")
        for vertex in metrics[1]:
            print(f"    ({vertex[0]:7.2f}, {vertex[1]:7.2f})")


if __name__ == "__main__":
    main()
