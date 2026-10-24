from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageFilter
from skimage import data

from culler.cli import main
from culler.loader import find_photos, read_exif
from culler.metrics import measure
from culler.xmp import sidecar_path

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

START = datetime(2026, 9, 14, 10, 0, 0)


def _save(img: Image.Image, path: Path, when: datetime) -> None:
    exif = Image.Exif()
    exif[0x0110] = "ILCE-7M4"  # Model
    exif[0x010F] = "SONY"  # Make
    exif.get_ifd(0x8769)[0x9003] = when.strftime("%Y:%m:%d %H:%M:%S")  # DateTimeOriginal
    img.save(path, "JPEG", quality=92, exif=exif)


def _scene(seed: int) -> Image.Image:
    # Native size: upscaling a small sample would make it genuinely soft.
    base = Image.fromarray(data.coffee() if seed % 2 else data.rocket())
    return base.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if seed > 2 else base


@pytest.fixture
def trip(tmp_path: Path) -> Path:
    t = START
    # A three-frame burst of the same scene, one of them slightly softer.
    sharp = Image.fromarray(data.astronaut())
    _save(sharp, tmp_path / "DSC00001.JPG", t)
    _save(sharp.filter(ImageFilter.GaussianBlur(1.2)), tmp_path / "DSC00002.JPG", t + timedelta(seconds=0.5))
    _save(sharp, tmp_path / "DSC00003.JPG", t + timedelta(seconds=1))
    # Separate scenes later on.
    _save(_scene(1), tmp_path / "DSC00010.JPG", t + timedelta(minutes=5))
    _save(_scene(2), tmp_path / "DSC00011.JPG", t + timedelta(minutes=9))
    # Badly out of focus.
    _save(_scene(3).filter(ImageFilter.GaussianBlur(12)), tmp_path / "DSC00020.JPG", t + timedelta(minutes=15))
    # Blown out and nearly black frames.
    bright = Image.fromarray(np.clip(np.asarray(_scene(4), dtype=int) + 170, 0, 255).astype("uint8"))
    _save(bright, tmp_path / "DSC00030.JPG", t + timedelta(minutes=20))
    dark = Image.fromarray((np.asarray(_scene(5)) * 0.04).astype("uint8"))
    _save(dark, tmp_path / "DSC00031.JPG", t + timedelta(minutes=25))
    # macOS metadata junk that must be ignored.
    (tmp_path / "._DSC00001.JPG").write_bytes(b"junk")
    return tmp_path


def _results(folder: Path) -> dict:
    import json

    rows = json.loads((folder / ".studio-photo" / "results.json").read_text())
    return {row["file"]: row for row in rows}


def test_find_photos_prefers_raw_and_skips_junk(tmp_path: Path):
    for name in ["A.ARW", "A.JPG", "B.jpg", "._B.jpg", "notes.txt"]:
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / ".studio-photo").mkdir()
    (tmp_path / ".studio-photo" / "C.jpg").write_bytes(b"x")
    assert [p.name for p in find_photos(tmp_path)] == ["A.ARW", "B.jpg"]


def test_exif_is_read(trip: Path):
    info = read_exif(trip / "DSC00002.JPG")
    assert info.camera == "SONY ILCE-7M4"
    assert info.captured_at == START  # whole seconds only in this fixture


def test_blurry_frame_measures_softer():
    sharp = data.astronaut()
    soft = np.asarray(Image.fromarray(sharp).filter(ImageFilter.GaussianBlur(4)))
    assert measure(soft).sharpness < measure(sharp).sharpness / 5


def test_dark_frame_is_not_mistaken_for_blurry():
    sharp = data.astronaut()
    dark = (sharp * 0.05).astype("uint8")
    assert measure(dark).sharpness > measure(sharp).sharpness / 3


def test_empty_frame_is_rejected(tmp_path: Path):
    _save(Image.fromarray(data.astronaut()), tmp_path / "A.JPG", START)
    _save(Image.new("RGB", (800, 600), (4, 4, 4)), tmp_path / "B.JPG", START + timedelta(minutes=1))
    main(["scan", str(tmp_path), "--workers", "1"])
    rows = _results(tmp_path)
    assert rows["B.JPG"]["decision"] == "reject"
    assert "empty frame" in rows["B.JPG"]["reasons"]


def test_scan_end_to_end(trip: Path):
    assert main(["scan", str(trip), "--workers", "2"]) == 0
    rows = _results(trip)
    assert len(rows) == 8

    burst = [rows[f"DSC0000{i}.JPG"] for i in (1, 2, 3)]
    assert len({r["burst"] for r in burst}) == 1
    assert sum(r["decision"] == "pick" for r in burst) == 1
    assert rows["DSC00002.JPG"]["decision"] != "pick"

    assert rows["DSC00010.JPG"]["decision"] == "pick"
    assert rows["DSC00011.JPG"]["decision"] == "pick"
    assert rows["DSC00020.JPG"]["decision"] == "reject"
    assert "blurry" in rows["DSC00020.JPG"]["reasons"]
    # Exposure is fixable in editing: noted, but the photos stay in.
    assert "overexposed" in rows["DSC00030.JPG"]["reasons"]
    assert "underexposed" in rows["DSC00031.JPG"]["reasons"]
    assert rows["DSC00030.JPG"]["decision"] == "pick"
    assert rows["DSC00031.JPG"]["decision"] == "pick"
    assert "studio-photo/underexposed" in sidecar_path(trip / "DSC00031.JPG").read_text()

    xmp = sidecar_path(trip / "DSC00020.JPG").read_text()
    assert 'xmp:Label="Red"' in xmp and 'xmp:Rating="1"' in xmp
    assert 'xmp:Label="Green"' in sidecar_path(trip / "DSC00010.JPG").read_text()
    assert (trip / ".studio-photo" / "report.html").exists()


def test_existing_sidecars_are_left_alone(trip: Path):
    mine = sidecar_path(trip / "DSC00010.JPG")
    mine.write_text("edited in Capture One")
    main(["scan", str(trip), "--workers", "1"])
    assert mine.read_text() == "edited in Capture One"
    main(["scan", str(trip), "--workers", "1", "--force"])
    assert mine.read_text() != "edited in Capture One"


def test_dry_run_writes_no_sidecars(trip: Path):
    main(["scan", str(trip), "--dry-run", "--workers", "1"])
    assert not list(trip.glob("*.xmp"))


def test_arw_uses_embedded_jpeg_preview(tmp_path: Path, monkeypatch):
    # No real ARW in the repo, so stand in for LibRaw and check the preview path.
    import io

    import rawpy

    from culler.loader import load_preview

    buf = io.BytesIO()
    Image.fromarray(data.astronaut()).resize((2000, 1333)).save(buf, "JPEG")

    class FakeRaw:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_thumb(self):
            class Thumb:
                format = rawpy.ThumbFormat.JPEG
                data = buf.getvalue()

            return Thumb()

    monkeypatch.setattr(rawpy, "imread", lambda path: FakeRaw())
    preview = load_preview(tmp_path / "DSC09999.ARW")
    assert preview.shape == (682, 1024, 3)
