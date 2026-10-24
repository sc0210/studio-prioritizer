"""Per-photo quality measurements computed on the preview."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import imagehash
import numpy as np
from PIL import Image

FACE_MODEL = Path(__file__).parent / "models" / "face_detection_yunet_2023mar.onnx"
# YuNet confidence below which a detection is ignored. High on purpose: a
# missed face costs nothing, a face found in foliage invents a "blink".
FACE_CONFIDENCE = 0.85

_face_model = None
_eye_model = None


@dataclass
class Metrics:
    # Focus of the sharpest region. Using the best tile rather than the whole
    # frame keeps shallow depth-of-field portraits from being flagged as blurry.
    sharpness: float
    # Focus of the whole frame, used to tell motion blur from a soft background.
    global_sharpness: float
    # Spread between the 1st and 99th luminance percentiles. Near zero means
    # the frame holds no picture at all (lens cap, pocket shot).
    tonal_range: float
    brightness: float  # mean luminance, 0-255
    shadows_clipped: float  # fraction of pixels crushed to black
    highlights_clipped: float  # fraction of pixels blown to white
    faces: int
    faces_eyes_closed: int  # faces where no open eye was found
    phash: str


def measure(rgb: np.ndarray) -> Metrics:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    low, high = np.percentile(gray, (1, 99))
    normalized = _normalize(gray, low, high)
    sharpness, global_sharpness = _sharpness(normalized)
    faces, closed = _faces(_normalize(rgb, low, high), normalized)
    return Metrics(
        sharpness=sharpness,
        global_sharpness=global_sharpness,
        tonal_range=float(high - low),
        brightness=float(gray.mean()),
        shadows_clipped=float((gray <= 3).mean()),
        highlights_clipped=float((gray >= 252).mean()),
        faces=faces,
        faces_eyes_closed=closed,
        phash=str(imagehash.phash(Image.fromarray(rgb))),
    )


def _normalize(image: np.ndarray, low: float, high: float) -> np.ndarray:
    # Exposure is fixable in the RAW, focus isn't, so judge focus as if the
    # exposure were already corrected: stretch the tones to the full range.
    # Without this a dark but sharp frame has weak edges and reads as blurry.
    if high - low < 8:
        return image
    stretched = (image.astype(np.float32) - low) * (255.0 / (high - low))
    return np.clip(stretched, 0, 255).astype(np.uint8)


def _sharpness(gray: np.ndarray, grid: int = 4) -> tuple[float, float]:
    # Light denoise first so high ISO grain doesn't read as detail.
    smooth = cv2.GaussianBlur(gray, (3, 3), 0)
    lap = cv2.Laplacian(smooth, cv2.CV_64F)
    h, w = lap.shape
    tiles = [
        lap[r * h // grid : (r + 1) * h // grid, c * w // grid : (c + 1) * w // grid].var()
        for r in range(grid)
        for c in range(grid)
    ]
    return float(max(tiles)), float(lap.var())


def _faces(rgb: np.ndarray, gray: np.ndarray) -> tuple[int, int]:
    global _face_model, _eye_model
    if _face_model is None:
        _face_model = cv2.FaceDetectorYN.create(
            str(FACE_MODEL), "", (320, 320), score_threshold=FACE_CONFIDENCE
        )
        _eye_model = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")

    h, w = gray.shape
    _face_model.setInputSize((w, h))
    _, detections = _face_model.detect(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if detections is None:
        return 0, 0

    # Faces this small are background people; their eyes can't be judged.
    min_face = min(h, w) / 15
    faces = [d for d in detections if d[2] >= min_face]
    closed = 0
    for d in faces:
        face_w = d[2]
        # YuNet gives eye centres; look for an open eye in a box around each.
        # The eye model only fires on open eyes, so neither firing hints at a blink.
        if not any(_eye_open(gray, d[4 + 2 * i], d[5 + 2 * i], face_w) for i in range(2)):
            closed += 1
    return len(faces), closed


def _eye_open(gray: np.ndarray, x: float, y: float, face_w: float) -> bool:
    half = max(int(face_w * 0.2), 8)
    x0, y0 = max(int(x) - half, 0), max(int(y) - half, 0)
    crop = gray[y0 : int(y) + half, x0 : int(x) + half]
    if crop.size == 0:
        return True
    crop = cv2.resize(crop, (64, 64))
    eyes = _eye_model.detectMultiScale(crop, scaleFactor=1.05, minNeighbors=3, minSize=(16, 16))
    return len(eyes) > 0
