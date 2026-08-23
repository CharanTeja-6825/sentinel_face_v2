"""MediaPipe pose columns on face_templates — D12.

The enrolment path now measures head pose in real degrees with MediaPipe's facial
transformation matrix, instead of deriving unitless yaw/pitch ratios from five SCRFD
keypoints. Those degrees are worth keeping: they are what a later calibration run needs
to check whether `angle_yaw_deg` / `angle_pitch_deg` are bucketing sensibly, and roll
was not measurable at all before.

Every column is NULLABLE on purpose. Rows written before this migration have no degrees
to backfill, and centroid rows have none by nature. Making them NOT NULL with a default
would fabricate a pose for both.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("face_templates", sa.Column("yaw_deg", sa.REAL(), nullable=True))
    op.add_column("face_templates", sa.Column("pitch_deg", sa.REAL(), nullable=True))
    op.add_column("face_templates", sa.Column("roll_deg", sa.REAL(), nullable=True))
    op.add_column(
        "face_templates", sa.Column("landmark_source", sa.String(length=48), nullable=True)
    )
    # Rows that already exist came from the 5-keypoint SCRFD path. Say so, rather than
    # leaving them indistinguishable from rows a future writer forgot to stamp.
    op.execute(
        "UPDATE face_templates SET landmark_source = 'scrfd_10g_bnkps' "
        "WHERE landmark_source IS NULL"
    )


def downgrade() -> None:
    op.drop_column("face_templates", "landmark_source")
    op.drop_column("face_templates", "roll_deg")
    op.drop_column("face_templates", "pitch_deg")
    op.drop_column("face_templates", "yaw_deg")
