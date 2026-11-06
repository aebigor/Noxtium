"""Remove legacy non-official QR WhatsApp tables.

Revision ID: 20261020_remove_qr
Revises: 20261020_ext_access
"""
from alembic import op
import sqlalchemy as sa

revision = "20261020_remove_qr"
down_revision = "20261020_ext_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Drop only the legacy QR-specific tables. Official Meta connection/message tables remain.
    if inspector.has_table("qr_whatsapp_messages"):
        op.drop_table("qr_whatsapp_messages")
    if inspector.has_table("qr_whatsapp_connections"):
        op.drop_table("qr_whatsapp_connections")


def downgrade() -> None:
    # Restores the legacy table structure for schema rollback only; QR code is not re-enabled.
    op.create_table(
        "qr_whatsapp_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phone_number", sa.String(length=50), nullable=True),
        sa.Column("verified_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="disconnected"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_qr_whatsapp_connections_company_id", "qr_whatsapp_connections", ["company_id"], unique=True)
    op.create_index("ix_qr_whatsapp_connections_status", "qr_whatsapp_connections", ["status"], unique=False)
    op.create_table(
        "qr_whatsapp_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("qr_whatsapp_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.String(length=255), nullable=False),
        sa.Column("from_number", sa.String(length=50), nullable=True),
        sa.Column("to_number", sa.String(length=50), nullable=True),
        sa.Column("message_text", sa.Text(), nullable=True),
        sa.Column("direction", sa.String(length=12), nullable=False, server_default="IN"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_qr_whatsapp_messages_company_id", "qr_whatsapp_messages", ["company_id"], unique=False)
    op.create_index("ix_qr_whatsapp_messages_connection_id", "qr_whatsapp_messages", ["connection_id"], unique=False)
    op.create_index("ix_qr_whatsapp_messages_message_id", "qr_whatsapp_messages", ["message_id"], unique=True)
