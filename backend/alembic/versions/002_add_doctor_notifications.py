"""Add doctor_notifications table (C-9: doctor-side notification inbox)

Revision ID: add_doctor_notifications
Revises: 001_baseline
Create Date: 2026-08-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "add_doctor_notifications"
down_revision: Union[str, None] = "001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # C-9: doctor-side inbox. Mirrors patient_notifications shape.
    op.create_table(
        "doctor_notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "doctor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("doctors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("meta", JSONB, nullable=True),
        sa.Column("read", sa.Boolean, server_default=sa.text("false")),
        sa.Column(
            "patient_id",
            UUID(as_uuid=True),
            sa.ForeignKey("patients.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_doctor_notifications_doctor_id",
        "doctor_notifications",
        ["doctor_id"],
    )
    op.create_index(
        "ix_doctor_notifications_patient_id",
        "doctor_notifications",
        ["patient_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_doctor_notifications_patient_id", table_name="doctor_notifications")
    op.drop_index("ix_doctor_notifications_doctor_id", table_name="doctor_notifications")
    op.drop_table("doctor_notifications")
