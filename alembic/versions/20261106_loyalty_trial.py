"""Make loyalty demo opt-in and begin it only after admin approval."""
from alembic import op
import sqlalchemy as sa

revision = "20261106_loyalty_trial"
down_revision = "20261105_loyalty_consent"
branch_labels = None
depends_on = None


def upgrade():
    # Existing records received a default start date at account creation. Clear it:
    # no business should lose demo days before requesting and receiving approval.
    op.execute("UPDATE loyalty_programs SET trial_started_at = NULL")
    op.alter_column("loyalty_programs", "trial_started_at", existing_type=sa.DateTime(timezone=True), nullable=True, server_default=None)


def downgrade():
    # On downgrade, initialize missing dates to migration time to satisfy NOT NULL.
    op.execute("UPDATE loyalty_programs SET trial_started_at = CURRENT_TIMESTAMP WHERE trial_started_at IS NULL")
    op.alter_column("loyalty_programs", "trial_started_at", existing_type=sa.DateTime(timezone=True), nullable=False)
