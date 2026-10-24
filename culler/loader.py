"""Finding photos on disk and turning them into small previews plus EXIF data."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import exifread
import numpy as np
from PIL import Image, ImageOps

RAW_EXTENSIONS = {".arw"}
JPEG_EXTENSIONS = {".jpg", ".jpeg"}
SUPPORTED_EXTENSIONS = RAW_EXTENSIONS | JPEG_EXTENSIONS

# Long edge of the preview every metric runs on. Big enough to judge focus,
# small enough that a few thousand photos score in minutes on a laptop CPU.
PREVIEW_SIZE = 1024


@dataclass
class PhotoInfo:
    path: Path
    captured_at: datetime | None = None
    camera: str | None = None
    lens: str | None = None
    iso: int | None = None
    shutter: str | None = None
    aperture: float | None = None
    focal_length: float | None = None
    gps: tuple[float, float] | None = None
    extra: dict = field(default_factory=dict)


def find_photos(root: Path) -> list[Path]:
    """All supported files under root, skipping hidden folders and macOS '._' files.

    When a RAW and a JPEG share a name (RAW+JPEG shooting), only the RAW is kept,
    because that's the file that goes into Capture One.
    """
    photos: dict[tuple[Path, str], Path] = {}
    for path in sorted(root.rglob("*")):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        if path.name.startswith("._") or not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue
        key = (path.parent, path.stem)
        if key in photos and photos[key].suffix.lower() in RAW_EXTENSIONS:
            continue
        photos[key] = path
    return sorted(photos.values())


def load_preview(path: Path) -> np.ndarray:
    """An RGB uint8 array no larger than PREVIEW_SIZE on its long edge."""
    if path.suffix.lower() in RAW_EXTENSIONS:
        image = _raw_preview(path)
    else:
        image = Image.open(path)
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((PREVIEW_SIZE, PREVIEW_SIZE), Image.Resampling.LANCZOS)
    return np.asarray(image)


def _raw_preview(path: Path) -> Image.Image:
    # Sony ARW files carry a full-size JPEG preview. Using it is ~50x faster
    # than demosaicing the raw data and is what the camera itself shows.
    import rawpy

    with rawpy.imread(str(path)) as raw:
        try:
            thumb = raw.extract_thumb()
        except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
            return Image.fromarray(raw.postprocess(half_size=True, use_camera_wb=True))
    if thumb.format == rawpy.ThumbFormat.JPEG:
        return Image.open(io.BytesIO(thumb.data))
    return Image.fromarray(thumb.data)


def read_exif(path: Path) -> PhotoInfo:
    info = PhotoInfo(path=path)
    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False)
    except Exception:
        return info

    def text(*names: str) -> str | None:
        for name in names:
            if name in tags:
                value = str(tags[name]).strip()
                if value:
                    return value
        return None

    taken = text("EXIF DateTimeOriginal", "Image DateTime")
    if taken:
        try:
            info.captured_at = datetime.strptime(taken, "%Y:%m:%d %H:%M:%S")
            subsec = text("EXIF SubSecTimeOriginal")
            if subsec and subsec.isdigit():
                info.captured_at = info.captured_at.replace(
                    microsecond=int(subsec.ljust(6, "0")[:6])
                )
        except ValueError:
            pass

    make, model = text("Image Make"), text("Image Model")
    if model:
        info.camera = model if not make or model.startswith(make) else f"{make} {model}"
    info.lens = text("EXIF LensModel")
    iso = text("EXIF ISOSpeedRatings", "EXIF PhotographicSensitivity")
    if iso and iso.split()[0].isdigit():
        info.iso = int(iso.split()[0])
    info.shutter = text("EXIF ExposureTime")
    info.aperture = _ratio(tags.get("EXIF FNumber"))
    info.focal_length = _ratio(tags.get("EXIF FocalLength"))
    info.gps = _gps(tags)
    return info


def _ratio(tag) -> float | None:
    if tag is None or not tag.values:
        return None
    value = tag.values[0]
    try:
        return round(float(value.num) / float(value.den), 1) if value.den else None
    except AttributeError:
        return float(value)


def _gps(tags) -> tuple[float, float] | None:
    try:
        lat = _dms(tags["GPS GPSLatitude"].values)
        lon = _dms(tags["GPS GPSLongitude"].values)
    except (KeyError, ZeroDivisionError):
        return None
    if str(tags.get("GPS GPSLatitudeRef", "N")) == "S":
        lat = -lat
    if str(tags.get("GPS GPSLongitudeRef", "E")) == "W":
        lon = -lon
    return round(lat, 6), round(lon, 6)


def _dms(values) -> float:
    d, m, s = (float(v.num) / float(v.den) for v in values)
    return d + m / 60 + s / 3600
