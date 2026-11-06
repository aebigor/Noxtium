"""Store granular loyalty consent and campaign targeting."""
from alembic import op
import sqlalchemy as sa

revision = "20261105_loyalty_consent"
down_revision = "20261105_loyalty"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('loyalty_customers', sa.Column('privacy_consent', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('loyalty_customers', sa.Column('consent_whatsapp', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('loyalty_customers', sa.Column('consent_sms', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('loyalty_customers', sa.Column('consent_push', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('loyalty_customers', sa.Column('consent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('loyalty_customers', sa.Column('consent_text_version', sa.String(30), nullable=True))
    op.add_column('loyalty_campaigns', sa.Column('target_type', sa.String(20), nullable=False, server_default='mass'))
    op.add_column('loyalty_campaigns', sa.Column('target_customer_id', sa.Integer(), sa.ForeignKey('loyalty_customers.id', ondelete='SET NULL'), nullable=True))
    op.add_column('loyalty_campaigns', sa.Column('channel', sa.String(20), nullable=False, server_default='push'))

def downgrade():
    op.drop_column('loyalty_campaigns', 'channel')
    op.drop_column('loyalty_campaigns', 'target_customer_id')
    op.drop_column('loyalty_campaigns', 'target_type')
    op.drop_column('loyalty_customers', 'consent_text_version')
    op.drop_column('loyalty_customers', 'privacy_consent')
    op.drop_column('loyalty_customers', 'consent_at')
    op.drop_column('loyalty_customers', 'consent_push')
    op.drop_column('loyalty_customers', 'consent_sms')
    op.drop_column('loyalty_customers', 'consent_whatsapp')
