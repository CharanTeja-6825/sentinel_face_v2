"""Full INIT.md §6 schema.

Revision ID: 0001
Revises:
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgvector must exist before any vector column is created.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")  # gen_random_uuid()

    # ─────────────────────────── Identity ───────────────────────────
    op.create_table(
        "students",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("roll_no", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(200)),
        sa.Column("consent_given", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("consent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "section_students",
        sa.Column("section_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sections.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("student_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("students.id", ondelete="CASCADE"), primary_key=True),
    )

    # ─────────────────────────── Enrolment ──────────────────────────
    op.create_table(
        "enrolment_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("student_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("students.id", ondelete="CASCADE")),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("captured_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("angles_captured", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "face_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("student_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("students.id", ondelete="CASCADE")),
        sa.Column("embedding", Vector(512), nullable=False),
        sa.Column("angle", sa.String(16), nullable=False),
        sa.Column("quality_score", sa.REAL, nullable=False),
        sa.Column("is_centroid", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_templates_student", "face_templates", ["student_id"])

    # ────────────────────────── Timetable ───────────────────────────
    op.create_table(
        "timetable_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("section_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sections.id", ondelete="CASCADE")),
        sa.Column("day_of_week", sa.String(3), nullable=False),
        sa.Column("start_period", sa.Integer, nullable=False),
        sa.Column("end_period", sa.Integer, nullable=False),
        sa.Column("course_code", sa.String(32), nullable=False),
        sa.Column("component", sa.CHAR(1), nullable=False),
        sa.Column("group_code", sa.String(16), nullable=False),
        sa.Column("room", sa.String(32), nullable=False),
        # Makes seed loading idempotent (§9.4).
        sa.UniqueConstraint("section_id", "day_of_week", "start_period",
                            name="uq_block_section_day_start"),
    )

    # ─────────────────────── Attendance sessions ────────────────────
    op.create_table(
        "attendance_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("block_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("timetable_blocks.id")),
        sa.Column("section_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sections.id")),
        sa.Column("session_date", sa.Date, nullable=False),
        sa.Column("start_period", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("video_path", sa.Text),
        sa.Column("video_duration_s", sa.REAL),
        sa.Column("expected_count", sa.Integer),
        sa.Column("detected_count", sa.Integer),
        sa.Column("frames_sampled", sa.Integer),
        sa.Column("processing_ms", sa.Integer),
        sa.Column("error_message", sa.Text),
        sa.Column("model_version", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("section_id", "session_date", "start_period",
                            name="uq_session_section_date_period"),
    )

    # ────────────────── Evidence (append-only) ──────────────────────
    op.create_table(
        "tracks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("attendance_sessions.id", ondelete="CASCADE")),
        sa.Column("cluster_id", sa.Integer),
        sa.Column("first_seen_s", sa.REAL, nullable=False),
        sa.Column("last_seen_s", sa.REAL, nullable=False),
        sa.Column("crop_count", sa.Integer, nullable=False),
        sa.Column("mean_quality", sa.REAL, nullable=False),
        sa.Column("best_crop_path", sa.Text),
    )

    op.create_table(
        "observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("attendance_sessions.id", ondelete="CASCADE")),
        sa.Column("cluster_id", sa.Integer, nullable=False),
        sa.Column("top1_student_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("students.id")),
        sa.Column("top1_score", sa.REAL),
        sa.Column("top2_student_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("students.id")),
        sa.Column("top2_score", sa.REAL),
        sa.Column("margin", sa.REAL),
        sa.Column("band", sa.String(16), nullable=False),
        sa.Column("crop_paths", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # ───────────────────────── The ledger ───────────────────────────
    op.create_table(
        "attendance_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("attendance_sessions.id", ondelete="CASCADE")),
        sa.Column("student_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("students.id")),
        sa.Column("decision", sa.String(10), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("score", sa.REAL),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        # Makes writes idempotent — §6 invariant 2.
        sa.UniqueConstraint("session_id", "student_id",
                            name="uq_decision_session_student"),
    )

    op.create_table(
        "unmatched_faces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("attendance_sessions.id", ondelete="CASCADE")),
        sa.Column("cluster_id", sa.Integer, nullable=False),
        sa.Column("crop_path", sa.Text, nullable=False),
        sa.Column("best_score", sa.REAL),
        sa.Column("resolution", sa.String(20), server_default="unresolved"),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    for table in (
        "unmatched_faces",
        "attendance_decisions",
        "observations",
        "tracks",
        "attendance_sessions",
        "timetable_blocks",
        "face_templates",
        "enrolment_sessions",
        "section_students",
        "sections",
        "students",
    ):
        op.drop_table(table)
