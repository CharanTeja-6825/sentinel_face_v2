"""Where does a video lose its faces, and what should the thresholds be?

Two jobs in one script, because they read the same run:

1. PER-FRAME DIAGNOSIS — the original job. Replays sample -> detect -> quality ->
   track and prints what happened to every detection. This is the tool that found
   D9 (a 1100 px close-up rejected `too_blurry` on 9 of 10 frames, dropping the
   track below `min_crops_per_track`, and the session reported zero detections
   with no error anywhere).

2. CALIBRATION REPORT — spec §24. config/thresholds.yaml says at the top that
   every value in it is a starting value requiring calibration, and none of them
   have been measured against real classroom footage. This prints the
   distributions those numbers should be set from: where the face widths actually
   land, what the blur and brightness spreads look like, which gate is doing the
   rejecting, and how much evidence a track really accumulates.

   It also answers the one open question this phase introduced. A track's
   embedding is now the mean of its best `observation.max_per_track` looks rather
   than the mean of every accepted look (spec §10, §29.5). That should be neutral
   or better — low-quality observations no longer dilute the aggregate — but
   "should be" is not a measurement, so the report prints the cosine between the
   two means per track. Read it as:

       >= 0.99   the buffer changes nothing; the cap is comfortable
       0.98-0.99 fine, but worth watching
       <  0.98   raise observation.max_per_track — the discarded observations
                 were carrying real information

Usage: python scripts/diagnose_video.py /storage/videos/<id>.mov [--quiet]

NOTE: unlike the pipeline, this script deliberately keeps every accepted aligned
crop, because the all-crops baseline cannot be computed otherwise. That is fine
for a tool you run on purpose against one video; it is exactly what the pipeline
must not do (§29.8).
"""

from __future__ import annotations

import sys
from collections import Counter

import cv2
import numpy as np

from app.config import settings
from app.services import face_engine, quality
from app.utils.tracking import FaceObservation, IoUTracker
from app.workers import video_pipeline

path = sys.argv[1]
quiet = "--quiet" in sys.argv[2:]

cap = cv2.VideoCapture(path)
print(
    "video:", path,
    "| fps", round(cap.get(cv2.CAP_PROP_FPS), 2),
    "| frames", int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
    "| size", int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
    "x", int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
)
cap.release()

engine = face_engine.load_engine()
vcfg, qcfg, mcfg = settings.video, settings.quality, settings.matching
ocfg = settings.observation

print(f"det_size={vcfg.det_size} tiling_at_dim>={video_pipeline.TILING_MIN_DIM}")
print(f"min_face_width_px={qcfg.min_face_width_px} min_det_score={qcfg.min_det_score} "
      f"min_blur_variance={qcfg.min_blur_variance} max_yaw={qcfg.max_yaw_ratio} "
      f"max_pitch={qcfg.max_pitch_ratio}")
print(f"brightness=[{qcfg.min_brightness}, {qcfg.max_brightness}] "
      f"bands: <{qcfg.min_face_width_px} UNUSABLE / <{ocfg.band_medium_px} LOW / "
      f"<{ocfg.band_high_px} MEDIUM / >= HIGH")
print(f"track_min_hits={vcfg.track_min_hits} min_crops_per_track={mcfg.min_crops_per_track} "
      f"max_per_track={ocfg.max_per_track}")
print()

tracker = IoUTracker(
    iou_threshold=vcfg.track_iou_threshold,
    max_age=vcfg.track_max_age_frames,
    min_hits=vcfg.track_min_hits,
)

reasons: Counter[str] = Counter()
bands: Counter[str] = Counter()
widths: list[float] = []
scores: list[float] = []
blurs: list[float] = []
brightnesses: list[float] = []
asymmetries: list[float] = []
clippings: list[float] = []
n_frames = 0

# track.id -> every accepted aligned crop, for the all-crops baseline only.
all_crops: dict[int, list[np.ndarray]] = {}

for ts, frame in video_pipeline.sample_frames(path, vcfg.sample_fps):
    n_frames += 1
    dets = video_pipeline.detect_frame(engine, frame)
    associations = tracker.update(dets, ts)

    line = f"t={ts:6.2f}s dets={len(dets):2d}"
    for track, det in associations:
        w = float(det.bbox[2] - det.bbox[0])
        widths.append(w)

        # `det` is passed straight to the gate — Detection already carries the
        # .bbox / .kps / .det_score it reads.
        r = quality.assess(det, frame, qcfg)
        track.record(r)
        reasons[r.reason or "ACCEPTED"] += 1
        bands[quality.resolution_band(w)] += 1

        if r.accepted:
            scores.append(r.quality_score)
            blurs.append(float(r.detail["blur"]))
            brightnesses.append(float(r.detail["brightness"]))
            asymmetries.append(float(r.detail["luma_asymmetry"]))
            clippings.append(float(r.detail["clipped_fraction"]))

            aligned = engine.align(frame, det.kps)
            all_crops.setdefault(track.id, []).append(aligned)
            track.offer(
                r.quality_score,
                FaceObservation(timestamp_s=ts, quality=r, aligned=aligned),
                ocfg.max_per_track,
            )

        yaw, pitch = quality.pose_ratios(det.kps)
        line += (f" | w={w:5.0f} det={det.det_score:.2f} "
                 f"yaw={yaw:+.2f} pitch={pitch:+.2f} -> {r.reason or 'ok'}")

    if not quiet:
        print(line)

tracks = tracker.finish()


def pct(values: list[float], label: str, fmt: str = "6.1f") -> None:
    """p5/p25/p50/p75/p95 — the shape, not just the extremes.

    A median alone cannot tell you whether a threshold is cutting the tail or the
    body of the distribution, which is the only question that matters when setting
    one.
    """
    if not values:
        print(f"  {label:<18}: (none)")
        return
    p = np.percentile(values, [5, 25, 50, 75, 95])
    print(
        f"  {label:<18}: p5 {p[0]:{fmt}}  p25 {p[1]:{fmt}}  p50 {p[2]:{fmt}}  "
        f"p75 {p[3]:{fmt}}  p95 {p[4]:{fmt}}   (n={len(values)})"
    )


print()
print("═" * 78)
print("CALIBRATION REPORT — every threshold below is UNCALIBRATED until set from this")
print("═" * 78)
print(f"sampled frames   : {n_frames}")
print(f"detections       : {len(widths)}")
print()
print("DISTRIBUTIONS (accepted observations, except face width = all detections)")
pct(widths, "face width px")
pct(scores, "quality score", "6.3f")
pct(blurs, "blur variance")
pct(brightnesses, "brightness")
pct(asymmetries, "luma asymmetry", "6.3f")
pct(clippings, "clipped fraction", "6.3f")
print()
print("GATE OUTCOMES — which threshold is doing the rejecting")
total = sum(reasons.values()) or 1
for reason, count in reasons.most_common():
    print(f"  {reason:<28}: {count:6d}  ({100.0 * count / total:5.1f}%)")
print()
print("RESOLUTION BANDS (§19) — is this a threshold problem or a camera problem?")
for band in (quality.BAND_HIGH, quality.BAND_MEDIUM, quality.BAND_LOW, quality.BAND_UNUSABLE):
    count = bands.get(band, 0)
    print(f"  {band:<28}: {count:6d}  ({100.0 * count / total:5.1f}%)")
print()

print(f"TRACKS: {len(tracks)} confirmed (min_hits={vcfg.track_min_hits})")
dropped = 0
deltas: list[float] = []
for t in tracks:
    kept = t.observations()
    every = all_crops.get(t.id, [])
    note = ""
    if len(kept) < mcfg.min_crops_per_track:
        dropped += 1
        note = "  <- DROPPED, below min_crops_per_track"

    delta = ""
    # The §10 buffer check. Only meaningful once the buffer actually evicted
    # something; below the cap the two means are the same vectors.
    if len(every) > len(kept) >= 1:
        embeddings_all = engine.embed_aligned(every)
        embeddings_best = engine.embed_aligned([o.aligned for o in kept])
        mean_all = embeddings_all.mean(axis=0)
        mean_best = embeddings_best.mean(axis=0)
        mean_all /= np.linalg.norm(mean_all) + 1e-12
        mean_best /= np.linalg.norm(mean_best) + 1e-12
        cosine = float(np.dot(mean_all, mean_best))
        deltas.append(cosine)
        delta = f"  cos(all={len(every)}, best={len(kept)})={cosine:.4f}"

    print(
        f"  track {t.id}: {t.observation_count:4d} observations, "
        f"{len(kept)} retained  {t.first_seen_s:6.1f}s..{t.last_seen_s:6.1f}s"
        f"{delta}{note}"
    )
    if t.reject_reasons:
        print(f"           rejected: {dict(t.reject_reasons)}")

print()
print(f"tracks dropped below min_crops_per_track: {dropped} of {len(tracks)}")
if deltas:
    worst = min(deltas)
    print(f"best-{ocfg.max_per_track} vs all-crops cosine: "
          f"min {worst:.4f} / median {np.median(deltas):.4f}  (n={len(deltas)})")
    if worst < 0.98:
        print(f"  ^ below 0.98 — RAISE observation.max_per_track above "
              f"{ocfg.max_per_track}; the discarded observations carried real signal")
    else:
        print(f"  ^ the {ocfg.max_per_track}-observation cap is not costing accuracy here")
else:
    print(f"best-K vs all-crops: no track exceeded the cap of {ocfg.max_per_track}, "
          "so the buffer discarded nothing and there is nothing to compare")
