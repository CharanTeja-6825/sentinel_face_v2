"""Roster gallery, matching and banding — INIT.md §8.5, §8.6.

This module is where the two accuracy-critical guardrails live:

* §14.2 — the gallery contains ONLY students on this session's roster. Matching
  against the whole student table produces plausible-looking results with a far
  worse error rate and raises nothing. Scoping to ~60 candidates instead of
  ~20,000 is what makes the accuracy acceptable at all (§1.2).
* §14.6 — assignment is GLOBAL and one-to-one (Hungarian), not independent
  best-match. Independent matching lets one student be matched by two different
  faces, which is exactly the proxy-attendance loophole this system exists to
  close.
"""

from __future__ import annotations

import logging
import uuid

import numpy as np
from scipy.optimize import linear_sum_assignment
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import MatchingConfig, settings
from app.models import FaceTemplate, Student

log = logging.getLogger(__name__)


class GalleryError(RuntimeError):
    """Raised when the gallery is not what the roster says it should be."""


def load_roster_gallery(
    db: Session, roster: list[Student], model_version: str
) -> dict[uuid.UUID, np.ndarray]:
    """Templates for roster students only, filtered to one model version.

    §14.1: embeddings from different models are meaningless together and
    nothing raises on their own, so the version filter is applied in the query
    rather than checked afterwards.

    Returns {student_id: (T_i, 512)} containing only students who actually have
    templates. Roster students with none cannot be matched and will be marked
    absent — see DECISIONS.md D7 for why this is not an error.
    """
    roster_ids = [s.id for s in roster]
    if not roster_ids:
        raise GalleryError("Session roster is empty — nothing to match against")

    rows = db.execute(
        select(FaceTemplate.student_id, FaceTemplate.embedding).where(
            FaceTemplate.student_id.in_(roster_ids),
            FaceTemplate.model_version == model_version,
            # Individual per-angle templates AND the centroid are both usable;
            # scoring takes a max over all of them (§8.5).
        )
    ).all()

    gallery: dict[uuid.UUID, list[np.ndarray]] = {}
    for student_id, embedding in rows:
        gallery.setdefault(student_id, []).append(
            np.asarray(embedding, dtype=np.float32)
        )

    stacked = {sid: np.vstack(vs) for sid, vs in gallery.items()}

    # §8.5 / DECISIONS.md D7 — the guarantee is that the gallery never reaches
    # outside the roster, and covers exactly the enrolled part of it.
    if not set(stacked).issubset(set(roster_ids)):
        raise GalleryError(
            "Gallery contains students outside the session roster — "
            "this would silently destroy accuracy"
        )

    log.info(
        "gallery=%d enrolled=%d roster=%d model_version=%s",
        len(stacked), len(stacked), len(roster_ids), model_version,
    )
    if not stacked:
        raise GalleryError(
            f"No face templates for any of the {len(roster_ids)} roster students "
            f"at model_version {model_version!r}. Enrol students before "
            "processing video."
        )
    return stacked


def match_clusters_to_roster(
    cluster_embeddings: np.ndarray, gallery: dict[uuid.UUID, np.ndarray]
) -> list[dict]:
    """Assign clusters to students, one-to-one.

    cluster_embeddings : (C, 512) L2-normalised
    gallery            : student_id -> (T_i, 512) all their templates
    """
    student_ids = list(gallery.keys())
    if len(cluster_embeddings) == 0 or not student_ids:
        return []

    # Score = MAX over that student's templates, not the centroid.
    # Multi-angle enrolment exists precisely so a side view can match a
    # side-view template; averaging would destroy that (§8.5).
    S = np.zeros((len(cluster_embeddings), len(student_ids)), dtype=np.float32)
    for j, sid in enumerate(student_ids):
        S[:, j] = (cluster_embeddings @ gallery[sid].T).max(axis=1)

    # Global one-to-one assignment (§14.6).
    rows, cols = linear_sum_assignment(-S)

    results = []
    for r, c in zip(rows, cols):
        order = np.argsort(-S[r])
        top1 = int(order[0])
        top2 = int(order[1]) if len(order) > 1 else None
        score = float(S[r, top1])
        second = float(S[r, top2]) if top2 is not None else 0.0

        # The assignment may hand this cluster a student that is not its own
        # argmax — that is the point of a global solution. Report the assigned
        # student as top1 so the decision and the evidence agree.
        assigned = int(c)
        assigned_score = float(S[r, assigned])
        if assigned != top1:
            second = score
            top1, score = assigned, assigned_score

        results.append(
            {
                "cluster_id": int(r),
                "top1_student_id": student_ids[top1],
                "top1_score": score,
                "top2_student_id": student_ids[top2] if top2 is not None else None,
                "top2_score": second,
                "margin": score - second,
            }
        )
    return results


def band(score: float, margin: float, cfg: MatchingConfig | None = None) -> str:
    """confident | uncertain | no_match — §8.6.

    Uncertain entries default to ABSENT if faculty does nothing. A false absent
    is corrected in three seconds by a student sitting in the room; a false
    present is invisible and enables proxy attendance. Never default the other
    way (§14.7).
    """
    cfg = cfg or settings.matching
    if score >= cfg.t_high and margin >= cfg.margin_min:
        return "confident"          # -> present, source='auto'
    if score >= cfg.t_low:
        return "uncertain"          # -> shown to faculty, defaults to absent
    return "no_match"               # -> unmatched_faces
