"""Quality gate and pose estimation — INIT.md §7.3, §7.4.

Every rejection returns a SPECIFIC reason string. The registration wizard shows
these to the student, and vague reasons make the wizard frustrating (§7.3).

Nothing here hardcodes a threshold — all values come from
config/thresholds.yaml via app.config.settings (§0.6).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from app.config import QualityConfig, settings

# Rejection reasons. The frontend maps these to friendly text (§11); the raw
# codes are the API contract.
NO_FACE = "no_face_detected"
MULTIPLE_FACES = "multiple_faces"
LOW_DETECTION = "low_detection_confidence"
TOO_SMALL = "face_too_small"
TOO_BLURRY = "too_blurry"
POOR_LIGHTING = "poor_lighting"
EXTREME_POSE = "extreme_pose"
TOO_SIMILAR = "too_similar"
# Guided enrolment only — the frame is usable, but not for the angle the
# wizard is currently asking for, or not good enough to become a template.
WRONG_ANGLE = "wrong_angle"
LOW_QUALITY = "low_quality"
# MediaPipe enrolment path only (D12). Newly measurable failures, not restatements:
# a blinked frame passed every gate above and became a permanent template, and roll
# could not be measured at all by the 5-keypoint estimator.
EYES_CLOSED = "eyes_closed"
EXTREME_ROLL = "extreme_roll"
NO_LANDMARKS = "no_landmarks"


@dataclass
class QualityResult:
    accepted: bool
    reason: str | None = None
    quality_score: float = 0.0
    angle: str | None = None
    # On the video path these are the unitless ratios of `pose_ratios()`. On the
    # MediaPipe enrolment path they are DEGREES — `pose_in_degrees` says which, so a
    # reader never has to guess what a "yaw of 0.3" means.
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    pose_in_degrees: bool = False
    detail: dict = field(default_factory=dict)


def _reject(reason: str, **detail) -> QualityResult:
    return QualityResult(accepted=False, reason=reason, detail=detail)


# ───────────────────────────── pose (§7.4) ─────────────────────────────


def pose_ratios(kps) -> tuple[float, float]:
    """Yaw and pitch ratios from InsightFace's 5 landmarks.

    kps order is [left_eye, right_eye, nose, left_mouth, right_mouth] in IMAGE
    coordinates — "left eye" means the eye on the left of the image, which for
    an unmirrored frame is the subject's RIGHT eye. See DECISIONS.md for the
    empirically resolved sign convention (§7.4 sign convention warning).
    """
    le, re, nose, lm, rm = np.asarray(kps, dtype=np.float64)

    # Yaw: horizontal asymmetry of nose between the eyes.
    # Ranges roughly -1 (turned far right) .. +1 (turned far left).
    d_left = nose[0] - le[0]
    d_right = re[0] - nose[0]
    yaw = (d_left - d_right) / (d_left + d_right + 1e-6)

    # Pitch: nose height relative to the eye line and mouth line.
    eye_y = (le[1] + re[1]) / 2
    mouth_y = (lm[1] + rm[1]) / 2
    span = mouth_y - eye_y + 1e-6
    pitch = ((nose[1] - eye_y) / span - 0.5) * 2

    return float(yaw), float(pitch)


def classify_angle(yaw: float, pitch: float) -> str:
    """Bucket into the five coarse classes of §5.1 required_angles.

    A geometric approximation, not true 3D pose estimation — acceptable here
    because we only need five coarse buckets and rejection of extremes (§7.4).
    """
    if abs(yaw) < 0.15 and abs(pitch) < 0.20:
        return "front"
    if yaw >= 0.15:
        return "left"
    if yaw <= -0.15:
        return "right"
    if pitch <= -0.20:
        return "up"
    if pitch >= 0.20:
        return "down"
    return "front"


# ───────────────────────────── sharpness ───────────────────────────────

# The scale the blur metric is measured at. 112 is not arbitrary: it is the
# size ArcFace consumes, so "sharp enough" is judged at the resolution the
# recogniser actually sees.
BLUR_REFERENCE_PX = 112


def blur_variance(gray: np.ndarray) -> float:
    """Variance of the Laplacian, measured at a FIXED crop scale.

    §7.3 says "variance of Laplacian on the crop" without pinning the crop
    size, and that omission matters: the Laplacian is a per-pixel second
    derivative, so the same face photographed larger spreads each edge over
    more pixels and scores LOWER. Measured raw, one real face crop scored 1585
    at 60 px wide and 123 at 600 px wide — a 13x swing with no change in
    sharpness. A single threshold cannot mean anything against a metric that
    moves 13x with subject distance; a 1100 px close-up read "too_blurry"
    while a tiny back-row face sailed through.

    Normalising to a fixed size collapses that to a ~2x spread, in the
    direction that is actually true (a smaller face carries less real detail).
    Measured at this scale, cfg.min_blur_variance = 40.0 sits between a
    visibly-soft face (~120) and an unusable one (~26).
    """
    resized = cv2.resize(
        gray,
        (BLUR_REFERENCE_PX, BLUR_REFERENCE_PX),
        interpolation=cv2.INTER_AREA,
    )
    return float(cv2.Laplacian(resized, cv2.CV_64F).var())


# ──────────────────────── quality score (§7.3) ─────────────────────────


def weighted_score(
    det_score: float,
    width_px: float,
    blur: float,
    yaw: float,
    pitch: float,
    cfg: QualityConfig | None = None,
    pose_n: float | None = None,
) -> float:
    """Composite 0..1 quality score.

    INIT.md §7.3 calls for a weighted_score() but does not define it, so per
    §0.2 this is our choice, logged in DECISIONS.md: each component is
    normalised against its configured threshold, clipped to [0, 1], then
    combined 0.35 detection / 0.25 size / 0.25 sharpness / 0.15 pose
    centrality. Detection confidence and face size dominate because they are
    what actually predict whether the embedding is usable.

    `pose_n` lets a caller supply its own pose-centrality term. The MediaPipe enrolment
    path measures pose in degrees, so normalising it against `max_yaw_ratio` would be
    meaningless. Left as None — which is every existing caller, including the whole
    video path — the behaviour and the output are unchanged.
    """
    cfg = cfg or settings.quality

    det_n = np.clip((det_score - cfg.min_det_score) / (1.0 - cfg.min_det_score), 0, 1)
    # Saturates at 3x the minimum width — beyond that, bigger stops helping.
    size_n = np.clip(
        (width_px - cfg.min_face_width_px) / (2 * cfg.min_face_width_px), 0, 1
    )
    # Saturates at 5x the minimum Laplacian variance.
    blur_n = np.clip(
        (blur - cfg.min_blur_variance) / (4 * cfg.min_blur_variance), 0, 1
    )
    if pose_n is None:
        pose_n = np.clip(
            1.0
            - 0.5 * (abs(yaw) / cfg.max_yaw_ratio + abs(pitch) / cfg.max_pitch_ratio),
            0,
            1,
        )
    else:
        pose_n = np.clip(pose_n, 0, 1)

    return float(0.35 * det_n + 0.25 * size_n + 0.25 * blur_n + 0.15 * pose_n)


# ───────────────────────── the gate itself (§7.3) ──────────────────────


def assess(face, frame: np.ndarray, cfg: QualityConfig | None = None) -> QualityResult:
    """Run every check in §7.3 order, returning the first failure's reason."""
    cfg = cfg or settings.quality

    # 1. Detection confidence
    det_score = float(face.det_score)
    if det_score < cfg.min_det_score:
        return _reject(LOW_DETECTION, det_score=det_score)

    # 2. Face size in source pixels (pre-resize — §5.1 min_face_width_px)
    x1, y1, x2, y2 = (float(v) for v in face.bbox)
    width = x2 - x1
    if width < cfg.min_face_width_px:
        return _reject(TOO_SMALL, width_px=width)

    # 3. Blur — variance of Laplacian on the crop
    h, w = frame.shape[:2]
    cx1, cy1 = max(0, int(x1)), max(0, int(y1))
    cx2, cy2 = min(w, int(x2)), min(h, int(y2))
    crop = frame[cy1:cy2, cx1:cx2]
    if crop.size == 0:
        return _reject(TOO_SMALL, width_px=width)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    blur = blur_variance(gray)
    if blur < cfg.min_blur_variance:
        return _reject(TOO_BLURRY, blur=blur)

    # 4. Brightness
    mean_v = float(gray.mean())
    if not (cfg.min_brightness <= mean_v <= cfg.max_brightness):
        return _reject(POOR_LIGHTING, brightness=mean_v)

    # 5. Pose
    yaw, pitch = pose_ratios(face.kps)
    if abs(yaw) > cfg.max_yaw_ratio or abs(pitch) > cfg.max_pitch_ratio:
        return _reject(EXTREME_POSE, yaw=yaw, pitch=pitch)

    return QualityResult(
        accepted=True,
        quality_score=weighted_score(det_score, width, blur, yaw, pitch, cfg),
        angle=classify_angle(yaw, pitch),
        yaw=yaw,
        pitch=pitch,
        detail={
            "det_score": det_score,
            "width_px": width,
            "blur": blur,
            "brightness": mean_v,
        },
    )


# ══════════════════ MediaPipe enrolment path (D12) ══════════════════════
#
# Everything above this line is unchanged and still serves Module B. `assess()` is
# called by the video pipeline through a duck-typed `_CropFace` adapter, and
# `min_crops_per_track` means a small tightening there silently zeroes whole tracks
# — the D9 incident. So this is a parallel gate, not a rewrite of that one.
#
# `blur_variance()` (D9) and `weighted_score()` (D4) are reused as they are: they take
# plain numbers and know nothing about which model produced them.


def classify_angle_deg(yaw: float, pitch: float, cfg: QualityConfig | None = None) -> str:
    """Bucket real degrees into the five classes of §5.1 required_angles.

    Two differences from `classify_angle()`, beyond the units:

    * The boundaries come from config (`angle_yaw_deg`, `angle_pitch_deg`) rather than
      the 0.15 / 0.20 literals, which were the only thresholds in the codebase not
      readable from thresholds.yaml.
    * Whichever axis is further past ITS OWN boundary wins, instead of yaw always being
      tested first. Under the old ordering a face at yaw 16 deg and pitch 30 deg was
      labelled `left` and could never be labelled `down`, so the `down` quota was
      reachable only by someone who tilted while keeping their head perfectly straight.

    Sign convention (D12, matching D5): positive yaw = subject turned to their own left;
    positive pitch = looking down.
    """
    cfg = cfg or settings.quality

    yaw_excess = abs(yaw) / cfg.angle_yaw_deg
    pitch_excess = abs(pitch) / cfg.angle_pitch_deg

    if yaw_excess < 1.0 and pitch_excess < 1.0:
        return "front"
    if yaw_excess >= pitch_excess:
        return "left" if yaw > 0 else "right"
    return "down" if pitch > 0 else "up"


def assess_mediapipe(
    mp_face,
    frame: np.ndarray,
    cfg: QualityConfig | None = None,
) -> QualityResult:
    """The enrolment quality gate. First failure wins, every reason actionable.

    `frame` is the ORIGINAL, un-enhanced image, and that is deliberate (D13). Blur and
    brightness are the two metrics that describe what ArcFace will actually embed, and
    ArcFace embeds raw pixels:

    * Blur on the enhanced copy would be measured after a bilateral filter, which
      strips the noise that inflates Laplacian variance — a sharp, noisy frame would
      read blurrier than it is, and D9's calibration would no longer hold.
    * Brightness on the enhanced copy would be measured after adaptive gamma, whose
      entire job is to move the mean into range. The gate would then pass frames whose
      true exposure is unrecoverable, and hand ArcFace a dark crop anyway.

    Preprocessing earns its place upstream of this, by making MediaPipe find and land
    the face at all in poor light. It is not a way past the gate.
    """
    cfg = cfg or settings.quality

    # 1. Landmarks. `analyse()` returns None when the mesh found nothing, so reaching
    #    here with an empty face means something upstream is wrong.
    if mp_face is None or mp_face.landmarks.size == 0:
        return _reject(NO_LANDMARKS)

    # 2. Detection confidence
    det_score = float(mp_face.det_score)
    if det_score < cfg.min_det_score:
        return _reject(LOW_DETECTION, det_score=det_score)

    # 3. Face size, from the landmark span rather than the detector box — BlazeFace and
    #    SCRFD disagree on box tightness, and min_face_width_px is shared with the video
    #    path. The span measures 0.97-1.01x the SCRFD width on real frames.
    width = mp_face.width_px
    if width < cfg.min_face_width_px:
        return _reject(TOO_SMALL, width_px=width)

    # 4. Blur — the D9 metric, on the raw crop, at the fixed 112 px scale.
    crop = _landmark_crop(mp_face, frame)
    if crop.size == 0:
        return _reject(TOO_SMALL, width_px=width)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    blur = blur_variance(gray)
    if blur < cfg.min_blur_variance:
        return _reject(TOO_BLURRY, blur=blur)

    # 5. Brightness
    mean_v = float(gray.mean())
    if not (cfg.min_brightness <= mean_v <= cfg.max_brightness):
        return _reject(POOR_LIGHTING, brightness=mean_v)

    # 6. Eyes open. New capability: a blink is invisible to every check above, and an
    #    enrolment template with the eyes shut is matched against for the rest of term.
    blink = mp_face.eye_blink
    if blink > cfg.max_eye_blink:
        return _reject(EYES_CLOSED, eye_blink=blink)

    yaw, pitch, roll = mp_pose(mp_face)

    # 7. Roll. Also new — the 5-keypoint estimator could not measure it. A rolled head
    #    produces a poor similarity transform and therefore a poor embedding.
    if abs(roll) > cfg.max_roll_deg:
        return _reject(EXTREME_ROLL, roll=roll)

    # 8. Yaw / pitch extremity
    if abs(yaw) > cfg.max_yaw_deg or abs(pitch) > cfg.max_pitch_deg:
        return _reject(EXTREME_POSE, yaw=yaw, pitch=pitch)

    pose_n = 1.0 - 0.5 * (abs(yaw) / cfg.max_yaw_deg + abs(pitch) / cfg.max_pitch_deg)

    return QualityResult(
        accepted=True,
        quality_score=weighted_score(det_score, width, blur, yaw, pitch, cfg, pose_n=pose_n),
        angle=classify_angle_deg(yaw, pitch, cfg),
        yaw=yaw,
        pitch=pitch,
        roll=roll,
        pose_in_degrees=True,
        detail={
            "det_score": det_score,
            "width_px": width,
            "blur": blur,
            "brightness": mean_v,
            "eye_blink": blink,
        },
    )


def mp_pose(mp_face) -> tuple[float, float, float]:
    """(yaw, pitch, roll) in degrees. Thin indirection so tests can pass a stub."""
    from app.services.mp_face import pose_degrees

    return pose_degrees(mp_face.transform)


def _landmark_crop(mp_face, frame: np.ndarray) -> np.ndarray:
    """The face region of the RAW frame, bounded by the landmark extent."""
    h, w = frame.shape[:2]
    xs, ys = mp_face.landmarks[:, 0], mp_face.landmarks[:, 1]
    x1, y1 = max(0, int(xs.min())), max(0, int(ys.min()))
    x2, y2 = min(w, int(xs.max())), min(h, int(ys.max()))
    return frame[y1:y2, x1:x2]
