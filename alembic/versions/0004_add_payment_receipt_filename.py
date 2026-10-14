"""Add missing receipt_filename column to payments."""
from alembic import op
import sqlalchemy as sa

# Alembic stores version_num in VARCHAR(32); keep revision ID under 32 chars.
revision = "0004_payment_receipt"
down_revision = "0003_add_user_role"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "payments" not in tables:
        raise RuntimeError(
            "No existe la tabla payments. Verifica que las migraciones anteriores estén aplicadas."
        )

    columns = {column["name"] for column in inspector.get_columns("payments")}
    if "receipt_filename" not in columns:
        op.add_column(
            "payments",
            sa.Column("receipt_filename", sa.String(length=255), nullable=True),
        )


def downgrade():
    # No elimina la columna para evitar perder nombres de comprobantes.
    pass
