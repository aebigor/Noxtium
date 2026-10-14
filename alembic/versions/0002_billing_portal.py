"""add noxtium client portal billing tables"""
from alembic import op
import sqlalchemy as sa

revision = "0002_billing_portal"
down_revision = "0001_initial_noxtium"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_company_id", "users", ["company_id"])
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "services",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(20), nullable=False, server_default="✦"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_services_slug"),
    )
    op.create_index("ix_services_slug", "services", ["slug"])

    op.create_table(
        "service_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("billing_period", sa.String(30), nullable=False, server_default="monthly"),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_service_plans_service_id", "service_plans", ["service_id"])

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("service_plan_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING_PAYMENT"),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_plan_id"], ["service_plans.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_subscriptions_company_id", "subscriptions", ["company_id"])
    op.create_index("ix_subscriptions_service_plan_id", "subscriptions", ["service_plan_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("provider", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("transaction_id", sa.String(150)),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_payments_subscription_id", "payments", ["subscription_id"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_index("ix_payments_transaction_id", "payments", ["transaction_id"])


def downgrade():
    op.drop_table("payments")
    op.drop_table("subscriptions")
    op.drop_table("service_plans")
    op.drop_table("services")
    op.drop_table("users")
