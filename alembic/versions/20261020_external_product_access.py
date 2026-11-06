"""Add external product access handoff to subscriptions.

Revision ID: 20261020_ext_access
Revises: 8857ff82db47
"""
from alembic import op
import sqlalchemy as sa

revision = "20261020_ext_access"
down_revision = "8857ff82db47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("external_access_url", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("provisioning_status", sa.String(length=30), nullable=False,
                  server_default="NOT_REQUIRED"),
    )
    op.create_table(
        "lead_inquiries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lead_inquiries_email", "lead_inquiries", ["email"], unique=False)
    op.create_index("ix_lead_inquiries_status", "lead_inquiries", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_lead_inquiries_status", table_name="lead_inquiries")
    op.drop_index("ix_lead_inquiries_email", table_name="lead_inquiries")
    op.drop_table("lead_inquiries")
    op.drop_column("subscriptions", "provisioning_status")
    op.drop_column("subscriptions", "external_access_url")
