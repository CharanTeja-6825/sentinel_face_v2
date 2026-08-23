"""End-to-end plumbing check for Module B.

Seeds a timetable, creates a roster, enrols each roster student from a face in
the bundled sample photo, builds a short video from that same photo, uploads it
and waits for the RQ worker to finish. Then prints the results payload.

This proves the PATH works — upload, queue, worker, pipeline, persistence, API.
It proves nothing about ACCURACY, because the "video" is a still photo and the
enrolment templates come from the same frames. Real numbers require real
footage and human ground truth (§12 Phase 6, §15).

Run inside the backend container:
    docker compose exec backend python scripts/smoke_e2e.py
"""

from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from insightface.data import get_image  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import FaceTemplate, Student  # noqa: E402
from app.services.face_engine import FaceEngine, load_engine  # noqa: E402

API = "http://localhost:8000"
SECTION = "S-67"


def build_video(path: Path, frame: np.ndarray, seconds=12, fps=15) -> None:
    """Pan slowly across the photo so tracked boxes move like real footage."""
    h, w = frame.shape[:2]
    out_w, out_h = w - 40, h - 40
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (out_w, out_h)
    )
    total = seconds * fps
    for i in range(total):
        dx = int(20 + 20 * np.sin(2 * np.pi * i / total))
        dy = int(20 + 10 * np.cos(2 * np.pi * i / total))
        writer.write(frame[dy : dy + out_h, dx : dx + out_w])
    writer.release()


def main() -> int:
    import httpx

    client = httpx.Client(base_url=API, timeout=60.0)

    print("== seeding timetable ==")
    print(client.post("/timetable/seed").json())

    engine = load_engine()
    photo = get_image("t1")
    faces = engine.detect(photo)
    print(f"== {len(faces)} faces in the sample photo -> {len(faces)} students ==")

    db = SessionLocal()
    roll_nos = []
    try:
        for i, face in enumerate(faces):
            roll = f"SMOKE-{i:03d}"
            roll_nos.append(roll)
            student = db.query(Student).filter(Student.roll_no == roll).one_or_none()
            if student is None:
                student = Student(roll_no=roll, name=f"Smoke Student {i}")
                db.add(student)
                db.commit()
                db.refresh(student)
            if not db.query(FaceTemplate).filter(
                FaceTemplate.student_id == student.id
            ).count():
                db.add(
                    FaceTemplate(
                        student_id=student.id,
                        embedding=FaceEngine.embedding_of(face),
                        angle="front",
                        quality_score=0.9,
                        is_centroid=True,
                        model_version=FaceEngine.MODEL_VERSION,
                        source="enrolment",
                    )
                )
                db.commit()
    finally:
        db.close()

    print(client.post(f"/admin/sections/{SECTION}/students",
                      json={"roll_nos": roll_nos}).json())

    blocks = client.get("/timetable/blocks",
                        params={"section": SECTION, "day": "Mon"}).json()
    block = next(b for b in blocks if b["eligible"])

    created = client.post(
        "/sessions",
        json={"block_id": block["id"], "session_date": str(date.today())},
    )
    if created.status_code == 409:
        print("session already exists for today; delete it or pick another date")
        return 1
    created.raise_for_status()
    session = created.json()
    session_id = session["session_id"]
    print(f"== session {session_id}: expected={session['expected_count']} "
          f"enrolled={session['enrolled_pct']}% ==")

    video = Path("/tmp/smoke.mp4")
    build_video(video, photo)
    print(f"== uploading {video.stat().st_size / 1e6:.1f} MB ==")
    with video.open("rb") as fh:
        r = client.post(
            f"/sessions/{session_id}/video",
            files={"file": ("smoke.mp4", fh, "video/mp4")},
        )
    r.raise_for_status()
    print(r.json())

    print("== waiting for the worker ==")
    deadline = time.time() + 900
    status = {}
    while time.time() < deadline:
        status = client.get(f"/sessions/{session_id}").json()
        print(f"   status={status['status']:<11} "
              f"frames={status.get('frames_sampled')} "
              f"progress={status.get('progress')}")
        if status["status"] in ("completed", "failed"):
            break
        time.sleep(5)

    if status.get("status") != "completed":
        print("FAILED:", status.get("error_message"))
        return 1

    results = client.get(f"/sessions/{session_id}/results").json()
    print("\n== stats ==")
    for k, v in results["stats"].items():
        print(f"   {k}: {v}")
    print(f"\n   confident: {len(results['confident'])}")
    for row in results["confident"]:
        print(f"      {row['student']['roll_no']} score={row['score']:.3f} "
              f"margin={row['margin']:.3f}")
    print(f"   uncertain: {len(results['uncertain'])}")
    for row in results["uncertain"]:
        print(f"      {row['student']['roll_no']} score={row['score']:.3f} "
              f"margin={row['margin']:.3f}")
    print(f"   absent:    {len(results['absent'])}")
    print(f"   unmatched: {len(results['unmatched'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
