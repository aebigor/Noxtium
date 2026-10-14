"""Add role to users table."""
from alembic import op
import sqlalchemy as sa

revision = "0003_add_user_role"
down_revision = "0002_billing_portal"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Compatible con bases donde users ya existe pero role no fue creado.
    if "users" not in inspector.get_table_names():
        raise RuntimeError(
            "No existe la tabla users. Ejecuta primero las migraciones anteriores."
        )

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "role" not in columns:
        op.add_column(
            "users",
            sa.Column("role", sa.String(length=20), nullable=False, server_default="client"),
        )

    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("users")}
    if "ix_users_role" not in indexes:
        op.create_index("ix_users_role", "users", ["role"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" not in inspector.get_table_names():
        return

    indexes = {index["name"] for index in inspector.get_indexes("users")}
    if "ix_users_role" in indexes:
        op.drop_index("ix_users_role", table_name="users")

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "role" in columns:
        op.drop_column("users", "role")
