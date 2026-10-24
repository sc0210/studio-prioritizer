# studio-prioritizer

Pre-culls a travel shoot so you only look at the photos worth editing.

Point it at a folder of Sony `.ARW` (or JPEG) files. It scores every frame and flags the weak ones: out of focus, blown out, too dark, a possible blink, or a near-copy of a better frame in the same burst. Then it writes an XMP sidecar next to each photo, which Capture One reads as star ratings and color labels.

Nothing is moved or deleted. The sidecars and a report are the only files it writes.

| Label | Meaning | Stars |
|---|---|---|
| 🟢 Green | Keeper, the best frame of its burst | 2–5, by score across the whole shoot |
| 🟡 Yellow | Fine, but a better near-identical frame exists | at most 2 |
| 🔴 Red | Reject: blurry, overexposed or underexposed | 1 |

Each sidecar also adds keywords such as `studio-photo/reject` and `studio-photo/blurry`, so you can filter on the reason in Capture One.

## Run it with Docker (macOS)

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```sh
git clone https://github.com/sc0210/studio-prioritizer && cd studio-prioritizer
PHOTOS=~/Pictures/Japan-2026 docker compose run --rm culler
```

The first run builds the image (a few minutes). After that, a scan prints a summary and the path of the report:

```
Scoring 1843 photos from /photos ...
Done in 212s: 611 picks, 742 similar shots, 490 rejects.
XMP sidecars written: 1843
Report: /photos/.studio-photo/report.html
```

To view the report, open `~/Pictures/Japan-2026/.studio-photo/report.html` in a browser. It's a contact sheet grouped by burst, with rejects hidden by default. `results.csv` in the same folder has every metric, if you want to tune the thresholds.

Pass options after the service name:

```sh
PHOTOS=~/Pictures/Japan-2026 docker compose run --rm culler scan /photos --dry-run
```

| Option | What it does |
|---|---|
| `--dry-run` | Score and write the report, but no sidecars |
| `--force` | Overwrite `.xmp` files that already exist (by default they're left alone, because they may hold your Capture One edits) |
| `--blur-floor 60` | Raise to reject more soft frames, lower to keep more |
| `--burst-seconds 2` | The maximum gap between frames that still count as one burst |

## Bring the results into Capture One

1. Run the scan **before** importing, so the sidecars are already there.
2. In Capture One, open **Preferences → Image → Metadata** and make sure **Auto Sync Sidecar XMP** is set to **Load** or **Full Sync**.
3. Import the folder. Then filter by color label (Green), or by rating (3★ and up) to start with the best frames.

If you already imported the folder, select the images and choose **Image → Sync Metadata**.

## How scoring works

All metrics run on the JPEG preview embedded in each ARW, scaled down to 1024 px. The full RAW is never decoded, which is what keeps the scan fast on a laptop CPU. Docker on macOS can't use the Apple GPU, so nothing here needs one.

- **Focus.** Measured as Laplacian variance on the sharpest tile of a 4×4 grid, so a sharp subject against a blurred background still counts as in focus. A frame is rejected below `--blur-floor`, or when it's below 20% of the shoot's median focus.
- **Exposure.** Measured from the share of clipped highlights and shadows, plus mean brightness.
- **Blinks.** OpenCV face detection, then a check for open eyes in each face. A face with no open eye costs points but never rejects a photo on its own.
- **Bursts.** Frames taken within 2 seconds of each other that also look alike (perceptual hash) form a group. The highest-scoring frame of each group gets green, the rest get yellow.

The score is 60% focus, 30% exposure and 10% eyes. Stars rank the keepers against each other: the top 10% get 5★, the next 20% 4★, the next 40% 3★, and the rest 2★.

## Development

```sh
pip install -r requirements-dev.txt
python -m culler scan ~/Pictures/some-trip --dry-run
pytest
```

## Roadmap

1. **Culling engine.** This POC.
2. **Review web app.** Browse bursts in the browser, override picks with the keyboard, and load folders from a cloud drive.
3. **Social media helper.** Captions built from EXIF and location, plus carousel and grid layout templates.
4. **Learns your taste.** Train on your keep and reject choices and your Capture One ratings, so the ranking gets more personal over time.
