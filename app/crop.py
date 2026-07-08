"""Compute a face-centered 9:16 crop window for a clip using YuNet face detection."""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "face_detection_yunet_2023mar.onnx"
SAMPLE_FPS = 4.0
SCORE_THRESHOLD = 0.7
ACTIVE_SPEAKER_WINDOW_S = 12.0
MIN_FACE_AREA_RATIO = 0.012
SPEAKER_SCORE_MARGIN = 1.15


@dataclass
class CropWindow:
    x: int
    y: int
    w: int
    h: int
    face_found: bool


@dataclass
class _FaceTrack:
    centers_x: list[float]
    centers_y: list[float]
    areas: list[float]
    lower_activity: list[float]
    mouth_activity: list[float]
    prev_lower_roi: np.ndarray | None = None
    prev_mouth_roi: np.ndarray | None = None

    @property
    def last_center(self) -> tuple[float, float]:
        return self.centers_x[-1], self.centers_y[-1]

    @property
    def center_x(self) -> float:
        return statistics.median(self.centers_x)

    @property
    def center_y(self) -> float:
        return statistics.median(self.centers_y)

    @property
    def area(self) -> float:
        return statistics.median(self.areas)

    @property
    def activity_score(self) -> float:
        if not self.lower_activity:
            return 0.0
        mouth = statistics.mean(self.mouth_activity) if self.mouth_activity else 0.0
        return statistics.mean(self.lower_activity) + mouth * 0.5


def compute_crop(video_path: Path, start_s: float, end_s: float) -> CropWindow:
    """Static 9:16 crop centered on the likely active speaker."""
    cap = cv2.VideoCapture(str(video_path))
    try:
        frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        crop_h = frame_h
        crop_w = int(round(crop_h * 9 / 16))
        if crop_w > frame_w:
            # Source narrower than 9:16 (already vertical), so crop height instead.
            crop_w = frame_w
            crop_h = int(round(crop_w * 16 / 9))

        detector = cv2.FaceDetectorYN.create(
            str(MODEL_PATH), "", (frame_w, frame_h), score_threshold=SCORE_THRESHOLD
        )

        speaker = _select_active_speaker(cap, detector, start_s, end_s, frame_w, frame_h)
        if speaker is not None:
            face_found = True
            cx = speaker.center_x
            cy = speaker.center_y
        else:
            centers_x, centers_y = _largest_face_centers(cap, detector, start_s, end_s)
            face_found = bool(centers_x)
            cx = statistics.median(centers_x) if face_found else frame_w / 2
            cy = statistics.median(centers_y) if face_found else frame_h / 2

        crop_x = int(round(cx - crop_w / 2))
        crop_x = max(0, min(crop_x, frame_w - crop_w))
        crop_y = int(round(cy - crop_h / 2))
        crop_y = max(0, min(crop_y, frame_h - crop_h))
        return CropWindow(x=crop_x, y=crop_y, w=crop_w, h=crop_h, face_found=face_found)
    finally:
        cap.release()


def _select_active_speaker(
    cap: cv2.VideoCapture,
    detector: cv2.FaceDetectorYN,
    start_s: float,
    end_s: float,
    frame_w: int,
    frame_h: int,
) -> _FaceTrack | None:
    """Choose the persistent face with the strongest opening lower-face motion."""
    tracks: list[_FaceTrack] = []
    min_face_area = frame_w * frame_h * MIN_FACE_AREA_RATIO
    max_track_distance = max(frame_w * 0.12, 48)
    speaker_end_s = min(end_s, start_s + ACTIVE_SPEAKER_WINDOW_S)

    t = start_s
    while t < speaker_end_s:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if ok:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            _, faces = detector.detect(frame)
            if faces is not None:
                for face in sorted(faces, key=lambda f: f[2] * f[3], reverse=True):
                    x, y, w, h = [float(v) for v in face[:4]]
                    area = w * h
                    if area < min_face_area:
                        continue
                    cx = x + w / 2
                    cy = y + h / 2
                    lower_roi = _lower_face_roi(gray, face)
                    mouth_roi = _mouth_roi(gray, face)
                    track = _nearest_track(tracks, cx, cy, max_track_distance)
                    if track is None:
                        tracks.append(_FaceTrack([cx], [cy], [area], [], [], lower_roi, mouth_roi))
                    else:
                        _add_face_to_track(track, cx, cy, area, lower_roi, mouth_roi)
        t += 1.0 / SAMPLE_FPS

    candidates = [track for track in tracks if len(track.centers_x) >= 3]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    candidates.sort(key=lambda track: track.activity_score, reverse=True)
    best = candidates[0]
    runner_up_score = candidates[1].activity_score
    if best.activity_score > 0 and best.activity_score >= runner_up_score * SPEAKER_SCORE_MARGIN:
        return best

    # If mouth/lower-face motion is ambiguous, use the persistent largest face.
    return max(candidates, key=lambda track: track.area)


def _largest_face_centers(
    cap: cv2.VideoCapture,
    detector: cv2.FaceDetectorYN,
    start_s: float,
    end_s: float,
) -> tuple[list[float], list[float]]:
    centers_x: list[float] = []
    centers_y: list[float] = []
    t = start_s
    while t < end_s:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if ok:
            _, faces = detector.detect(frame)
            if faces is not None and len(faces) > 0:
                face = max(faces, key=lambda f: f[2] * f[3])
                x, y, w, h = face[:4]
                centers_x.append(float(x + w / 2))
                centers_y.append(float(y + h / 2))
        t += 1.0 / SAMPLE_FPS
    return centers_x, centers_y


def _nearest_track(
    tracks: list[_FaceTrack],
    cx: float,
    cy: float,
    max_distance: float,
) -> _FaceTrack | None:
    if not tracks:
        return None
    nearest = min(
        tracks,
        key=lambda track: (track.last_center[0] - cx) ** 2 + (track.last_center[1] - cy) ** 2,
    )
    dx = nearest.last_center[0] - cx
    dy = nearest.last_center[1] - cy
    if (dx * dx + dy * dy) ** 0.5 <= max_distance:
        return nearest
    return None


def _add_face_to_track(
    track: _FaceTrack,
    cx: float,
    cy: float,
    area: float,
    lower_roi: np.ndarray | None,
    mouth_roi: np.ndarray | None,
) -> None:
    track.centers_x.append(cx)
    track.centers_y.append(cy)
    track.areas.append(area)
    if lower_roi is not None and track.prev_lower_roi is not None:
        track.lower_activity.append(float(np.mean(cv2.absdiff(lower_roi, track.prev_lower_roi))))
    if mouth_roi is not None and track.prev_mouth_roi is not None:
        track.mouth_activity.append(float(np.mean(cv2.absdiff(mouth_roi, track.prev_mouth_roi))))
    if lower_roi is not None:
        track.prev_lower_roi = lower_roi
    if mouth_roi is not None:
        track.prev_mouth_roi = mouth_roi


def _lower_face_roi(gray: np.ndarray, face: np.ndarray) -> np.ndarray | None:
    x, y, w, h = [float(v) for v in face[:4]]
    return _resized_roi(gray, x + w * 0.22, y + h * 0.52, x + w * 0.78, y + h * 0.95)


def _mouth_roi(gray: np.ndarray, face: np.ndarray) -> np.ndarray | None:
    x, y, w, h = [float(v) for v in face[:4]]
    mouth_left_x, mouth_left_y, mouth_right_x, mouth_right_y = [float(v) for v in face[10:14]]
    mouth_cx = (mouth_left_x + mouth_right_x) / 2
    mouth_cy = (mouth_left_y + mouth_right_y) / 2
    mouth_w = max(abs(mouth_right_x - mouth_left_x) * 2.4, w * 0.35, 8)
    mouth_h = max(h * 0.28, 8)
    return _resized_roi(
        gray,
        mouth_cx - mouth_w / 2,
        mouth_cy - mouth_h * 0.6,
        mouth_cx + mouth_w / 2,
        mouth_cy + mouth_h * 0.9,
    )


def _resized_roi(
    gray: np.ndarray,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> np.ndarray | None:
    height, width = gray.shape[:2]
    left = max(0, int(round(x1)))
    top = max(0, int(round(y1)))
    right = min(width, int(round(x2)))
    bottom = min(height, int(round(y2)))
    if right <= left or bottom <= top:
        return None
    return cv2.resize(gray[top:bottom, left:right], (32, 24), interpolation=cv2.INTER_AREA)
