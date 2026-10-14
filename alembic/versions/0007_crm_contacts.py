"""Add company-scoped CRM contacts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0007_crm_contacts"
down_revision = "0006_agent_setup"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "crm_contacts" not in inspect(bind).get_table_names():
        op.create_table(
            "crm_contacts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("phone", sa.String(50), nullable=False),
            sa.Column("contact_name", sa.String(150), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="NEW"),
            sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("company_id", "phone", name="uq_crm_contacts_company_phone"),
        )
    inspector = inspect(bind)
    indexes = {idx["name"] for idx in inspector.get_indexes("crm_contacts")}
    if "ix_crm_contacts_company_id" not in indexes:
        op.create_index("ix_crm_contacts_company_id", "crm_contacts", ["company_id"])
    if "ix_crm_contacts_status" not in indexes:
        op.create_index("ix_crm_contacts_status", "crm_contacts", ["status"])


def downgrade():
    # Preserve CRM contact history; intentionally do not drop the table.
    pass
