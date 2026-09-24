"""add daily attendance cycle fields

Revision ID: c0a2d1e9f4ab
Revises: b7e3f91d20ac
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c0a2d1e9f4ab"
down_revision: Union[str, Sequence[str], None] = "b7e3f91d20ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table keeps this migration compatible with the school's
    # current SQLite deployment as well as PostgreSQL.
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("attendance_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("initial_roll_call_completed_at", sa.DateTime(), nullable=True))
        batch.create_index("ix_sessions_attendance_date", ["attendance_date"], unique=False)
        batch.create_unique_constraint(
            "uq_daily_attendance_class_date", ["class_id", "attendance_date"]
        )


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.drop_constraint("uq_daily_attendance_class_date", type_="unique")
        batch.drop_index("ix_sessions_attendance_date")
        batch.drop_column("initial_roll_call_completed_at")
        batch.drop_column("attendance_date")
