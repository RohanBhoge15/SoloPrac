"""Baseline migration — matches init-schema.sql

Revision ID: 001_baseline
Revises:
Create Date: 2026-07-27
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable PostGIS extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "postgis"')

    # ── users ──
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text, unique=True, nullable=False, index=True),
        sa.Column("password_hash", sa.Text),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("phone", sa.Text),
        sa.Column("phone_hash", sa.Text),
        sa.Column("dob", sa.Date),
        sa.Column("gender", sa.Text),
        sa.Column("address", sa.Text),
        sa.Column("blood_group", sa.Text),
        sa.Column("allergies", sa.Text),
        sa.Column("known_conditions", sa.Text),
        sa.Column("height_cm", sa.Float),
        sa.Column("weight_kg", sa.Float),
        sa.Column("emergency_contact_name", sa.Text),
        sa.Column("emergency_contact_phone", sa.Text),
        sa.Column("insurance_info", sa.Text),
        sa.Column("consent_for_share", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── doctors ──
    op.create_table(
        "doctors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text, unique=True, nullable=False, index=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("speciality", sa.Text, server_default="General Practice"),
        # sa.Column("location") is added via raw SQL below (PostGIS GEOGRAPHY)
        sa.Column("clinic_name", sa.Text, nullable=False, server_default=""),
        sa.Column("clinic_address", sa.Text, nullable=False, server_default=""),
        sa.Column("pincode", sa.String(6), index=True),
        sa.Column("phone", sa.Text, nullable=False, server_default=""),
        sa.Column("registration_number", sa.Text),
        sa.Column("password_hash", sa.Text),
        sa.Column("verification_status", sa.Text, nullable=False, server_default="unverified"),
        sa.Column("license_document_path", sa.Text),
        sa.Column("rejection_reason", sa.Text),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("state_medical_council", sa.Text),
        sa.Column("year_of_registration", sa.Integer),
        sa.Column("qualification", sa.Text),
        sa.Column("abdm_verified_at", sa.DateTime(timezone=True)),
        sa.Column("settings", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # PostGIS geography column (raw SQL since SQLAlchemy type mapping varies)
    op.execute("""
        ALTER TABLE doctors
        ADD COLUMN IF NOT EXISTS location GEOGRAPHY(POINT, 4326)
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_doctors_location ON doctors USING GIST (location)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_doctors_pincode ON doctors (pincode) WHERE pincode IS NOT NULL")


def downgrade() -> None:
    op.drop_table("doctors")
    op.drop_table("users")
    op.execute('DROP EXTENSION IF EXISTS "postgis"')
