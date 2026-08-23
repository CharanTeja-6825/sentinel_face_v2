"""Module B — the video pipeline — INIT.md §8.

    [1] decode + sample   [2] detect      [3] track
    [4] quality gate      [5] embed       [6] track aggregate
    [7] cluster           [8] assign      [9] band + persist

The two steps that matter more than they look (§8.2):

* Step 6, track aggregation, is where most of the accuracy comes from. A single
  back-row frame gives a marginal embedding; the mean of thirty crops of the
  same person routinely matches when no individual frame would. This is the
  temporal-union principle — a student only has to be clearly visible
  occasionally (§1.2).
* Step 7, clustering, exists because trackers fragment. Someone who turns away
  or is briefly occluded gets a new track_id on return. Without merging, one
  student becomes four tracks and the one-to-one assignment in step 8 marks
  three of them as unknown intruders (§14.5).
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import cv2
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import (
    AttendanceDecision,
    AttendanceSession,
    Observation,
    Track as TrackRow,
    UnmatchedFace,
)
from app.services import gallery_service, quality
from app.services.face_engine import FaceEngine, load_engine
from app.services.roster_service import get_roster
from app.utils import storage
from app.utils.tracking import Detection, IoUTracker

log = logging.getLogger(__name__)

# Above this source dimension, a single det_size resize shrinks back-row faces
# below detectability, so the frame is tiled instead (§8.3, §14.4).
#
# Measured on the LONGER side, not the width: phones shoot 4K portrait, which
# arrives as 2160x3840. Testing width alone let a genuine 4K source through
# untiled purely because it was held upright.
TILING_MIN_DIM = 3000


# ───────────────────────── [1] decode + sample ─────────────────────────


def sample_frames(video_path: str, sample_fps: float) -> Iterator[tuple[float, np.ndarray]]:
    """Yield (timestamp_s, frame) at the configured rate.

    Uses grab() for skipped frames and retrieve() only on kept ones — roughly a
    10x decode speedup on a long video versus decoding everything and throwing
    most of it away (§8.3).
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video {video_path!r} — is it a valid file?")
    try:
        native_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        if not np.isfinite(native_fps) or native_fps <= 0:
            native_fps = 25.0
        stride = max(1, int(round(native_fps / sample_fps)))

        idx = 0
        while True:
            ok = cap.grab()
            if not ok:
                break
            if idx % stride == 0:
                ok, frame = cap.retrieve()
                if not ok:
                    break
                yield idx / native_fps, frame
            idx += 1
    finally:
        cap.release()


def video_duration_s(video_path: str) -> float:
    cap = cv2.VideoCapture(video_path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        return float(frames / fps) if fps > 0 else 0.0
    finally:
        cap.release()


# ───────────────────────────── [2] detect ──────────────────────────────


def _nms(boxes: np.ndarray, kps: np.ndarray, thresh: float = 0.4):
    """Merge overlapping detections from adjacent tiles."""
    if len(boxes) == 0:
        return boxes, kps
    order = np.argsort(-boxes[:, 4])
    keep = []
    while order.size:
        i = order[0]
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(boxes[i, 0], boxes[rest, 0])
        yy1 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xx2 = np.minimum(boxes[i, 2], boxes[rest, 2])
        yy2 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        area_i = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        area_r = (boxes[rest, 2] - boxes[rest, 0]) * (boxes[rest, 3] - boxes[rest, 1])
        ovr = inter / np.maximum(area_i + area_r - inter, 1e-6)
        order = rest[ovr < thresh]
    keep = np.asarray(keep, dtype=int)
    return boxes[keep], kps[keep]


def detect_frame(engine: FaceEngine, frame: np.ndarray) -> list[Detection]:
    """Detect faces, tiling the frame when the source is 4K-class.

    SCRFD resizes input to det_size. On a 4K source with a small det_size, a
    back-row face shrinks below detectability before the detector ever sees it
    (§8.3, §14.4).
    """
    height, width = frame.shape[:2]

    if max(width, height) >= TILING_MIN_DIM:
        boxes_all, kps_all = [], []
        # 2x2 tiles at 60% of each dimension, so adjacent tiles overlap by 20%
        # and a face sitting on a seam is whole in at least one of them.
        tile_w, tile_h = int(width * 0.6), int(height * 0.6)
        for oy in (0, height - tile_h):
            for ox in (0, width - tile_w):
                tile = frame[oy : oy + tile_h, ox : ox + tile_w]
                boxes, kps = engine.detect_only(tile, input_size=engine.det_size)
                if len(boxes):
                    boxes = boxes.copy()
                    boxes[:, [0, 2]] += ox
                    boxes[:, [1, 3]] += oy
                    kps = kps.copy()
                    kps[:, :, 0] += ox
                    kps[:, :, 1] += oy
                    boxes_all.append(boxes)
                    kps_all.append(kps)
            if height - tile_h == 0:
                break
        if not boxes_all:
            return []
        boxes, kps = _nms(np.vstack(boxes_all), np.vstack(kps_all))
    else:
        boxes, kps = engine.detect_only(frame, input_size=engine.det_size)

    return [
        Detection(bbox=b[:4].astype(np.float32), kps=k, det_score=float(b[4]))
        for b, k in zip(boxes, kps)
    ]


# ─────────────────── [4]-[6] quality, embed, aggregate ─────────────────


@dataclass
class TrackSummary:
    track_index: int
    embedding: np.ndarray          # mean of surviving crops, re-normalised
    first_seen_s: float
    last_seen_s: float
    crop_count: int
    mean_quality: float
    best_crop: np.ndarray          # aligned 112x112 image of the best crop
    best_quality: float


def summarise_track(
    engine: FaceEngine,
    track,
    index: int,
    frames: dict[float, np.ndarray],
) -> TrackSummary | None:
    """Quality-gate a track's crops, embed the survivors, average them."""
    cfg = settings.matching

    aligned, qualities = [], []
    for crop in track.crops:
        frame = frames.get(crop.timestamp_s)
        if frame is None:
            continue

        # Same quality gate as enrolment — one implementation, one behaviour.
        face = _CropFace(crop.bbox, crop.kps, crop.det_score)
        result = quality.assess(face, frame)
        if not result.accepted:
            continue

        aligned.append(engine.align(frame, crop.kps))
        qualities.append(result.quality_score)

    # §5.1 min_crops_per_track — a track with too little evidence is dropped
    # rather than guessed at.
    if len(aligned) < cfg.min_crops_per_track:
        return None

    embeddings = engine.embed_aligned(aligned)

    # Step 6: mean embedding, re-normalised. This is where most of the accuracy
    # comes from (§8.2).
    mean = embeddings.mean(axis=0)
    mean = mean / (np.linalg.norm(mean) + 1e-12)

    best = int(np.argmax(qualities))
    return TrackSummary(
        track_index=index,
        embedding=mean.astype(np.float32),
        first_seen_s=track.first_seen_s,
        last_seen_s=track.last_seen_s,
        crop_count=len(aligned),
        mean_quality=float(np.mean(qualities)),
        best_crop=aligned[best],
        best_quality=float(qualities[best]),
    )


class _CropFace:
    """Adapter so quality.assess() can score a tracked detection."""

    __slots__ = ("bbox", "kps", "det_score")

    def __init__(self, bbox, kps, det_score):
        self.bbox = bbox
        self.kps = kps
        self.det_score = det_score


# ──────────────────────────── [7] cluster ──────────────────────────────


def cluster_tracks(summaries: list[TrackSummary]) -> np.ndarray:
    """Merge fragmented tracks of the same person (§8.2 step 7)."""
    if not summaries:
        return np.zeros((0,), dtype=int)
    if len(summaries) == 1:
        return np.zeros((1,), dtype=int)

    X = np.vstack([s.embedding for s in summaries])
    labels = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=settings.matching.cluster_distance,
        metric="cosine",
        linkage="average",
    ).fit_predict(X)
    return labels


# ───────────────────────────── the pipeline ────────────────────────────


@dataclass
class PipelineResult:
    frames_sampled: int
    detections: int
    tracks: list[TrackSummary]
    labels: np.ndarray
    cluster_embeddings: np.ndarray
    processing_ms: int


def run_pipeline(
    session: AttendanceSession, db: Session, progress_every: int = 25
) -> PipelineResult:
    started = time.monotonic()
    cfg_video = settings.video

    engine = load_engine(det_size=tuple(cfg_video.det_size))
    tracker = IoUTracker(
        iou_threshold=cfg_video.track_iou_threshold,
        max_age=cfg_video.track_max_age_frames,
        min_hits=cfg_video.track_min_hits,
    )

    frames: dict[float, np.ndarray] = {}
    frames_sampled = 0
    detections_total = 0

    for timestamp_s, frame in sample_frames(session.video_path, cfg_video.sample_fps):
        detections = detect_frame(engine, frame)
        detections_total += len(detections)
        frames[timestamp_s] = frame
        tracker.update(detections, timestamp_s)
        frames_sampled += 1

        # §8.7 — real progress for the UI, not an unresponsive spinner.
        if frames_sampled % progress_every == 0:
            session.frames_sampled = frames_sampled
            db.commit()

    tracks = tracker.finish()
    log.info(
        "sampled %d frames, %d detections, %d confirmed tracks",
        frames_sampled, detections_total, len(tracks),
    )

    summaries = []
    for i, track in enumerate(tracks):
        summary = summarise_track(engine, track, i, frames)
        if summary is not None:
            summaries.append(summary)

    labels = cluster_tracks(summaries)

    # One embedding per cluster: quality-weighted mean of its tracks.
    cluster_embeddings = []
    for label in sorted(set(labels.tolist())):
        members = [s for s, l in zip(summaries, labels) if l == label]
        weights = np.array([max(s.crop_count, 1) for s in members], dtype=np.float32)
        stack = np.vstack([s.embedding for s in members])
        mean = (stack * weights[:, None]).sum(axis=0) / weights.sum()
        cluster_embeddings.append(mean / (np.linalg.norm(mean) + 1e-12))

    return PipelineResult(
        frames_sampled=frames_sampled,
        detections=detections_total,
        tracks=summaries,
        labels=labels,
        cluster_embeddings=(
            np.vstack(cluster_embeddings).astype(np.float32)
            if cluster_embeddings
            else np.zeros((0, 512), np.float32)
        ),
        processing_ms=int((time.monotonic() - started) * 1000),
    )


# ─────────────────────── [9] band + persist (§8.6) ─────────────────────


def persist(session: AttendanceSession, db: Session, result: PipelineResult) -> None:
    model_version = FaceEngine.MODEL_VERSION
    roster = get_roster(db, session.section_id)
    gallery = gallery_service.load_roster_gallery(db, roster, model_version)

    matches = gallery_service.match_clusters_to_roster(
        result.cluster_embeddings, gallery
    )

    # Persist crops per cluster, then tracks.
    cluster_crops: dict[int, list[str]] = {}
    labels = result.labels.tolist()
    for summary, label in zip(result.tracks, labels):
        rel = storage.save_crop(
            session.id, int(label), summary.track_index, summary.best_crop
        )
        cluster_crops.setdefault(int(label), []).append(rel)
        db.add(
            TrackRow(
                session_id=session.id,
                cluster_id=int(label),
                first_seen_s=summary.first_seen_s,
                last_seen_s=summary.last_seen_s,
                crop_count=summary.crop_count,
                mean_quality=summary.mean_quality,
                best_crop_path=rel,
            )
        )

    present_students: dict[uuid.UUID, float] = {}

    for match in matches:
        cluster_id = match["cluster_id"]
        verdict = gallery_service.band(match["top1_score"], match["margin"])

        db.add(
            Observation(
                session_id=session.id,
                cluster_id=cluster_id,
                top1_student_id=match["top1_student_id"],
                top1_score=match["top1_score"],
                top2_student_id=match["top2_student_id"],
                top2_score=match["top2_score"],
                margin=match["margin"],
                band=verdict,
                crop_paths=cluster_crops.get(cluster_id, []),
                model_version=model_version,
            )
        )

        if verdict == "confident":
            present_students[match["top1_student_id"]] = match["top1_score"]
        elif verdict == "no_match":
            crops = cluster_crops.get(cluster_id, [])
            db.add(
                UnmatchedFace(
                    session_id=session.id,
                    cluster_id=cluster_id,
                    crop_path=crops[0] if crops else "",
                    best_score=match["top1_score"],
                )
            )
        # 'uncertain' deliberately writes no decision — it defaults to absent
        # until faculty says otherwise (§8.6, §14.7).

    # Clusters that got no assignment at all (more faces than roster students)
    # are unmatched people in the room.
    assigned = {m["cluster_id"] for m in matches}
    for cluster_id in sorted({int(l) for l in labels} - assigned):
        crops = cluster_crops.get(cluster_id, [])
        db.add(
            UnmatchedFace(
                session_id=session.id,
                cluster_id=cluster_id,
                crop_path=crops[0] if crops else "",
                best_score=None,
            )
        )

    # Every roster student gets a decision. Absent is the default (§8.6).
    for student in roster:
        decision = "present" if student.id in present_students else "absent"
        db.execute(
            pg_insert(AttendanceDecision)
            .values(
                session_id=session.id,
                student_id=student.id,
                decision=decision,
                source="auto",
                score=present_students.get(student.id),
            )
            # §6 invariant 2 — retried writes must never duplicate.
            .on_conflict_do_update(
                constraint="uq_decision_session_student",
                set_={
                    "decision": decision,
                    "source": "auto",
                    "score": present_students.get(student.id),
                },
            )
        )

    session.detected_count = int(len(set(labels)))
    session.expected_count = len(roster)
    session.frames_sampled = result.frames_sampled
    session.processing_ms = result.processing_ms
    session.model_version = model_version
    db.commit()


def reset_session_results(session_id: uuid.UUID, db: Session) -> None:
    """Make reprocessing idempotent — §8.7.

    Observations are append-only *within* a run (§6 invariant 1); a re-run
    replaces the previous run's rows wholesale rather than mutating them, so a
    retried job never double-writes.
    """
    for model in (Observation, TrackRow, UnmatchedFace):
        db.execute(delete(model).where(model.session_id == session_id))
    db.execute(
        delete(AttendanceDecision).where(
            AttendanceDecision.session_id == session_id,
            AttendanceDecision.source == "auto",
        )
    )
    db.commit()
    storage.clear_session_crops(session_id)


# ────────────────────────── the RQ job (§8.7) ──────────────────────────


def process_video(session_id: str) -> dict:
    """Entry point enqueued by POST /sessions/{id}/video."""
    sid = uuid.UUID(str(session_id))
    db = SessionLocal()
    try:
        session = db.get(AttendanceSession, sid)
        if session is None:
            raise ValueError(f"Attendance session {sid} not found")

        session.status = "processing"
        session.error_message = None
        db.commit()

        try:
            reset_session_results(sid, db)
            session.video_duration_s = video_duration_s(session.video_path)
            result = run_pipeline(session, db)
            persist(session, db, result)
            session.status = "completed"
            db.commit()
            return {
                "session_id": str(sid),
                "frames_sampled": result.frames_sampled,
                "clusters": int(len(set(result.labels.tolist()))),
                "processing_ms": result.processing_ms,
            }
        except Exception as exc:
            db.rollback()
            session = db.get(AttendanceSession, sid)
            session.status = "failed"
            session.error_message = f"{type(exc).__name__}: {exc}"
            db.commit()
            log.exception("Video processing failed for session %s", sid)
            raise  # let RQ record the failure
    finally:
        db.close()
