# studio-prioritizer

Pre-culls a travel shoot so you only look at the photos worth editing.

Point it at a folder of Sony `.ARW` (or JPEG) files. If you shoot RAW+JPEG, only the ARW is scored, even when the JPEGs sit in a different folder. It scores every frame and flags the ones you can't rescue: out of focus, or an empty frame (lens cap, pocket shot). It also marks near-copies of a better frame in the same burst. Then it writes an XMP sidecar next to each photo, which Capture One reads as star ratings and color labels.

Exposure problems are **noted but never held against a photo**, because a RAW that's too bright or too dark is fixed in seconds in Capture One. Those photos keep their rank and get an `overexposed` or `underexposed` keyword, so you can find them quickly.

Nothing is moved or deleted. The sidecars and a report are the only files it writes.

| Label | Meaning | Stars |
|---|---|---|
| 🟢 Green | Keeper, the best frame of its burst | 2–5, by score across the whole shoot |
| 🟡 Yellow | Fine, but a better near-identical frame exists | at most 2 |
| 🔴 Red | Reject: out of focus or an empty frame | 1 |

Each sidecar also adds keywords such as `studio-photo/reject`, `studio-photo/blurry` and `studio-photo/underexposed`, so you can filter on the reason in Capture One.

## Run it with Docker (macOS)

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```sh
git clone https://github.com/sc0210/studio-prioritizer && cd studio-prioritizer
PHOTOS=~/Pictures/Japan-2026 docker compose run --build --rm culler
```

`--build` rebuilds the image whenever the code has changed, so a `git pull` takes effect straight away. The first build takes a few minutes, and later ones are near-instant when nothing changed. A scan prints a summary and the path of the report:

```
Scoring 1843 photos from /photos ...
Done in 212s: 611 picks, 742 similar shots, 490 rejects.
XMP sidecars written: 1843
Report: /photos/.studio-photo/report.html
```

To view the report, open `~/Pictures/Japan-2026/.studio-photo/report.html` in a browser. The report includes:

- **Rank:** every non-rejected photo gets a rank (#1 is the strongest of the trip). A **Top 10 / 25 / 50 / 100** filter jumps straight to the best photos.
- **Filters:** by pick, similar or reject, by file type (ARW or JPG), by minimum stars, or by note (needs exposure fix, possible blink). You can also search by file name.
- **One per burst:** shows only the best frame of each burst. The viewer shows the other frames in a strip.
- **Viewer:** click a photo for a large preview with its EXIF data, and use ← → to step through. **Focus area** (`F`) outlines where the focus score was measured. **Fix exposure** (`E`) previews a dark or bright shot with its exposure evened out.
- **Compare:** tick 2 to 4 photos (or press `C`) to see them side by side.
- **Day headers:** when sorted by time, photos are grouped under the day they were taken.
- **Copy names:** puts the file names in the current view on the clipboard.

Press `?` in the report for all shortcuts. Your filter settings are remembered between visits.

Pass options after the service name:

```sh
PHOTOS=~/Pictures/Japan-2026 docker compose run --build --rm culler scan /photos --dry-run
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

- **Focus.** Measured as Laplacian variance on the sharpest tile of a 4×4 grid, so a sharp subject against a blurred background still counts as in focus. The tones are stretched first, as if the exposure were already fixed, so a dark but sharp frame isn't mistaken for a blurry one. A frame is rejected below `--blur-floor`, or when it's below 20% of the shoot's median focus.
- **Exposure.** Measured from the share of clipped highlights and shadows, plus mean brightness. It only adds a note and doesn't change the score.
- **Blinks.** Faces are found with [YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet), a small neural face detector (MIT licensed, bundled in `culler/models/`). Each eye is then checked for being open. A face with no open eye costs points but never rejects a photo on its own. Faces that are tiny in the frame are ignored.
- **Bursts.** Frames taken within 2 seconds of each other that also look alike (perceptual hash) form a group. The highest-scoring frame of each group gets green, the rest get yellow.

The score is 85% focus and 15% eyes. Stars rank the keepers against each other: the top 10% get 5★, the next 20% 4★, the next 40% 3★, and the rest 2★.

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
