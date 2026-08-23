"""Where does a video lose its faces? — run each stage, print what survives.

Usage: python scripts/diagnose_video.py /storage/videos/<id>.mov
"""

from __future__ import annotations

import sys
from collections import Counter

import cv2
import numpy as np

from app.config import settings
from app.services import face_engine, quality
from app.utils.tracking import IoUTracker
from app.workers import video_pipeline

path = sys.argv[1]
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
print(f"det_size={vcfg.det_size} tiling_at_dim>={video_pipeline.TILING_MIN_DIM}")
print(f"min_face_width_px={qcfg.min_face_width_px} min_det_score={qcfg.min_det_score} "
      f"min_blur_variance={qcfg.min_blur_variance} max_yaw={qcfg.max_yaw_ratio} "
      f"max_pitch={qcfg.max_pitch_ratio}")
print(f"track_min_hits={vcfg.track_min_hits} min_crops_per_track={mcfg.min_crops_per_track}")
print()

tracker = IoUTracker(
    iou_threshold=vcfg.track_iou_threshold,
    max_age=vcfg.track_max_age_frames,
    min_hits=vcfg.track_min_hits,
)

reasons: Counter[str] = Counter()
widths: list[float] = []
n_frames = 0

for ts, frame in video_pipeline.sample_frames(path, vcfg.sample_fps):
    n_frames += 1
    dets = video_pipeline.detect_frame(engine, frame)
    line = f"t={ts:6.2f}s dets={len(dets):2d}"
    for d in dets:
        w = float(d.bbox[2] - d.bbox[0])
        widths.append(w)
        face = video_pipeline._CropFace(
            bbox=d.bbox, kps=d.kps, det_score=d.det_score
        )
        r = quality.assess(face, frame, qcfg)
        reasons[r.reason or "ACCEPTED"] += 1
        yaw, pitch = quality.pose_ratios(d.kps)
        line += (f" | w={w:5.0f} det={d.det_score:.2f} "
                 f"yaw={yaw:+.2f} pitch={pitch:+.2f} -> {r.reason or 'ok'}")
    print(line)
    tracker.update(dets, ts)

tracks = tracker.finish()
print()
print(f"sampled frames   : {n_frames}")
print(f"detections       : {len(widths)}")
if widths:
    print(f"face width px    : min {min(widths):.0f} / median {np.median(widths):.0f} / max {max(widths):.0f}")
print(f"quality outcomes : {dict(reasons)}")
print(f"tracks emitted   : {len(tracks)} (min_hits={vcfg.track_min_hits})")
for t in tracks:
    print(f"  track {t.id}: {len(t.crops)} crops  {t.first_seen_s:.1f}s..{t.last_seen_s:.1f}s")
