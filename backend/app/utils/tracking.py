"""IoU tracker — INIT.md §8.4.

Deliberately simple: a heavyweight tracking library is not warranted for this
prototype, and track fragmentation is handled downstream by clustering (§8.2
step 7) rather than by a smarter tracker.

`min_hits` is what filters spurious single-frame detections — reflections,
posters, motion artefacts — out of the results.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass
class Detection:
    bbox: np.ndarray          # x1, y1, x2, y2
    kps: np.ndarray           # 5 x 2
    det_score: float


@dataclass
class Crop:
    timestamp_s: float
    bbox: np.ndarray
    kps: np.ndarray
    det_score: float


@dataclass
class Track:
    id: int
    bbox: np.ndarray
    age: int = 0              # frames since last match
    hits: int = 0             # total matched detections
    crops: list[Crop] = field(default_factory=list)

    @property
    def first_seen_s(self) -> float:
        return self.crops[0].timestamp_s if self.crops else 0.0

    @property
    def last_seen_s(self) -> float:
        return self.crops[-1].timestamp_s if self.crops else 0.0


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

    def update(self, detections: list[Detection], timestamp_s: float) -> None:
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
            track.crops.append(
                Crop(timestamp_s, det.bbox, det.kps, det.det_score)
            )

        # 4. Unmatched detections start new tracks.
        for di in sorted(unmatched_dets):
            det = detections[di]
            track = Track(id=self.next_id, bbox=det.bbox, hits=1)
            track.crops.append(Crop(timestamp_s, det.bbox, det.kps, det.det_score))
            self.next_id += 1
            self.tracks.append(track)

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

    def finish(self) -> list[Track]:
        """All tracks confirmed by min_hits, in first-seen order (§8.4 step 6)."""
        everything = self.retired + self.tracks
        confirmed = [t for t in everything if t.hits >= self.min_hits]
        return sorted(confirmed, key=lambda t: (t.first_seen_s, t.id))
