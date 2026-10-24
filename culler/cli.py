"""Command line entry point: `python -m culler scan <folder>`."""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from . import xmp
from .loader import find_photos, load_preview, read_exif
from .metrics import measure
from .report import save_thumbnail, thumb_name, write_results
from .scoring import Result, Thresholds, score_all


def _analyse(job: tuple[Path, Path, Path]) -> Result | str:
    path, root, out_dir = job
    try:
        rgb = load_preview(path)
        result = Result(info=read_exif(path), metrics=measure(rgb))
        save_thumbnail(rgb, out_dir / thumb_name(result, root))
        return result
    except Exception as exc:  # one bad file shouldn't stop a whole trip
        return f"{path}: {exc}"


def scan(args: argparse.Namespace) -> int:
    root = Path(args.folder).resolve()
    if not root.is_dir():
        print(f"Not a folder: {root}", file=sys.stderr)
        return 2
    out_dir = Path(args.out).resolve() if args.out else root / ".studio-photo"
    (out_dir / "thumbs").mkdir(parents=True, exist_ok=True)

    photos = find_photos(root)
    if not photos:
        print(f"No ARW or JPEG files found in {root}")
        return 1
    print(f"Scoring {len(photos)} photos from {root} ...")

    started = time.time()
    results, errors = [], []
    jobs = [(p, root, out_dir) for p in photos]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for i, outcome in enumerate(pool.map(_analyse, jobs, chunksize=4), 1):
            (errors if isinstance(outcome, str) else results).append(outcome)
            if i % 50 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)}", flush=True)

    thresholds = Thresholds(blur_floor=args.blur_floor, burst_seconds=args.burst_seconds)
    score_all(results, thresholds)
    write_results(results, root, out_dir)

    written = skipped = 0
    if not args.dry_run:
        for r in results:
            if xmp.write_sidecar(r, force=args.force) == "written":
                written += 1
            else:
                skipped += 1

    counts = {d: sum(r.decision == d for r in results) for d in ("pick", "duplicate", "reject")}
    print(
        f"\nDone in {time.time() - started:.0f}s: {counts['pick']} picks, "
        f"{counts['duplicate']} similar shots, {counts['reject']} rejects."
    )
    if args.dry_run:
        print("Dry run: no XMP sidecars written.")
    else:
        print(f"XMP sidecars written: {written}" + (f", left alone (already existed): {skipped}" if skipped else ""))
    print(f"Report: {out_dir / 'report.html'}")
    for e in errors:
        print(f"  could not read {e}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="culler", description="Pre-cull travel photos for Capture One.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("scan", help="score a folder of photos and write XMP ratings")
    p.add_argument("folder")
    p.add_argument("--out", help="where to put the report (default: <folder>/.studio-photo)")
    p.add_argument("--dry-run", action="store_true", help="score and report, but don't write XMP sidecars")
    p.add_argument("--force", action="store_true", help="overwrite XMP sidecars that already exist")
    p.add_argument("--workers", type=int, default=os.cpu_count())
    p.add_argument("--blur-floor", type=float, default=Thresholds.blur_floor)
    p.add_argument("--burst-seconds", type=float, default=Thresholds.burst_seconds)
    p.set_defaults(func=scan)
    args = parser.parse_args(argv)
    return args.func(args)
