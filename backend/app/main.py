"""FastAPI application — INIT.md §4, §10."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.routers import admin, enrolment, recognition, sessions, timetable
from app.services import face_engine, mp_face

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
log = logging.getLogger("sentinelface")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # §5.2 — say loudly that the period clock times are unverified.
    settings.warn_if_unverified()

    for d in (settings.videos_dir, settings.crops_dir, settings.model_root):
        d.mkdir(parents=True, exist_ok=True)

    # §14.10 — load the model once, here, not per request. First run downloads
    # antelopev2 (~360 MB) into settings.model_root.
    try:
        face_engine.load_engine()
    except Exception:
        # /health reports the failure; the rest of the API (timetable, admin)
        # stays usable. Enrolment and video endpoints will fail loudly.
        log.error("Continuing without a face model — /health will report it.")

    # Same rule for MediaPipe (D12): built once here, not per request. First run
    # downloads face_landmarker.task (~3.8 MB) and blaze_face_short_range.tflite
    # (~230 KB) into settings.model_root/mediapipe. The worker does NOT load this —
    # Module B is unchanged and never touches MediaPipe.
    try:
        mp_face.load_mediapipe()
    except Exception:
        log.error("Continuing without MediaPipe — /health will report it. "
                  "Enrolment will fail until this is fixed.")

    yield


app = FastAPI(title="SentinelFace", version=settings.app_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Evidence crops referenced by crop_url in /sessions/{id}/results.
settings.crops_dir.mkdir(parents=True, exist_ok=True)
app.mount("/crops", StaticFiles(directory=str(settings.crops_dir)), name="crops")

app.include_router(timetable.router)
app.include_router(enrolment.router)
app.include_router(sessions.router)
app.include_router(admin.router)
app.include_router(recognition.router)


@app.get("/health")
def health() -> dict:
    """db, redis, model, version — §10."""
    db_ok, db_err = True, None
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok, db_err = False, f"{type(exc).__name__}: {exc}"

    redis_ok, redis_err = True, None
    try:
        redis.Redis.from_url(settings.redis_url).ping()
    except Exception as exc:
        redis_ok, redis_err = False, f"{type(exc).__name__}: {exc}"

    model = face_engine.engine_status()
    mediapipe = mp_face.mediapipe_status()

    return {
        # Both engines count: MediaPipe down means enrolment is down, even though
        # matching an already-built gallery would still work.
        "status": "ok"
        if (db_ok and redis_ok and model["loaded"] and mediapipe["loaded"])
        else "degraded",
        "version": settings.app_version,
        "database": {"ok": db_ok, "error": db_err},
        "redis": {"ok": redis_ok, "error": redis_err},
        "model": model,
        "mediapipe": mediapipe,
        "periods_verified": settings.periods.verified,
    }
