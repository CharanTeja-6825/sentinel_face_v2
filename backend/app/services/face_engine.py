"""InsightFace singleton — INIT.md §7.2.

Loaded ONCE, in the FastAPI lifespan handler (and once per RQ worker process).
Constructing this per request adds seconds to every call and exhausts memory
under any concurrency (§14.10).

Two hard rules enforced here:

* `antelopev2` (SCRFD-10G + glintr100 / ResNet-100 / Glint360K), not
  `buffalo_l` — §3 "Model choice".
* Always `.normed_embedding`, never `.embedding`. The former is L2-normalised,
  which makes cosine similarity a plain dot product and makes every threshold
  in §5.1 meaningful. Using `.embedding` silently turns cosine similarity into
  an unnormalised dot product (§14.8).
"""

from __future__ import annotations

import logging
import threading

import numpy as np
import onnxruntime

from app.config import settings

log = logging.getLogger(__name__)

_PREFERRED_PROVIDERS = ["CUDAExecutionProvider", "CPUExecutionProvider"]


def _providers() -> list[str]:
    """Only request providers this onnxruntime build actually has.

    Asking for CUDAExecutionProvider on a CPU-only build raises rather than
    falling back, which would make the whole app fail to start on this Mac.
    """
    available = set(onnxruntime.get_available_providers())
    chosen = [p for p in _PREFERRED_PROVIDERS if p in available]
    return chosen or ["CPUExecutionProvider"]


def _flatten_nested_model_dir() -> None:
    """Work around the antelopev2 release packaging.

    `antelopev2.zip` on the insightface v0.7 release extracts to
    `<root>/models/antelopev2/antelopev2/*.onnx` — one level deeper than
    insightface's own `glob(model_dir + '/*.onnx')` looks. The result is an
    unhelpful `assert 'detection' in self.models` at load time. Lift the .onnx
    files up one level once, on first load.
    """
    model_dir = settings.model_root / "models" / "antelopev2"
    nested = model_dir / "antelopev2"
    if not nested.is_dir():
        return
    for onnx in nested.glob("*.onnx"):
        target = model_dir / onnx.name
        if not target.exists():
            onnx.rename(target)
    if not any(nested.iterdir()):
        nested.rmdir()
    log.info("Flattened nested antelopev2 model directory")


class FaceEngine:
    # Stored on every embedding row and checked before any comparison (§14.1).
    MODEL_VERSION = "antelopev2/glintr100"

    def __init__(self, det_size: tuple[int, int] = (640, 640), ctx_id: int = -1):
        # ctx_id=-1 forces CPU, 0 selects first GPU.
        from insightface.app import FaceAnalysis
        from insightface.utils.storage import ensure_available

        self.det_size = tuple(det_size)
        self.ctx_id = ctx_id
        self.providers = _providers()
        log.info(
            "Loading antelopev2 (det_size=%s, ctx_id=%s, providers=%s) from %s",
            self.det_size, ctx_id, self.providers, settings.model_root,
        )
        # Download first (if absent), then repair the layout, then load.
        ensure_available("models", "antelopev2", root=str(settings.model_root))
        _flatten_nested_model_dir()

        self.app = FaceAnalysis(
            name="antelopev2",
            root=str(settings.model_root),
            providers=self.providers,
            # The antelopev2 pack also ships genderage, 2d106det and 1k3d68.
            # This system uses neither age/gender nor dense landmarks — SCRFD
            # detection and glintr100 recognition are the whole pipeline (§3).
            # Loading the rest costs real memory per process, and there are
            # three of them (api, worker, tests).
            allowed_modules=["detection", "recognition"],
        )
        self.app.prepare(ctx_id=ctx_id, det_size=self.det_size)
        log.info("antelopev2 ready")

    def detect(self, bgr_image: np.ndarray) -> list:
        """Returns insightface Face objects.

        Each has .bbox, .kps (5x2), .det_score and .normed_embedding (512,).
        """
        return self.app.get(bgr_image)

    @staticmethod
    def embedding_of(face) -> np.ndarray:
        """The only sanctioned way to read an embedding off a Face."""
        return np.asarray(face.normed_embedding, dtype=np.float32)

    # ── detection and recognition as separate steps (§8.1 steps 2, 4, 5) ──
    #
    # The video pipeline must run the quality gate BETWEEN detection and
    # embedding, so that recognition — by far the more expensive of the two on
    # CPU — only runs on crops that survive. `detect()` above does both at once
    # and is right for the enrolment path, where there is exactly one face.

    def detect_only(
        self, bgr_image: np.ndarray, input_size: tuple[int, int] | None = None
    ) -> tuple[np.ndarray, np.ndarray]:
        """Returns (bboxes[N,5] as x1,y1,x2,y2,score, kps[N,5,2])."""
        det = self.app.models["detection"]
        bboxes, kpss = det.detect(bgr_image, input_size=input_size or self.det_size)
        if bboxes is None or len(bboxes) == 0:
            return np.zeros((0, 5), np.float32), np.zeros((0, 5, 2), np.float32)
        return bboxes, kpss

    def align(self, bgr_image: np.ndarray, kps: np.ndarray) -> np.ndarray:
        """ArcFace-canonical 112x112 alignment for one face."""
        from insightface.utils import face_align

        return face_align.norm_crop(bgr_image, landmark=np.asarray(kps), image_size=112)

    def embed_aligned(self, crops: list[np.ndarray]) -> np.ndarray:
        """Embed a batch of aligned 112x112 crops, L2-normalised.

        Normalising here is what keeps cosine similarity a plain dot product,
        exactly as `.normed_embedding` does on the enrolment path (§14.8).
        """
        if not crops:
            return np.zeros((0, 512), np.float32)
        feats = self.app.models["recognition"].get_feat(crops)
        feats = np.asarray(feats, dtype=np.float32).reshape(len(crops), -1)
        norms = np.linalg.norm(feats, axis=1, keepdims=True)
        return feats / np.maximum(norms, 1e-12)


# ─────────────────────────── module singleton ───────────────────────────

_engine: FaceEngine | None = None
_load_error: str | None = None
_lock = threading.Lock()


def load_engine(det_size: tuple[int, int] | None = None) -> FaceEngine:
    """Build the singleton. Called from the FastAPI lifespan and the worker."""
    global _engine, _load_error
    with _lock:
        if _engine is None:
            try:
                _engine = FaceEngine(
                    det_size=det_size or settings.enrolment_det_size,
                    ctx_id=settings.ctx_id,
                )
                _load_error = None
            except Exception as exc:  # surface via /health rather than crashing
                _load_error = f"{type(exc).__name__}: {exc}"
                log.exception("FaceEngine failed to load")
                raise
        return _engine


def get_engine() -> FaceEngine:
    if _engine is None:
        return load_engine()
    return _engine


def engine_status() -> dict:
    """For /health — reports honestly rather than hiding a failed load."""
    return {
        "loaded": _engine is not None,
        "model_version": FaceEngine.MODEL_VERSION,
        "det_size": list(_engine.det_size) if _engine else None,
        "providers": _engine.providers if _engine else None,
        "error": _load_error,
    }
