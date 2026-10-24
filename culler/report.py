"""Results files and a static contact sheet for checking the culling at a glance."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from PIL import Image

from .scoring import Result

THUMB_SIZE = 360


def save_thumbnail(rgb, out: Path) -> None:
    image = Image.fromarray(rgb)
    image.thumbnail((THUMB_SIZE, THUMB_SIZE))
    image.save(out, "JPEG", quality=80)


def write_results(results: list[Result], root: Path, out_dir: Path) -> None:
    rows = [_row(r, root) for r in sorted(results, key=lambda r: r.info.path)]
    (out_dir / "results.json").write_text(json.dumps(rows, indent=2, default=str))
    with open(out_dir / "results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["file"])
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "; ".join(v) if isinstance(v, list) else v for k, v in row.items()})
    (out_dir / "report.html").write_text(_html(results, root))


def thumb_name(result: Result, root: Path) -> str:
    rel = result.info.path.relative_to(root).with_suffix("")
    return "thumbs/" + "__".join(rel.parts) + ".jpg"


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
    counts = {d: sum(r.decision == d for r in results) for d in ("pick", "duplicate", "reject")}
    cards = []
    for r in sorted(results, key=lambda r: (r.burst, -r.score)):
        reasons = ", ".join(r.reasons) or "looks good"
        cards.append(
            f'<figure class="{r.decision}" data-burst="{r.burst}">'
            f'<img loading="lazy" src="{html.escape(thumb_name(r, root))}" alt="">'
            f"<figcaption><b>{html.escape(r.info.path.name)}</b>"
            f'<span>{"★" * r.stars}{"☆" * (5 - r.stars)} · {r.score:.0f}</span>'
            f"<small>{html.escape(reasons)}</small></figcaption></figure>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Culling report</title>
<style>
:root {{ --bg:#f6f6f4; --fg:#1d1d1b; --muted:#6b6b66; --card:#fff;
  --pick:#2e8b57; --duplicate:#c9a227; --reject:#c0392b; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#161615; --fg:#ececea; --muted:#9a9a94; --card:#222220; }} }}
body {{ margin:0; padding:24px 16px; background:var(--bg); color:var(--fg);
  font:14px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
header {{ display:flex; flex-wrap:wrap; gap:12px; align-items:baseline; margin-bottom:16px; }}
h1 {{ font-size:20px; margin:0 12px 0 0; }}
label {{ color:var(--muted); cursor:pointer; }}
main {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(200px, 1fr)); gap:12px; }}
figure {{ margin:0; background:var(--card); border-top:4px solid var(--pick); border-radius:6px; overflow:hidden; }}
figure.duplicate {{ border-color:var(--duplicate); }}
figure.reject {{ border-color:var(--reject); opacity:.55; }}
img {{ width:100%; aspect-ratio:3/2; object-fit:cover; display:block; background:#0002; }}
figcaption {{ padding:8px; display:grid; gap:2px; }}
figcaption b {{ font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
small {{ color:var(--muted); }}
body.hide-reject .reject, body.hide-duplicate .duplicate {{ display:none; }}
</style></head>
<body class="hide-reject">
<header><h1>Culling report</h1>
<span>{counts["pick"]} picks · {counts["duplicate"]} similar · {counts["reject"]} rejects</span>
<label><input type="checkbox" data-toggle="reject"> show rejects</label>
<label><input type="checkbox" data-toggle="duplicate" checked> show similar shots</label>
</header>
<main>{"".join(cards)}</main>
<script>
document.querySelectorAll("[data-toggle]").forEach(box => box.addEventListener("change", () =>
  document.body.classList.toggle("hide-" + box.dataset.toggle, !box.checked)));
</script>
</body></html>
"""
