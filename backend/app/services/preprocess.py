"""Frame preprocessing for the enrolment path — D13.

A webcam frame used to go straight from `cv2.imdecode` into detection, so a dim or
backlit frame just failed the quality gate with no attempt to recover it. This module
sits in front of MediaPipe and cleans the frame up first.

THE ORDER MATTERS, and it is denoise -> gamma -> CLAHE:

* Denoise first, because CLAHE amplifies whatever noise it is handed. A bilateral
  filter rather than a Gaussian one — Gaussian blurs the very edges the Laplacian
  sharpness metric scores, which would let genuinely soft frames through the gate.
* Gamma second, to land global exposure in range before local contrast runs. CLAHE on a
  badly under-exposed frame equalises noise, not detail.
* CLAHE last, on the L channel of LAB only. Chroma is left alone, so skin tone does not
  shift — equalising RGB channels independently is what produces the classic colour cast.

WHERE THE OUTPUT GOES — this is the whole design (D13). The enhanced frame feeds
detection, landmarking and the quality metrics. It NEVER reaches ArcFace: alignment and
embedding read the original pixels. ArcFace was trained on largely un-enhanced faces, so
enhancing what it embeds shifts the embedding distribution away from the thresholds the
video path is calibrated against (`t_high` 0.60, `t_low` 0.45, `cluster_distance` 0.50)
— and every stored template would then depend on the preprocessing parameters, so
retuning `clahe_clip` would silently invalidate the gallery.

`enhance()` also runs on a DOWNSCALED copy (`preprocess.max_side`). BlazeFace consumes
128x128 and the face mesh 256x256, so full-resolution enhancement buys them nothing, and
a bilateral filter on a 1280x720 frame does not fit in the wizard's 700 ms probe budget.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.config import PreprocessConfig, settings

# Gamma outside this range means the frame is so far off that correcting it fully would
# manufacture detail that is not there. Clamp and let the brightness gate reject it.
GAMMA_MIN, GAMMA_MAX = 0.5, 2.0


def fit_to_max_side(bgr: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    """Downscale so the longer side is `max_side`. Returns (image, scale).

    `scale` maps a coordinate in the returned image back to the original:
    `orig_xy = small_xy / scale`. Never upscales — a small frame is already cheap.
    """
    h, w = bgr.shape[:2]
    longest = max(h, w)
    if longest <= max_side:
        return bgr, 1.0
    scale = max_side / longest
    return cv2.resize(
        bgr, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA
    ), scale


def adaptive_gamma(bgr: np.ndarray, target_luma: float) -> tuple[np.ndarray, float]:
    """Push mean luminance toward `target_luma`. Returns (image, gamma applied).

    gamma = log(target) / log(mean), the standard closed form: applying `x ** gamma` to
    a normalised image maps the current mean onto the target exactly. Returned so the
    caller can log what was actually done — a frame that needed gamma 0.5 is a lighting
    problem the operator should know about, not just a frame that happened to pass.
    """
    mean = float(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).mean()) / 255.0
    # A frame that is pure black or pure white has no exposure to recover.
    if not (0.01 < mean < 0.99):
        return bgr, 1.0

    gamma = float(np.clip(np.log(target_luma) / np.log(mean), GAMMA_MIN, GAMMA_MAX))
    if abs(gamma - 1.0) < 0.02:
        return bgr, 1.0

    # 256-entry LUT rather than per-pixel power — same result, ~50x faster.
    lut = np.clip(((np.arange(256) / 255.0) ** gamma) * 255.0, 0, 255).astype(np.uint8)
    return cv2.LUT(bgr, lut), gamma


def clahe_on_luminance(bgr: np.ndarray, clip: float, grid: int) -> np.ndarray:
    """CLAHE on the L channel of LAB, leaving a and b untouched."""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(
        clipLimit=clip, tileGridSize=(grid, grid)
    ).apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def enhance(
    bgr: np.ndarray, cfg: PreprocessConfig | None = None
) -> tuple[np.ndarray, dict]:
    """Denoise -> adaptive gamma -> CLAHE. Returns (enhanced, what-was-done).

    The second value is reported on the frame response and logged, so a student stuck on
    `poor_lighting` produces evidence of how hard the pipeline tried, rather than a bare
    rejection.
    """
    cfg = cfg or settings.preprocess
    if not cfg.enabled:
        return bgr, {"enabled": False}

    out = cv2.bilateralFilter(bgr, cfg.bilateral_d, cfg.bilateral_sigma, cfg.bilateral_sigma)
    out, gamma = adaptive_gamma(out, cfg.gamma_target_luma)
    out = clahe_on_luminance(out, cfg.clahe_clip, cfg.clahe_grid)

    return out, {
        "enabled": True,
        "gamma": round(gamma, 3),
        "mean_luma_before": round(float(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).mean()) / 255, 3),
        "mean_luma_after": round(float(cv2.cvtColor(out, cv2.COLOR_BGR2GRAY).mean()) / 255, 3),
    }


# ponytail: no white balance, Retinex or homomorphic filtering. CLAHE plus adaptive
# gamma covers the failure this system actually has (a dim or backlit classroom webcam).
# Add one when a measured failure mode calls for it, not before.
