"""add student_face_embeddings table

Revision ID: b7e3f91d20ac
Revises: 4331116ceb15
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e3f91d20ac"
down_revision: Union[str, Sequence[str], None] = "4331116ceb15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "student_face_embeddings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("external_student_id", sa.Integer(), nullable=False),
        sa.Column("image_type", sa.String(length=20), nullable=False),
        sa.Column("image_url", sa.String(length=1000), nullable=False),
        sa.Column("embedding_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "image_type", name="uq_student_image_type"),
    )
    op.create_index(
        op.f("ix_student_face_embeddings_id"), "student_face_embeddings", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_student_face_embeddings_student_id"),
        "student_face_embeddings",
        ["student_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_student_face_embeddings_external_student_id"),
        "student_face_embeddings",
        ["external_student_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_student_face_embeddings_external_student_id"),
        table_name="student_face_embeddings",
    )
    op.drop_index(
        op.f("ix_student_face_embeddings_student_id"),
        table_name="student_face_embeddings",
    )
    op.drop_index(
        op.f("ix_student_face_embeddings_id"), table_name="student_face_embeddings"
    )
    op.drop_table("student_face_embeddings")
