"""MediaPipe Face Detector + Face Landmarker singleton — D12.

This owns the front of the ENROLMENT pipeline: detection, 478 landmarks, real 3D head
pose and blendshapes. It replaces the hand-rolled geometry described in ARCHITECTURE.md
§5.3 — five SCRFD keypoints turned into unitless yaw/pitch ratios, with no roll at all.

It deliberately does NOT live inside `FaceEngine`. That singleton is inherited by the RQ
worker through copy-on-write fork (`workers/worker.py`) and has call sites across the
video pipeline, matching and admin. Module B is unchanged by this work, so MediaPipe
stays out of its way entirely.

WHY BOTH TASKS. `FaceLandmarkerResult` carries `face_landmarks`, `face_blendshapes` and
`facial_transformation_matrixes` — and no detection score. `min_det_score` is the quality
gate's first check and 0.35 of `weighted_score()`, so the landmarker alone leaves the
most heavily weighted term with no input. `FaceDetector` supplies
`detections[].categories[].score`. Hence both.

MediaPipe expects RGB; OpenCV frames are BGR. Converted once, in `analyse()`.
"""

from __future__ import annotations

import logging
import threading
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from app.config import settings

log = logging.getLogger(__name__)

_BASE = "https://storage.googleapis.com/mediapipe-models"
MODELS: dict[str, str] = {
    # Face Mesh V2 (256x256) -> 478 landmarks, plus BlazeFace 192 and the blendshape head.
    "face_landmarker.task": f"{_BASE}/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
    # BlazeFace short-range (128x128) — the selfie/webcam model, which is what enrolment
    # is: one large face filling the frame.
    #
    # Known and measured limit: it does not see small or turned faces. On the bundled
    # six-person group photo it returns nothing at any input scale. That is correct for
    # this path but it bounds the `multiple_faces` guard — a second face is caught down
    # to roughly half the primary face's apparent size (someone standing beside the
    # student), and missed beyond that. A face that small would fail `min_face_width_px`
    # anyway and so could never be the one enrolled.
    #
    # The full-range variant would extend that reach, but `blaze_face_full_range.tflite`
    # at `latest` emits a box tensor mediapipe 0.10.18's graph rejects
    # (RET_CHECK dims[1] == num_boxes_), so it is not an option on this pin.
    "blaze_face_short_range.tflite": f"{_BASE}/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite",
}

# Stamped on every template this path produces, so a future calibration run can tell
# MediaPipe-aligned rows from SCRFD-aligned ones. Distinct from FaceEngine.MODEL_VERSION,
# which still names the RECOGNISER and is deliberately unchanged — see D12.
LANDMARK_SOURCE = "mediapipe/face_landmarker_v2"

# ─────────────────────────── landmark indices ───────────────────────────

# The five points insightface's `norm_crop` expects, in IMAGE order:
# [left_eye, right_eye, nose, left_mouth, right_mouth]. "Left" means the smaller-x side
# of the image, which for an unmirrored frame is the subject's RIGHT — the same
# convention InsightFace's `kps` uses, verified: landmark 468 sits at smaller x than 473
# on every real frame measured.
#
# 468 and 473 are IRIS CENTRES, from the 10 points Face Mesh V2 adds on top of the 468
# surface landmarks. They are actual pupil centres rather than SCRFD's estimate of one,
# and since eye positions dominate the similarity transform this is the single biggest
# alignment-precision gain in the change.
KPS_IDX: tuple[int, ...] = (468, 473, 1, 61, 291)

# Rings for the wizard's overlay. A curated ~88 points rather than all 478: at a 700 ms
# probe rate nobody can count mesh vertices, and the full set is ~5 KB of JSON per probe
# against ~1 KB for these.
OVERLAY_RINGS: dict[str, tuple[int, ...]] = {
    "oval": (10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379,
             378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127,
             162, 21, 54, 103, 67, 109),
    "left_eye": (33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246),
    "right_eye": (263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466),
    "lips": (61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0,
             37, 39, 40, 185),
}


@dataclass
class MPFace:
    """One analysed face. Coordinates are in the pixel space of the frame passed in."""

    det_score: float
    bbox: tuple[float, float, float, float]      # x1, y1, x2, y2
    landmarks: np.ndarray                        # (478, 2) float32, pixels
    landmarks_norm: np.ndarray                   # (478, 2) float32, [0, 1]
    transform: np.ndarray                        # (4, 4) canonical -> camera
    blendshapes: dict[str, float] = field(default_factory=dict)
    n_faces: int = 1

    @property
    def width_px(self) -> float:
        """Face width from the landmark x-extent, not the detector box.

        BlazeFace and SCRFD do not agree on how tightly they box a face, and
        `min_face_width_px` is shared config the video path still reads against SCRFD.
        The landmark span is detector-agnostic and measures 0.97–1.01x the SCRFD box
        width on real frames, so the existing threshold keeps its meaning.
        """
        return float(self.landmarks[:, 0].max() - self.landmarks[:, 0].min())

    @property
    def eye_blink(self) -> float:
        """Worse of the two eyes. A blinked frame otherwise passes every gate."""
        return max(
            self.blendshapes.get("eyeBlinkLeft", 0.0),
            self.blendshapes.get("eyeBlinkRight", 0.0),
        )

    def arcface_kps(self) -> np.ndarray:
        """The (5, 2) landmark set `FaceEngine.align()` consumes."""
        return np.asarray(self.landmarks[list(KPS_IDX)], dtype=np.float32)

    def overlay(self) -> dict[str, list[list[float]]]:
        """Normalised rings for the wizard overlay, rounded to 3dp to keep JSON small."""
        return {
            name: [[round(float(x), 3), round(float(y), 3)]
                   for x, y in self.landmarks_norm[list(idx)]]
            for name, idx in OVERLAY_RINGS.items()
        }


def pose_degrees(transform: np.ndarray) -> tuple[float, float, float]:
    """(yaw, pitch, roll) in degrees from the 4x4 facial transformation matrix.

    SIGN CONVENTION — empirically resolved, not assumed. DECISIONS.md D5 exists because
    guessing this wrong tells every student to turn the wrong way with no visible error,
    so it was measured the same way D5 was: run real faces, then their mirror images.

    Yaw inverted under mirroring on 8/8 real crops (cleaner than the ratio estimator,
    which had a non-inverting near-frontal case). Reading the nose tip against the two
    iris centres on the non-frontal cases fixes the direction: a face whose nose has
    swung toward image-left — i.e. the subject turned to their own RIGHT — reads
    negative. So positive yaw = the subject turned to their own left, which is exactly
    the D5 convention already in the codebase and what `classify_angle_deg()` labels
    "left". No negation is applied; MediaPipe's frame already agrees.

    Pitch likewise matches `pose_ratios()`: positive = looking down. Verified against a
    real frame reading -19.3 deg with the chin visibly raised and the nose only 21% of
    the way down the eye-to-chin span, which is chin-up foreshortening.

    `cv2.RQDecomp3x3` inverts R = Rz(roll) @ Ry(yaw) @ Rx(pitch), and returns the angles
    as (x, y, z) = (pitch, yaw, roll) — hence the reordering below. Euler angles are
    order-dependent, so this matters as soon as a head is turned and tilted at once.
    """
    angles = cv2.RQDecomp3x3(np.asarray(transform, dtype=np.float64)[:3, :3])[0]
    return float(angles[1]), float(angles[0]), float(angles[2])


class MediaPipeFace:
    def __init__(self) -> None:
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python import vision

        self.model_dir = Path(settings.model_root) / "mediapipe"
        paths = _ensure_models(self.model_dir)

        self.landmarker = vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(paths["face_landmarker.task"])),
                # IMAGE, not VIDEO: the frame endpoint is stateless request/response, so
                # VIDEO mode's tracking has nothing to track across.
                running_mode=vision.RunningMode.IMAGE,
                # 2, not 1 — enrolment must be able to SEE a second face to refuse it.
                # At num_faces=1 a bystander would silently replace the student.
                num_faces=2,
                output_face_blendshapes=True,
                output_facial_transformation_matrixes=True,
                min_face_detection_confidence=settings.quality.min_det_score,
            )
        )
        self.detector = vision.FaceDetector.create_from_options(
            vision.FaceDetectorOptions(
                base_options=BaseOptions(
                    model_asset_path=str(paths["blaze_face_short_range.tflite"])
                ),
                running_mode=vision.RunningMode.IMAGE,
                min_detection_confidence=settings.quality.min_det_score,
            )
        )
        # MediaPipe task objects are not thread-safe, and FastAPI runs sync endpoints in
        # a threadpool, so two students enrolling at once would call into the same graph
        # concurrently. Serialise inference. Enrolment is CPU-bound anyway.
        self._infer_lock = threading.Lock()
        log.info("MediaPipe ready (models in %s)", self.model_dir)

    def analyse(self, bgr: np.ndarray) -> MPFace | None:
        """Detect + landmark one frame. None when no face is found.

        `n_faces` on the result is the larger of what the two models saw, so an
        ambiguous frame is reported as ambiguous rather than resolved by whichever
        model happened to miss the second person.
        """
        import mediapipe as mp

        h, w = bgr.shape[:2]
        image = mp.Image(
            image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        )

        with self._infer_lock:
            det = self.detector.detect(image)
            lmk = self.landmarker.detect(image)

        if not lmk.face_landmarks:
            return None

        n_faces = max(len(lmk.face_landmarks), len(det.detections))

        if det.detections:
            best = max(det.detections, key=lambda d: d.categories[0].score)
            box = best.bounding_box
            det_score = float(best.categories[0].score)
            bbox = (float(box.origin_x), float(box.origin_y),
                    float(box.origin_x + box.width), float(box.origin_y + box.height))
        else:
            # The mesh found a face the detector did not. Rather than invent a score,
            # report 0.0 and let `min_det_score` reject it — the gate is the authority.
            det_score = 0.0
            bbox = (0.0, 0.0, 0.0, 0.0)

        pts = lmk.face_landmarks[0]
        norm = np.array([[p.x, p.y] for p in pts], dtype=np.float32)

        return MPFace(
            det_score=det_score,
            bbox=bbox,
            landmarks=norm * np.array([w, h], dtype=np.float32),
            landmarks_norm=norm,
            transform=np.asarray(lmk.facial_transformation_matrixes[0], dtype=np.float64),
            blendshapes={c.category_name: float(c.score) for c in lmk.face_blendshapes[0]}
            if lmk.face_blendshapes else {},
            n_faces=n_faces,
        )


def _ensure_models(model_dir: Path) -> dict[str, Path]:
    """Download the two .task/.tflite bundles on first use.

    Mirrors what `insightface.utils.storage.ensure_available` does for antelopev2, so
    a fresh checkout needs no manual model step.
    """
    model_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, url in MODELS.items():
        target = model_dir / name
        if not target.exists() or target.stat().st_size == 0:
            log.info("Downloading MediaPipe model %s", name)
            tmp = target.with_suffix(target.suffix + ".part")
            urllib.request.urlretrieve(url, tmp)  # noqa: S310 — fixed https URLs above
            tmp.rename(target)
        paths[name] = target
    return paths


# ─────────────────────────── module singleton ───────────────────────────

_mp: MediaPipeFace | None = None
_load_error: str | None = None
_lock = threading.Lock()


def load_mediapipe() -> MediaPipeFace:
    """Build the singleton. Called from the FastAPI lifespan."""
    global _mp, _load_error
    with _lock:
        if _mp is None:
            try:
                _mp = MediaPipeFace()
                _load_error = None
            except Exception as exc:  # surface via /health rather than crashing
                _load_error = f"{type(exc).__name__}: {exc}"
                log.exception("MediaPipe failed to load")
                raise
        return _mp


def get_mediapipe() -> MediaPipeFace:
    return _mp if _mp is not None else load_mediapipe()


def mediapipe_status() -> dict:
    """For /health — reports honestly rather than hiding a failed load."""
    return {
        "loaded": _mp is not None,
        "landmark_source": LANDMARK_SOURCE,
        "model_dir": str(_mp.model_dir) if _mp else None,
        "error": _load_error,
    }
