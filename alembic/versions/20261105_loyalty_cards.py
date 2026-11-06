"""Add tenant-isolated loyalty cards, visits, campaigns and plan access."""
from alembic import op
import sqlalchemy as sa

revision = "20261105_loyalty"
down_revision = "20261020_remove_qr"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('loyalty_programs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('title', sa.String(120), nullable=False, server_default='Tarjeta de lealtad'),
        sa.Column('business_name', sa.String(150), nullable=False),
        sa.Column('icon', sa.String(20), nullable=False, server_default='⭐'),
        sa.Column('color', sa.String(7), nullable=False, server_default='#6d5dfc'),
        sa.Column('stamps_goal', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('reward_text', sa.String(255), nullable=False, server_default='Obtén una recompensa'),
        sa.Column('trial_started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_loyalty_programs_company_id','loyalty_programs',['company_id'])
    op.create_table('loyalty_customers',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('company_id',sa.Integer(),sa.ForeignKey('companies.id',ondelete='CASCADE'),nullable=False),
        sa.Column('program_id',sa.Integer(),sa.ForeignKey('loyalty_programs.id',ondelete='CASCADE'),nullable=False),
        sa.Column('name',sa.String(150),nullable=False),sa.Column('phone',sa.String(50),nullable=False),sa.Column('email',sa.String(255)),
        sa.Column('token',sa.String(64),nullable=False,unique=True),sa.Column('notification_consent',sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column('stamps',sa.Integer(),nullable=False,server_default='0'),sa.Column('last_visit_at',sa.DateTime(timezone=True)),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('company_id','phone',name='uq_loyalty_customer_company_phone'))
    for col in ('company_id','program_id','token'): op.create_index('ix_loyalty_customers_'+col,'loyalty_customers',[col],unique=(col=='token'))
    op.create_table('loyalty_stamps',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('company_id',sa.Integer(),sa.ForeignKey('companies.id',ondelete='CASCADE'),nullable=False),sa.Column('customer_id',sa.Integer(),sa.ForeignKey('loyalty_customers.id',ondelete='CASCADE'),nullable=False),sa.Column('approved_by_user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='SET NULL')),sa.Column('note',sa.String(255)),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_loyalty_stamps_company_id','loyalty_stamps',['company_id']); op.create_index('ix_loyalty_stamps_customer_id','loyalty_stamps',['customer_id'])
    op.create_table('loyalty_campaigns',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('company_id',sa.Integer(),sa.ForeignKey('companies.id',ondelete='CASCADE'),nullable=False),sa.Column('title',sa.String(150),nullable=False),sa.Column('message',sa.Text(),nullable=False),sa.Column('sent_count',sa.Integer(),nullable=False,server_default='0'),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_loyalty_campaigns_company_id','loyalty_campaigns',['company_id'])
    op.create_table('loyalty_push_subscriptions',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('company_id',sa.Integer(),sa.ForeignKey('companies.id',ondelete='CASCADE'),nullable=False),sa.Column('customer_id',sa.Integer(),sa.ForeignKey('loyalty_customers.id',ondelete='CASCADE'),nullable=False),sa.Column('endpoint',sa.Text(),nullable=False,unique=True),sa.Column('p256dh',sa.String(255),nullable=False),sa.Column('auth',sa.String(255),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_loyalty_push_subscriptions_company_id','loyalty_push_subscriptions',['company_id']); op.create_index('ix_loyalty_push_subscriptions_customer_id','loyalty_push_subscriptions',['customer_id'])
    op.create_table('loyalty_plan_purchases',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('company_id',sa.Integer(),sa.ForeignKey('companies.id',ondelete='CASCADE'),nullable=False),sa.Column('plan_code',sa.String(30),nullable=False),sa.Column('amount',sa.Integer(),nullable=False),sa.Column('status',sa.String(20),nullable=False,server_default='PENDING'),sa.Column('receipt_filename',sa.String(255)),sa.Column('starts_at',sa.DateTime(timezone=True)),sa.Column('expires_at',sa.DateTime(timezone=True)),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_loyalty_plan_purchases_company_id','loyalty_plan_purchases',['company_id'])


def downgrade():
    for table in ['loyalty_plan_purchases','loyalty_push_subscriptions','loyalty_campaigns','loyalty_stamps','loyalty_customers','loyalty_programs']:
        op.drop_table(table)
