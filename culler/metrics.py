"""Per-photo quality measurements computed on the preview."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import imagehash
import numpy as np
from PIL import Image

_face_model = None
_eye_model = None


@dataclass
class Metrics:
    # Focus of the sharpest region. Using the best tile rather than the whole
    # frame keeps shallow depth-of-field portraits from being flagged as blurry.
    sharpness: float
    # Focus of the whole frame, used to tell motion blur from a soft background.
    global_sharpness: float
    brightness: float  # mean luminance, 0-255
    shadows_clipped: float  # fraction of pixels crushed to black
    highlights_clipped: float  # fraction of pixels blown to white
    faces: int
    faces_eyes_closed: int  # faces where no open eye was found
    phash: str


def measure(rgb: np.ndarray) -> Metrics:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    sharpness, global_sharpness = _sharpness(gray)
    faces, closed = _faces(gray)
    return Metrics(
        sharpness=sharpness,
        global_sharpness=global_sharpness,
        brightness=float(gray.mean()),
        shadows_clipped=float((gray <= 3).mean()),
        highlights_clipped=float((gray >= 252).mean()),
        faces=faces,
        faces_eyes_closed=closed,
        phash=str(imagehash.phash(Image.fromarray(rgb))),
    )


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


def _faces(gray: np.ndarray) -> tuple[int, int]:
    global _face_model, _eye_model
    if _face_model is None:
        _face_model = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        _eye_model = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")

    min_face = max(40, min(gray.shape) // 12)
    faces = _face_model.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=6, minSize=(min_face, min_face)
    )
    closed = 0
    for x, y, w, h in faces:
        # The eye model only fires on open eyes, so a clear face with no eye
        # hits is a decent hint that someone blinked.
        upper = gray[y : y + h // 2 + h // 8, x : x + w]
        eyes = _eye_model.detectMultiScale(
            upper, scaleFactor=1.1, minNeighbors=4, minSize=(w // 10, w // 10)
        )
        if len(eyes) == 0:
            closed += 1
    return len(faces), closed
