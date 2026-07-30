"""Track the V17 pen-axis tip and fit its four-sided video trajectory."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import cv2
import numpy as np


INITIAL_CENTER = np.array([248.4, 553.0], dtype=np.float32)
INITIAL_POLYGON = np.array(
    [[220.0, 515.0], [315.0, 515.0], [315.0, 680.0], [220.0, 680.0]],
    dtype=np.float32,
)


def polygon_mask(shape: tuple[int, int], polygon: np.ndarray) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    cv2.fillConvexPoly(mask, np.rint(polygon).astype(np.int32), 255)
    return mask


def add_features(
    gray: np.ndarray, polygon: np.ndarray, existing: np.ndarray | None
) -> np.ndarray:
    mask = polygon_mask(gray.shape, polygon)
    if existing is not None:
        for point in existing.reshape(-1, 2):
            cv2.circle(mask, tuple(np.rint(point).astype(int)), 6, 0, -1)
    new_points = cv2.goodFeaturesToTrack(
        gray,
        maxCorners=120,
        qualityLevel=0.01,
        minDistance=5,
        mask=mask,
        blockSize=5,
    )
    if new_points is None:
        if existing is None:
            raise RuntimeError("no initial tracking features")
        return existing
    if existing is None:
        return new_points.astype(np.float32)
    return np.concatenate((existing, new_points.astype(np.float32)), axis=0)


def transform_points(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    return cv2.transform(points.reshape(1, -1, 2), matrix).reshape(-1, 2)


def track_video(video_path: Path) -> tuple[np.ndarray, float, np.ndarray]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"cannot open {video_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    ok, frame = capture.read()
    if not ok:
        raise RuntimeError("cannot read first frame")

    previous_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    polygon = INITIAL_POLYGON.copy()
    center = INITIAL_CENTER.copy()
    points = add_features(previous_gray, polygon, None)
    trajectory = [center.copy()]
    background_samples = [frame.copy()]
    frame_index = 0

    lk_params = dict(
        winSize=(25, 25),
        maxLevel=3,
        criteria=(
            cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
            30,
            0.01,
        ),
    )

    while True:
        ok, frame = capture.read()
        if not ok:
            break
        frame_index += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        next_points, status, _ = cv2.calcOpticalFlowPyrLK(
            previous_gray, gray, points, None, **lk_params
        )
        if next_points is None or status is None:
            raise RuntimeError(f"optical flow failed at frame {frame_index}")
        back_points, back_status, _ = cv2.calcOpticalFlowPyrLK(
            gray, previous_gray, next_points, None, **lk_params
        )
        if back_points is None or back_status is None:
            raise RuntimeError(f"backward flow failed at frame {frame_index}")

        forward = points.reshape(-1, 2)
        backward = back_points.reshape(-1, 2)
        candidate = next_points.reshape(-1, 2)
        valid = (
            (status.reshape(-1) != 0)
            & (back_status.reshape(-1) != 0)
            & (np.linalg.norm(forward - backward, axis=1) < 1.5)
        )
        old_good = forward[valid]
        new_good = candidate[valid]
        if len(old_good) < 6:
            raise RuntimeError(
                f"too few tracking features at frame {frame_index}: {len(old_good)}"
            )

        matrix, inliers = cv2.estimateAffinePartial2D(
            old_good,
            new_good,
            method=cv2.RANSAC,
            ransacReprojThreshold=2.0,
            maxIters=500,
            confidence=0.99,
            refineIters=10,
        )
        if matrix is None or inliers is None or int(inliers.sum()) < 5:
            delta = np.median(new_good - old_good, axis=0)
            matrix = np.array(
                [[1.0, 0.0, delta[0]], [0.0, 1.0, delta[1]]],
                dtype=np.float32,
            )
            kept = new_good
        else:
            kept = new_good[inliers.reshape(-1) != 0]

        polygon = transform_points(polygon, matrix)
        center = transform_points(center.reshape(1, 2), matrix)[0]
        points = kept.reshape(-1, 1, 2).astype(np.float32)
        if frame_index % 10 == 0 or len(points) < 35:
            points = add_features(gray, polygon, points)

        trajectory.append(center.copy())
        if frame_index % 30 == 0:
            background_samples.append(frame.copy())
        previous_gray = gray

    capture.release()
    background = np.median(
        np.stack(background_samples, axis=0), axis=0
    ).astype(np.uint8)
    return np.asarray(trajectory, dtype=np.float64), fps, background


def tip_candidates(
    gray: np.ndarray,
    predicted: np.ndarray,
    search_radius: int,
    expected_area: float,
) -> list[tuple[float, np.ndarray, float]]:
    height, width = gray.shape
    x0 = max(0, int(math.floor(predicted[0] - search_radius)))
    y0 = max(0, int(math.floor(predicted[1] - search_radius)))
    x1 = min(width, int(math.ceil(predicted[0] + search_radius + 1)))
    y1 = min(height, int(math.ceil(predicted[1] + search_radius + 1)))
    roi = gray[y0:y1, x0:x1]
    _, mask = cv2.threshold(roi, 90, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    result: list[tuple[float, np.ndarray, float]] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < 25.0 or area > 220.0:
            continue
        bx, by, bw, bh = cv2.boundingRect(contour)
        if bw < 5 or bh < 5 or bw > 24 or bh > 24:
            continue
        aspect = bw / bh
        if aspect < 0.45 or aspect > 2.2:
            continue
        perimeter = float(cv2.arcLength(contour, True))
        if perimeter <= 0.0:
            continue
        circularity = 4.0 * math.pi * area / (perimeter * perimeter)
        if circularity < 0.18:
            continue
        moments = cv2.moments(contour)
        if moments["m00"] == 0.0:
            continue
        center = np.array(
            [
                x0 + moments["m10"] / moments["m00"],
                y0 + moments["m01"] / moments["m00"],
            ],
            dtype=np.float64,
        )
        distance = float(np.linalg.norm(center - predicted))
        area_error = abs(math.log(max(area, 1.0) / max(expected_area, 1.0)))
        score = distance + 5.0 * area_error + 3.0 * abs(math.log(aspect))
        result.append((score, center, area))
    return sorted(result, key=lambda item: item[0])


def template_tip_candidate(
    gray: np.ndarray,
    predicted: np.ndarray,
    template: np.ndarray,
    search_radius: int,
) -> tuple[np.ndarray, float] | None:
    half_width = template.shape[1] // 2
    half_height = template.shape[0] // 2
    height, width = gray.shape
    x0 = max(0, int(math.floor(predicted[0] - search_radius - half_width)))
    y0 = max(0, int(math.floor(predicted[1] - search_radius - half_height)))
    x1 = min(width, int(math.ceil(predicted[0] + search_radius + half_width + 1)))
    y1 = min(height, int(math.ceil(predicted[1] + search_radius + half_height + 1)))
    roi = gray[y0:y1, x0:x1]
    if roi.shape[0] < template.shape[0] or roi.shape[1] < template.shape[1]:
        return None
    response = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
    _, maximum, _, location = cv2.minMaxLoc(response)
    center = np.array(
        [
            x0 + location[0] + template.shape[1] / 2.0,
            y0 + location[1] + template.shape[0] / 2.0,
        ],
        dtype=np.float64,
    )
    return center, float(maximum)


def hough_tip_candidates(
    gray: np.ndarray, predicted: np.ndarray, search_radius: int
) -> list[tuple[float, np.ndarray, float]]:
    height, width = gray.shape
    x0 = max(0, int(math.floor(predicted[0] - search_radius)))
    y0 = max(0, int(math.floor(predicted[1] - search_radius)))
    x1 = min(width, int(math.ceil(predicted[0] + search_radius + 1)))
    y1 = min(height, int(math.ceil(predicted[1] + search_radius + 1)))
    roi = gray[y0:y1, x0:x1]
    circles = cv2.HoughCircles(
        cv2.GaussianBlur(roi, (5, 5), 1.0),
        cv2.HOUGH_GRADIENT,
        dp=1.0,
        minDist=8.0,
        param1=80.0,
        param2=9.0,
        minRadius=4,
        maxRadius=13,
    )
    if circles is None:
        return []
    result: list[tuple[float, np.ndarray, float]] = []
    for x, y, radius in circles[0]:
        center = np.array([x0 + x, y0 + y], dtype=np.float64)
        distance = float(np.linalg.norm(center - predicted))
        score = distance + 0.5 * abs(float(radius) - 6.0)
        result.append((score, center, float(radius)))
    return sorted(result, key=lambda item: item[0])


def track_pen_tip(video_path: Path) -> tuple[np.ndarray, float, np.ndarray]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"cannot open {video_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    ok, first_frame = capture.read()
    if not ok:
        raise RuntimeError("cannot read first frame")
    first_gray = cv2.cvtColor(first_frame, cv2.COLOR_BGR2GRAY)
    center = INITIAL_CENTER.astype(np.float64)
    template_half_size = 13
    cx, cy = np.rint(center).astype(int)
    template = first_gray[
        cy - template_half_size : cy + template_half_size,
        cx - template_half_size : cx + template_half_size,
    ].copy()
    trajectory: list[np.ndarray] = [center.copy()]
    background_samples: list[np.ndarray] = [first_frame.copy()]
    velocity = np.zeros(2, dtype=np.float64)
    expected_area = 76.0
    missed = 0
    frame_index = 1
    minimum_template_score = 1.0

    while True:
        ok, frame = capture.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        predicted = center + velocity
        blob_candidates = tip_candidates(
            gray,
            predicted,
            28 if missed == 0 else 45,
            expected_area,
        )
        template_result = template_tip_candidate(
            gray, predicted, template, 42 if missed == 0 else 60
        )
        circle_candidates = hough_tip_candidates(
            gray, predicted, 35 if missed == 0 else 60
        )
        if template_result is not None:
            template_center, template_score = template_result
            minimum_template_score = min(minimum_template_score, template_score)
        else:
            template_center = predicted
            template_score = -1.0

        if circle_candidates and np.linalg.norm(
            circle_candidates[0][1] - predicted
        ) < 18.0:
            next_center = circle_candidates[0][1]
            step = next_center - center
            velocity = 0.65 * velocity + 0.35 * step
            center = next_center
            missed = 0
        elif template_score >= 0.30:
            next_center = template_center
            if (
                blob_candidates
                and np.linalg.norm(blob_candidates[0][1] - template_center) < 7.0
            ):
                next_center = 0.5 * (template_center + blob_candidates[0][1])
                expected_area = (
                    0.97 * expected_area + 0.03 * blob_candidates[0][2]
                )
            step = next_center - center
            velocity = 0.65 * velocity + 0.35 * step
            center = next_center
            missed = 0
        elif blob_candidates:
            _, next_center, area = blob_candidates[0]
            step = next_center - center
            velocity = 0.65 * velocity + 0.35 * step
            center = next_center
            expected_area = 0.97 * expected_area + 0.03 * area
            missed = 0
        else:
            center = predicted
            missed += 1
            if missed > 5:
                raise RuntimeError(
                    f"pen-tip blob lost at frame {frame_index}, center={center}"
                )
        trajectory.append(center.copy())
        if frame_index % 30 == 0:
            background_samples.append(frame.copy())
        frame_index += 1

    capture.release()
    background = np.median(
        np.stack(background_samples, axis=0), axis=0
    ).astype(np.uint8)
    print(f"template_min_score={minimum_template_score:.4f}")
    return np.asarray(trajectory, dtype=np.float64), fps, background


def smooth_path(path: np.ndarray, window: int = 11) -> np.ndarray:
    if window <= 1:
        return path.copy()
    kernel = np.ones(window, dtype=np.float64) / window
    result = np.empty_like(path)
    for axis in range(2):
        padded = np.pad(path[:, axis], (window // 2,), mode="edge")
        result[:, axis] = np.convolve(padded, kernel, mode="valid")
    return result


def save_outputs(
    output_dir: Path,
    trajectory: np.ndarray,
    fps: float,
    background: np.ndarray,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "pen_tip_track.csv"
    with csv_path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle)
        writer.writerow(("frame", "time_s", "x_px", "y_px"))
        for index, point in enumerate(trajectory):
            writer.writerow(
                (index, f"{index / fps:.6f}", f"{point[0]:.6f}", f"{point[1]:.6f}")
            )

    smoothed = smooth_path(trajectory)
    overlay = background.copy()
    count = len(smoothed)
    for index in range(1, count):
        ratio = index / max(1, count - 1)
        color = (
            int(255 * (1.0 - ratio)),
            int(180 * (1.0 - abs(2.0 * ratio - 1.0))),
            int(255 * ratio),
        )
        cv2.line(
            overlay,
            tuple(np.rint(smoothed[index - 1]).astype(int)),
            tuple(np.rint(smoothed[index]).astype(int)),
            color,
            3,
            cv2.LINE_AA,
        )
    cv2.circle(
        overlay, tuple(np.rint(smoothed[0]).astype(int)), 9, (0, 255, 0), -1
    )
    cv2.circle(
        overlay, tuple(np.rint(smoothed[-1]).astype(int)), 9, (0, 0, 255), -1
    )
    cv2.imwrite(str(output_dir / "pen_tip_track_overlay.png"), overlay)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("output_dir", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    trajectory, fps, background = track_video(args.video)
    save_outputs(args.output_dir, trajectory, fps, background)
    displacement = np.linalg.norm(trajectory[-1] - trajectory[0])
    print(
        f"tracking=PASS frames={len(trajectory)} fps={fps:.3f} "
        f"start_end_px={displacement:.3f} "
        f"x={trajectory[:, 0].min():.2f}..{trajectory[:, 0].max():.2f} "
        f"y={trajectory[:, 1].min():.2f}..{trajectory[:, 1].max():.2f}"
    )


if __name__ == "__main__":
    main()
