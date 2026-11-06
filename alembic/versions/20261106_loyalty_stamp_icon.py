"""Add a configurable icon for each loyalty stamp."""
from alembic import op
import sqlalchemy as sa

revision = "20261106_stamp_icon"
down_revision = "20261106_loyalty_trial"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("loyalty_programs", sa.Column("stamp_icon", sa.String(length=20), nullable=False, server_default="✦"))


def downgrade():
    op.drop_column("loyalty_programs", "stamp_icon")
