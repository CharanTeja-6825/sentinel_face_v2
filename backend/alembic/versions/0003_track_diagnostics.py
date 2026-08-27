"""Per-track quality diagnostics — spec §23.

Additive and entirely nullable. Every column here is a MEASUREMENT, not a
threshold and not a decision input: nothing in the pipeline reads them back, and
`downgrade` drops them without touching a single attendance decision.

They exist because config/thresholds.yaml says, at the top, that every value in
it is a starting value requiring calibration — and until a run records what the
face-width, blur and brightness distributions actually looked like, there is
nothing to calibrate against. Spec §24 asks for a repeatable evaluation set built
from the target environment; this is the half of it that the pipeline can supply
on its own.

Numbers only. No raw biometric frames are retained for telemetry (§29.9).

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Total detections associated with the track, accepted or not. The gap between
    # this and the existing `crop_count` is what `reject_reasons` explains.
    op.add_column("tracks", sa.Column("observation_count", sa.Integer(), nullable=True))
    op.add_column("tracks", sa.Column("resolution_band", sa.String(16), nullable=True))
    op.add_column("tracks", sa.Column("mean_face_width_px", sa.REAL(), nullable=True))
    op.add_column("tracks", sa.Column("mean_blur", sa.REAL(), nullable=True))
    op.add_column("tracks", sa.Column("mean_brightness", sa.REAL(), nullable=True))
    op.add_column(
        "tracks",
        sa.Column("reject_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    # Deliberately NO backfill. Rows from before this migration were produced by a
    # run that never measured these, and writing a default would make an unmeasured
    # run indistinguishable from a measured one — the failure mode D9 was.


def downgrade() -> None:
    for column in (
        "reject_reasons",
        "mean_brightness",
        "mean_blur",
        "mean_face_width_px",
        "resolution_band",
        "observation_count",
    ):
        op.drop_column("tracks", column)
