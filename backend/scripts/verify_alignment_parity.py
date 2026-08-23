#!/usr/bin/env python
"""Measure whether MediaPipe-aligned and SCRFD-aligned embeddings are comparable — D12.

WHY THIS EXISTS. Enrolment now aligns with MediaPipe's iris/nose/mouth landmarks while
the video pipeline still aligns with SCRFD's five keypoints. Both then go through the
same recogniser, so `FaceEngine.MODEL_VERSION` was left unchanged and the two kinds of
row sit in one gallery. That is a claim about the embeddings, and claims about
embeddings get measured, not asserted — bumping MODEL_VERSION instead would orphan
every existing template with no backfill path, so the decision is worth checking.

    python scripts/verify_alignment_parity.py IMAGE [IMAGE ...]
    python scripts/verify_alignment_parity.py --video /storage/videos/foo.mov

PASS is cosine > 0.95 on every face. Below that, stop and choose deliberately: bump
MODEL_VERSION and re-enrol, or keep SCRFD alignment and let MediaPipe supply only pose
and quality.

Also prints landmark span against SCRFD box width, which is what justifies one
`min_face_width_px` meaning the same thing on both paths.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import preprocess  # noqa: E402
from app.services.face_engine import load_engine  # noqa: E402
from app.services.mp_face import load_mediapipe  # noqa: E402

PASS_COSINE = 0.95


def frames(args) -> list[tuple[str, np.ndarray]]:
    out: list[tuple[str, np.ndarray]] = []
    for path in args.images:
        img = cv2.imread(path)
        if img is None:
            print(f"  skip (unreadable): {path}")
            continue
        out.append((Path(path).name, img))
    for path in args.video:
        cap = cv2.VideoCapture(path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        for i in range(0, total, max(1, total // args.samples)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, fr = cap.read()
            if ok:
                out.append((f"{Path(path).stem[:8]}@{i}", fr))
        cap.release()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("images", nargs="*", help="image files to measure")
    ap.add_argument("--video", action="append", default=[], help="sample frames from a video")
    ap.add_argument("--samples", type=int, default=10, help="frames per video")
    args = ap.parse_args()

    if not args.images and not args.video:
        ap.error("give at least one image or --video")

    engine = load_engine()
    mp = load_mediapipe()

    print(f"\n{'frame':20s} {'cosine':>8s} {'lm_span':>8s} {'scrfd_w':>8s} {'ratio':>6s}"
          f" {'yaw':>7s} {'pitch':>7s} {'roll':>7s}")
    print("-" * 78)

    cosines, ratios = [], []
    for tag, frame in frames(args):
        faces = engine.detect(frame)
        if len(faces) != 1:
            print(f"{tag:20s}  skip — SCRFD saw {len(faces)} faces")
            continue

        small, scale = preprocess.fit_to_max_side(frame, 640)
        enhanced, _ = preprocess.enhance(small)
        mp_face = mp.analyse(enhanced)
        if mp_face is None:
            print(f"{tag:20s}  skip — MediaPipe saw no face")
            continue
        mp_face.landmarks = mp_face.landmarks / scale

        from app.services.mp_face import pose_degrees

        yaw, pitch, roll = pose_degrees(mp_face.transform)

        # Same frame, same recogniser, two alignments. Only the 5 points differ.
        a = engine.embed_aligned([engine.align(frame, faces[0].kps)])[0]
        b = engine.embed_aligned([engine.align(frame, mp_face.arcface_kps())])[0]
        cosine = float(np.dot(a, b))

        lm_span = mp_face.width_px
        scrfd_w = float(faces[0].bbox[2] - faces[0].bbox[0])
        ratio = lm_span / scrfd_w if scrfd_w else float("nan")

        cosines.append(cosine)
        ratios.append(ratio)
        print(f"{tag:20s} {cosine:8.4f} {lm_span:8.0f} {scrfd_w:8.0f} {ratio:6.3f}"
              f" {yaw:+7.1f} {pitch:+7.1f} {roll:+7.1f}")

    if not cosines:
        print("\nNo comparable faces found — nothing measured.")
        return 2

    c, r = np.array(cosines), np.array(ratios)
    print("-" * 78)
    print(f"\nALIGNMENT PARITY   n={len(c)}  min={c.min():.4f}  mean={c.mean():.4f}  max={c.max():.4f}")
    print(f"WIDTH RATIO        landmark span / SCRFD box: "
          f"min={r.min():.3f}  mean={r.mean():.3f}  max={r.max():.3f}")

    if c.min() > PASS_COSINE:
        print(f"\nPASS — every face above {PASS_COSINE}. Enrolment and video templates are\n"
              f"comparable; MODEL_VERSION stays as it is.")
        return 0

    print(f"\nFAIL — {int((c <= PASS_COSINE).sum())} face(s) at or below {PASS_COSINE}.\n"
          f"Do not paper over this. Either bump FaceEngine.MODEL_VERSION and re-enrol\n"
          f"every student, or keep SCRFD alignment and use MediaPipe for pose only.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
