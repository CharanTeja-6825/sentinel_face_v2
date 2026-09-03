"""Live single-frame identification — the Live Test screen.

This module exists so the recognition half of the system can be *seen working*
without uploading a video and waiting on the RQ worker. It answers one question:
"if this webcam frame were a frame of classroom footage, who would the system
say these faces are, and how sure would it be?"

**It is read-only.** No attendance session, decision, track, crop or template is
written. A test screen that quietly marked someone present would be worse than
no test screen at all.

Every step below is the VIDEO path, not the enrolment path — `detect_frame`,
`quality.assess`, `align`/`embed_aligned`, the roster-scoped gallery, and the
same Hungarian assignment and banding that `video_pipeline.persist` runs. That
is the whole point: a pass here is evidence about attendance, not about a
parallel code path that happens to resemble it.

Two things the video pipeline does that a single frame cannot: tracking across
frames, and clustering several looks at one face into one identity. So a live
score is the pessimistic case — one look, no aggregation — and a name that
appears here would appear at least as confidently in a real run.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Section, Student
from app.services import gallery_service, quality, roster_service
from app.services.face_engine import FaceEngine, get_engine
from app.services.gallery_service import GalleryError

log = logging.getLogger(__name__)


def identify_frame(db: Session, image: str, section_code: str) -> dict:
    """Detect every face in one frame and name the ones the roster can name."""
    # Imported here, not at module scope: the worker module pulls sklearn and RQ,
    # and the API process should not pay for them unless somebody opens this page.
    # ponytail: reusing detect_frame rather than calling engine.detect_only keeps
    # the 4K tiling rule identical to attendance. Move detect_frame + _nms down
    # into face_engine if this import ever becomes a startup cost.
    from app.services.enrolment_service import decode_data_url
    from app.workers.video_pipeline import detect_frame

    section = db.scalar(select(Section).where(Section.code == section_code))
    if section is None:
        raise HTTPException(404, f"Unknown section {section_code!r}")

    roster = roster_service.get_roster(db, section.id)
    try:
        gallery = gallery_service.load_roster_gallery(db, roster, FaceEngine.MODEL_VERSION)
    except GalleryError as exc:
        # Empty roster, or nobody in it has enrolled. Both messages are already
        # written for a human to read.
        raise HTTPException(422, str(exc)) from None

    frame = decode_data_url(image)
    engine = get_engine()
    detections = detect_frame(engine, frame)

    faces: list[dict] = []
    embeddable: list[int] = []          # indices into `faces`, in detection order
    for det in detections:
        result = quality.assess(det, frame)
        faces.append(
            {
                "bbox": [float(v) for v in det.bbox],
                "accepted": result.accepted,
                # Raw code. The frontend owns the friendly text (ARCHITECTURE §11).
                "reason": result.reason,
                "quality_score": round(result.quality_score, 3),
                "band": None,
                "roll_no": None,
                "name": None,
                "score": None,
                "margin": None,
                "runner_up_roll": None,
            }
        )
        if result.accepted:
            embeddable.append(len(faces) - 1)

    if embeddable:
        crops = [engine.align(frame, detections[i].kps) for i in embeddable]
        embeddings = engine.embed_aligned(crops)
        by_id = {s.id: s for s in roster}

        # Global one-to-one, exactly as §14.6 requires — two people in frame can
        # never both be named as the same student, which is the loophole the
        # whole system exists to close.
        for m in gallery_service.match_clusters_to_roster(embeddings, gallery):
            face = faces[embeddable[m["cluster_id"]]]
            verdict = gallery_service.band(m["top1_score"], m["margin"])
            student: Student | None = by_id.get(m["top1_student_id"])
            runner_up: Student | None = by_id.get(m["top2_student_id"])

            face["band"] = verdict
            face["score"] = round(m["top1_score"], 3)
            face["margin"] = round(m["margin"], 3)
            # A no_match has a top-1, but naming it would invite reading a
            # rejected guess as an answer.
            if verdict != "no_match" and student is not None:
                face["roll_no"] = student.roll_no
                face["name"] = student.name
            if runner_up is not None:
                face["runner_up_roll"] = runner_up.roll_no

    cfg = settings.matching
    return {
        "section": section_code,
        "faces": faces,
        "roster_size": len(roster),
        "gallery_size": len(gallery),
        # Echoed so the screen can show the arithmetic — "0.62 >= 0.60, margin
        # 0.14 >= 0.10 -> confident" — instead of an unexplained verdict.
        "thresholds": {
            "t_high": cfg.t_high,
            "t_low": cfg.t_low,
            "margin_min": cfg.margin_min,
        },
    }
