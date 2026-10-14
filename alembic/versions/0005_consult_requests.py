"""Create missing consultation_requests table."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0005_consult_requests"
down_revision = "0004_payment_receipt"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    # Safe to run on databases where the table already exists.
    if "consultation_requests" not in inspector.get_table_names():
        op.create_table(
            "consultation_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("contact_method", sa.String(length=20), nullable=False),
            sa.Column("contact_value", sa.String(length=255), nullable=False),
            sa.Column("preferred_date", sa.String(length=40), nullable=True),
            sa.Column("preferred_time", sa.String(length=40), nullable=True),
            sa.Column("modules", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("business_description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING"),
            sa.Column("admin_notes", sa.Text(), nullable=True),
            sa.Column("meeting_url", sa.String(length=1000), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )

    inspector = inspect(bind)
    indexes = {idx["name"] for idx in inspector.get_indexes("consultation_requests")}
    if "ix_consultation_requests_company_id" not in indexes:
        op.create_index("ix_consultation_requests_company_id", "consultation_requests", ["company_id"])
    if "ix_consultation_requests_user_id" not in indexes:
        op.create_index("ix_consultation_requests_user_id", "consultation_requests", ["user_id"])
    if "ix_consultation_requests_status" not in indexes:
        op.create_index("ix_consultation_requests_status", "consultation_requests", ["status"])


def downgrade():
    # Preserve consultation data; intentionally do not drop the table.
    pass
