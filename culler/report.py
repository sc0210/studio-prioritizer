"""Results files and a static contact sheet for checking the culling at a glance."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from PIL import Image

from .scoring import Result

THUMB_SIZE = 480
TEMPLATE = Path(__file__).parent / "report_template.html"


def save_images(rgb, result: Result, root: Path, out_dir: Path) -> None:
    """A grid thumbnail and a larger preview for the report's viewer."""
    image = Image.fromarray(rgb)
    image.save(out_dir / image_name(result, root, "previews"), "JPEG", quality=82)
    image.thumbnail((THUMB_SIZE, THUMB_SIZE))
    image.save(out_dir / image_name(result, root, "thumbs"), "JPEG", quality=80)


def write_results(results: list[Result], root: Path, out_dir: Path) -> None:
    rows = [_row(r, root) for r in sorted(results, key=lambda r: r.info.path)]
    (out_dir / "results.json").write_text(json.dumps(rows, indent=2, default=str))
    with open(out_dir / "results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["file"])
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "; ".join(v) if isinstance(v, list) else v for k, v in row.items()})
    (out_dir / "report.html").write_text(_html(results, root))


def image_name(result: Result, root: Path, kind: str) -> str:
    # Keep the extension in the name so A.ARW and A.jpg never share a file.
    rel = result.info.path.relative_to(root)
    return f"{kind}/" + "__".join(rel.parts) + ".jpg"


def _row(r: Result, root: Path) -> dict:
    m, i = r.metrics, r.info
    return {
        "file": str(i.path.relative_to(root)),
        "decision": r.decision,
        "stars": r.stars,
        "label": r.label,
        "score": r.score,
        "reasons": r.reasons,
        "burst": r.burst,
        "captured_at": i.captured_at.isoformat() if i.captured_at else None,
        "camera": i.camera,
        "lens": i.lens,
        "iso": i.iso,
        "shutter": i.shutter,
        "aperture": i.aperture,
        "focal_length": i.focal_length,
        "gps": list(i.gps) if i.gps else None,
        "sharpness": round(m.sharpness, 1),
        "brightness": round(m.brightness, 1),
        "highlights_clipped": round(m.highlights_clipped, 4),
        "shadows_clipped": round(m.shadows_clipped, 4),
        "faces": m.faces,
        "faces_eyes_closed": m.faces_eyes_closed,
    }


def _html(results: list[Result], root: Path) -> str:
    rows = []
    for r in sorted(results, key=lambda r: r.info.path):
        row = _row(r, root)
        row["name"] = r.info.path.name
        row["type"] = r.info.path.suffix.lstrip(".").upper().replace("JPEG", "JPG")
        row["thumb"] = image_name(r, root, "thumbs")
        row["preview"] = image_name(r, root, "previews")
        rows.append(row)
    # "</" can't appear inside a <script> block, so escape it in the data.
    data = json.dumps(rows, default=str).replace("</", "<\\/")
    return TEMPLATE.read_text(encoding="utf-8").replace("/*DATA*/[]", data)
