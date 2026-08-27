"""IoU tracker and the face-observation abstraction — INIT.md §8.4, spec §6, §7, §10.

Deliberately simple: a heavyweight tracking library is not warranted for this
prototype, and track fragmentation is handled downstream by clustering (§8.2
step 7) rather than by a smarter tracker. Spec §6 lists ByteTrack / BoT-SORT /
DeepSORT and then says to benchmark rather than pick by reputation — there is no
labelled footage to benchmark against yet, so the tracker is unchanged.

`min_hits` is what filters spurious single-frame detections — reflections,
posters, motion artefacts — out of the results.

WHAT CHANGED, AND WHY IT IS THE WHOLE POINT (spec §7, §10, §29.8)
─────────────────────────────────────────────────────────────────
A `Track` used to hold `crops: list[Crop]`, where a `Crop` was a bbox plus five
keypoints and nothing else. That is cheap, but it meant the pixels needed to
score and align each crop were only available LATER — so `run_pipeline` kept
every sampled frame in a dict for the duration of the video. At the configured
ceilings (60 min, 2 fps, 4K) that is ~7,200 full-resolution frames, roughly
180 GB resident, and `max_duration_minutes` did nothing to stop it.

A track now holds the ALIGNED 112x112 crop of its best `max_per_track`
observations, scored as the frame goes past. The frame is then released. The
same restructuring is what spec §7 (a normalised observation object) and §10 (a
bounded, quality-ranked per-track buffer) ask for — one change, three
requirements. Residency per track is `max_per_track * 112 * 112 * 3` bytes,
about 300 KB at the configured 8, and is independent of video length.

Everything a track knows that is NOT a pixel — how many detections it absorbed,
what they were rejected for, when it started and stopped — is kept as running
counters rather than a list, so the diagnostics of §23 cost O(1) per track
instead of growing with the video.
"""

from __future__ import annotations

import heapq
import itertools
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

from app.services.quality import QualityResult


@dataclass
class Detection:
    """One face found in one frame, straight out of the detector.

    Carries exactly the three attributes `quality.assess()` duck-types on —
    `.bbox`, `.kps`, `.det_score` — so it can be passed to the gate directly. The
    `_CropFace` adapter that used to exist in video_pipeline.py only existed
    because the gate ran later, against a `Crop` that had been stripped of its
    frame; with the gate in the frame loop, the adapter has nothing left to adapt.
    """

    bbox: np.ndarray          # x1, y1, x2, y2
    kps: np.ndarray           # 5 x 2
    det_score: float


@dataclass
class FaceObservation:
    """A single scored, aligned look at one tracked face — spec §7.

    Spec §7's suggested shape carries track_id, frame_id, timestamp, bbox,
    detection_confidence, a quality breakdown, pose and an embedding slot. All of
    it is here or reachable: `quality.detail` holds the per-component breakdown
    (det_score, width_px, blur, brightness, band, luma_asymmetry,
    clipped_fraction), `quality.yaw/pitch` hold pose, and the track this hangs off
    supplies the track_id. The embedding slot is deliberately absent — embedding
    happens once per track, batched, over the survivors of this buffer (§14), so
    a per-observation slot would only ever hold None.

    `aligned` is the ONLY pixel data retained anywhere in the pipeline.
    """

    timestamp_s: float
    quality: QualityResult
    aligned: np.ndarray       # 112x112 BGR, ArcFace-canonical


@dataclass
class Track:
    """A physical face trajectory. NOT an identity — spec §3, §29.11.

    The tracker answers "is this the same observed face as before?". Who that face
    belongs to is decided much later, per cluster, in gallery_service.
    """

    id: int
    bbox: np.ndarray
    age: int = 0              # frames since last match
    hits: int = 0             # total matched detections

    first_seen_s: float = 0.0
    last_seen_s: float = 0.0

    # §23 per-track diagnostics, as counters rather than a list of everything.
    observation_count: int = 0                       # every associated detection
    reject_reasons: Counter = field(default_factory=Counter)

    # The bounded best-observation buffer (§10). A min-heap keyed on quality score,
    # so the weakest survivor is always at [0] and eviction is O(log k).
    best: list = field(default_factory=list)
    _seq: itertools.count = field(default_factory=itertools.count, repr=False)

    # ── the buffer (§10) ──

    def would_accept(self, quality_score: float, k: int) -> bool:
        """Would `offer` keep an observation with this score?

        Checked BEFORE aligning. Alignment is a warpAffine per observation, and on a
        long track most observations lose to the incumbents — asking first skips the
        warp for every one of them.
        """
        return len(self.best) < k or quality_score > self.best[0][0]

    def offer(self, quality_score: float, observation: FaceObservation, k: int) -> None:
        """Keep this observation if it is among the k best seen so far.

        The `next(self._seq)` tiebreaker is load-bearing, not decoration: heapq
        compares tuples element by element, so two observations with an identical
        score would fall through to comparing `FaceObservation`, and then the numpy
        array inside it, which raises. A strictly increasing int can never tie.
        """
        if k <= 0:
            return
        entry = (quality_score, next(self._seq), observation)
        if len(self.best) < k:
            heapq.heappush(self.best, entry)
        elif quality_score > self.best[0][0]:
            heapq.heapreplace(self.best, entry)

    def observations(self) -> list[FaceObservation]:
        """The retained observations, best quality first."""
        return [obs for _, _, obs in sorted(self.best, key=lambda e: -e[0])]

    def record(self, result: QualityResult) -> None:
        """Note that a detection was associated, accepted or not.

        Rejected observations still count. That is spec §9 — a face too small or too
        blurry to recognise is still a face worth TRACKING, and the reject reason is
        what tells a calibration run WHY a track produced no usable evidence. A track
        with 200 observations and 2 survivors, all `face_too_small`, is a camera
        placement problem; without this counter it looks like a threshold problem.
        """
        self.observation_count += 1
        if not result.accepted:
            self.reject_reasons[result.reason or "unknown"] += 1


def iou(a: np.ndarray, b: np.ndarray) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return float(inter / union) if union > 0 else 0.0


class IoUTracker:
    def __init__(self, iou_threshold: float, max_age: int, min_hits: int):
        self.iou_threshold = iou_threshold
        self.max_age = max_age
        self.min_hits = min_hits
        self.tracks: list[Track] = []
        self.retired: list[Track] = []
        self.next_id = 0

    def update(
        self, detections: list[Detection], timestamp_s: float
    ) -> list[tuple[Track, Detection]]:
        """Associate this frame's detections with tracks.

        Returns the (track, detection) pairs established this frame — matches and
        newly created tracks alike — so the caller can score them while it still
        holds the frame. Returning the pairs rather than taking a callback keeps the
        tracker ignorant of quality, alignment and embedding: it answers "same face
        as before?" and nothing else (spec §3).

        The association itself is unchanged: IoU cost matrix, Hungarian assignment,
        threshold on the resulting pairs.
        """
        associations: list[tuple[Track, Detection]] = []

        # 1-2. IoU cost matrix, then Hungarian assignment.
        matches: list[tuple[int, int]] = []
        unmatched_dets = set(range(len(detections)))
        unmatched_tracks = set(range(len(self.tracks)))

        if self.tracks and detections:
            scores = np.zeros((len(self.tracks), len(detections)), dtype=np.float32)
            for ti, track in enumerate(self.tracks):
                for di, det in enumerate(detections):
                    scores[ti, di] = iou(track.bbox, det.bbox)

            rows, cols = linear_sum_assignment(-scores)
            for ti, di in zip(rows, cols):
                # 3. Only pairs above the threshold count as the same person.
                if scores[ti, di] >= self.iou_threshold:
                    matches.append((int(ti), int(di)))
                    unmatched_tracks.discard(int(ti))
                    unmatched_dets.discard(int(di))

        for ti, di in matches:
            det = detections[di]
            track = self.tracks[ti]
            track.bbox = det.bbox
            track.age = 0
            track.hits += 1
            track.last_seen_s = timestamp_s
            associations.append((track, det))

        # 4. Unmatched detections start new tracks.
        for di in sorted(unmatched_dets):
            det = detections[di]
            track = Track(
                id=self.next_id,
                bbox=det.bbox,
                hits=1,
                first_seen_s=timestamp_s,
                last_seen_s=timestamp_s,
            )
            self.next_id += 1
            self.tracks.append(track)
            associations.append((track, det))

        # 5. Unmatched tracks age out.
        for ti in sorted(unmatched_tracks, reverse=True):
            self.tracks[ti].age += 1

        still_alive = []
        for track in self.tracks:
            if track.age > self.max_age:
                self.retired.append(track)
            else:
                still_alive.append(track)
        self.tracks = still_alive

        return associations

    def finish(self) -> list[Track]:
        """All tracks confirmed by min_hits, in first-seen order (§8.4 step 6)."""
        everything = self.retired + self.tracks
        confirmed = [t for t in everything if t.hits >= self.min_hits]
        return sorted(confirmed, key=lambda t: (t.first_seen_s, t.id))
