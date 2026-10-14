"""Add per-company restaurant agent configuration."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0006_agent_setup"
down_revision = "0005_consult_requests"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if "agent_configurations" not in inspector.get_table_names():
        op.create_table(
            "agent_configurations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("restaurant_name", sa.String(150), nullable=False),
            sa.Column("business_type", sa.String(80), nullable=False, server_default="Restaurante"),
            sa.Column("address", sa.String(255), nullable=True),
            sa.Column("opening_hours", sa.Text(), nullable=True),
            sa.Column("delivery_zones", sa.Text(), nullable=True),
            sa.Column("menu_items", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("sales_tone", sa.String(40), nullable=False, server_default="amable"),
            sa.Column("special_rules", sa.Text(), nullable=True),
            sa.Column("welcome_message", sa.String(500), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default="SETUP"),
            sa.Column("n8n_workflow_id", sa.String(120), nullable=True),
            sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("company_id", name="uq_agent_configurations_company_id"),
        )
    inspector = inspect(bind)
    indexes = {idx["name"] for idx in inspector.get_indexes("agent_configurations")}
    if "ix_agent_configurations_company_id" not in indexes:
        op.create_index("ix_agent_configurations_company_id", "agent_configurations", ["company_id"])
    if "ix_agent_configurations_status" not in indexes:
        op.create_index("ix_agent_configurations_status", "agent_configurations", ["status"])


def downgrade():
    # Preserve configuration and audit data; intentionally do not drop this table.
    pass
