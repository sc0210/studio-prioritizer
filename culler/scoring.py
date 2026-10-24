"""Turning raw metrics into a score, a keep/reject call, burst groups and star ratings."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

import imagehash

from .loader import PhotoInfo
from .metrics import Metrics


@dataclass
class Thresholds:
    # Best-tile Laplacian variance on the 1024px preview below which a photo is
    # treated as out of focus regardless of the rest of the shoot.
    blur_floor: float = 60.0
    # Also reject if far softer than this shoot's typical photo.
    blur_relative: float = 0.2
    highlights_max: float = 0.25
    shadows_max: float = 0.45
    too_dark: float = 22.0
    too_bright: float = 238.0
    # Consecutive frames this close in time and look are one burst.
    burst_seconds: float = 2.0
    burst_hash_distance: int = 16


@dataclass
class Result:
    info: PhotoInfo
    metrics: Metrics
    score: float = 0.0
    decision: str = "pick"  # pick | duplicate | reject
    reasons: list[str] = field(default_factory=list)
    burst: int = 0
    stars: int = 0

    @property
    def label(self) -> str:
        return {"pick": "Green", "duplicate": "Yellow", "reject": "Red"}[self.decision]


def score_all(results: list[Result], t: Thresholds | None = None) -> list[Result]:
    t = t or Thresholds()
    if not results:
        return results
    typical = statistics.median(r.metrics.sharpness for r in results)
    blur_limit = max(t.blur_floor, typical * t.blur_relative)

    for r in results:
        _score_one(r, blur_limit, t)
    _group_bursts(results, t)
    _assign_stars(results)
    return results


def _score_one(r: Result, blur_limit: float, t: Thresholds) -> None:
    m = r.metrics
    reasons = []
    if m.sharpness < blur_limit:
        reasons.append("blurry")
    washed_out = m.brightness > t.too_bright - 20 and m.highlights_clipped > t.highlights_max / 2
    if m.highlights_clipped > t.highlights_max or m.brightness > t.too_bright or washed_out:
        reasons.append("overexposed")
    if m.shadows_clipped > t.shadows_max or m.brightness < t.too_dark:
        reasons.append("underexposed")

    # 0 at the blur limit, 1 at ten times it.
    sharp = min(max(math.log10(max(m.sharpness, 1e-6) / blur_limit), 0.0), 1.0)
    exposure = 1.0 - min(1.0, 2 * m.highlights_clipped + m.shadows_clipped)
    if m.brightness < 60:
        exposure -= (60 - m.brightness) / 120
    elif m.brightness > 190:
        exposure -= (m.brightness - 190) / 130
    exposure = max(exposure, 0.0)
    eyes = 1.0
    if m.faces:
        eyes = 1.0 - m.faces_eyes_closed / m.faces
        if m.faces_eyes_closed:
            reasons.append("eyes closed?")

    r.score = round(100 * (0.6 * sharp + 0.3 * exposure + 0.1 * eyes), 1)
    r.reasons = reasons
    # A possible blink alone isn't enough to throw a photo away; it only costs points.
    r.decision = "reject" if set(reasons) - {"eyes closed?"} else "pick"


def _group_bursts(results: list[Result], t: Thresholds) -> None:
    ordered = sorted(
        results,
        key=lambda r: (r.info.captured_at is None, r.info.captured_at or 0, r.info.path.name),
    )
    burst = 0
    prev = None
    for r in ordered:
        if prev is not None and not _same_burst(prev, r, t):
            burst += 1
        r.burst = burst
        prev = r

    groups: dict[int, list[Result]] = {}
    for r in results:
        groups.setdefault(r.burst, []).append(r)
    for members in groups.values():
        keepers = [r for r in members if r.decision != "reject"]
        if len(keepers) < 2:
            continue
        best = max(keepers, key=lambda r: r.score)
        for r in keepers:
            if r is not best:
                r.decision = "duplicate"
                r.reasons.append("similar to a better shot")


def _same_burst(a: Result, b: Result, t: Thresholds) -> bool:
    ta, tb = a.info.captured_at, b.info.captured_at
    if ta and tb and abs((tb - ta).total_seconds()) > t.burst_seconds:
        return False
    distance = imagehash.hex_to_hash(a.metrics.phash) - imagehash.hex_to_hash(b.metrics.phash)
    return distance <= t.burst_hash_distance


def _assign_stars(results: list[Result]) -> None:
    keepers = sorted(
        (r for r in results if r.decision != "reject"), key=lambda r: r.score, reverse=True
    )
    n = len(keepers)
    for i, r in enumerate(keepers):
        rank = i / n
        r.stars = 5 if rank < 0.1 else 4 if rank < 0.3 else 3 if rank < 0.7 else 2
        if r.decision == "duplicate":
            r.stars = min(r.stars, 2)
    for r in results:
        if r.decision == "reject":
            r.stars = 1
