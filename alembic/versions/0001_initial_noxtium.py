"""initial noxtium crm schema"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_noxtium"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_companies_email", "companies", ["email"])

    op.create_table(
        "whatsapp_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("waba_id", sa.String(100), nullable=False),
        sa.Column("phone_number_id", sa.String(100), nullable=False),
        sa.Column("display_phone_number", sa.String(50)),
        sa.Column("verified_name", sa.String(255)),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("token_type", sa.String(80), nullable=False, server_default="business_integration_system_user"),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("phone_number_id", name="uq_whatsapp_connections_phone_number_id"),
    )
    op.create_index("ix_whatsapp_connections_company_id", "whatsapp_connections", ["company_id"])
    op.create_index("ix_whatsapp_connections_waba_id", "whatsapp_connections", ["waba_id"])
    op.create_index("ix_whatsapp_connections_phone_number_id", "whatsapp_connections", ["phone_number_id"])

    op.create_table(
        "whatsapp_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("whatsapp_connection_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.String(255), nullable=False),
        sa.Column("from_number", sa.String(50)),
        sa.Column("to_number", sa.String(50)),
        sa.Column("message_type", sa.String(50)),
        sa.Column("message_text", sa.Text()),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["whatsapp_connection_id"], ["whatsapp_connections.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("message_id", name="uq_whatsapp_messages_message_id"),
    )
    op.create_index("ix_whatsapp_messages_company_id", "whatsapp_messages", ["company_id"])
    op.create_index("ix_whatsapp_messages_whatsapp_connection_id", "whatsapp_messages", ["whatsapp_connection_id"])
    op.create_index("ix_whatsapp_messages_message_id", "whatsapp_messages", ["message_id"])

def downgrade():
    op.drop_table("whatsapp_messages")
    op.drop_table("whatsapp_connections")
    op.drop_index("ix_companies_email", table_name="companies")
    op.drop_table("companies")
