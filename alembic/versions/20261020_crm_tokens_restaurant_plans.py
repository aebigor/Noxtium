"""Add CRM token allowances and separate restaurant module plans.

Revision ID: 20261020_tokens_modules
Revises: 20261020_remove_qr
"""
from alembic import op
import sqlalchemy as sa

revision = "20261020_tokens_modules"
down_revision = "20261020_remove_qr"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("service_plans", sa.Column("included_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("subscriptions", sa.Column("token_limit", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("subscriptions", sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "n8n_token_usage_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", sa.String(length=200), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("workflow_id", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "event_id", name="uq_n8n_token_event_company_event"),
    )
    op.create_index("ix_n8n_token_usage_events_company_id", "n8n_token_usage_events", ["company_id"])
    op.create_index("ix_n8n_token_usage_events_subscription_id", "n8n_token_usage_events", ["subscription_id"])


def downgrade() -> None:
    op.drop_index("ix_n8n_token_usage_events_subscription_id", table_name="n8n_token_usage_events")
    op.drop_index("ix_n8n_token_usage_events_company_id", table_name="n8n_token_usage_events")
    op.drop_table("n8n_token_usage_events")
    op.drop_column("subscriptions", "tokens_used")
    op.drop_column("subscriptions", "token_limit")
    op.drop_column("service_plans", "included_tokens")
