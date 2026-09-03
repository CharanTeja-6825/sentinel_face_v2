"""Live Test endpoint — single-frame identification against a section roster.

Read-only by construction: `recognition_service.identify_frame` writes nothing.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.recognition import IdentifyIn, IdentifyOut
from app.services import recognition_service

router = APIRouter(prefix="/recognition", tags=["recognition"])


@router.post("/identify", response_model=IdentifyOut)
def identify(payload: IdentifyIn, db: Session = Depends(get_db)):
    return recognition_service.identify_frame(db, payload.image, payload.section)
