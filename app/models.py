from datetime import datetime, timezone

from .database import db


def utcnow():
    return datetime.now(timezone.utc)


class Company(db.Model):
    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(255), nullable=True, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    users = db.relationship("User", back_populates="company", cascade="all, delete-orphan")
    whatsapp_connections = db.relationship(
        "WhatsAppConnection", back_populates="company", cascade="all, delete-orphan"
    )
    subscriptions = db.relationship(
        "Subscription", back_populates="company", cascade="all, delete-orphan"
    )


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="client", index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    company = db.relationship("Company", back_populates="users")


class Service(db.Model):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(120), nullable=False, unique=True, index=True)
    description = db.Column(db.Text, nullable=False)
    icon = db.Column(db.String(20), nullable=False, default="✦")
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    plans = db.relationship("ServicePlan", back_populates="service", cascade="all, delete-orphan")


class ServicePlan(db.Model):
    __tablename__ = "service_plans"

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    billing_period = db.Column(db.String(30), nullable=False, default="monthly")
    features = db.Column(db.JSON, nullable=False, default=list)
    # Included AI/model tokens available for the n8n automations during this plan.
    included_tokens = db.Column(db.Integer, nullable=False, default=0)
    active = db.Column(db.Boolean, default=True, nullable=False)

    service = db.relationship("Service", back_populates="plans")
    subscriptions = db.relationship("Subscription", back_populates="plan")


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    service_plan_id = db.Column(db.Integer, db.ForeignKey("service_plans.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="PENDING_PAYMENT", index=True)
    starts_at = db.Column(db.DateTime(timezone=True))
    expires_at = db.Column(db.DateTime(timezone=True))
    # External products (e.g. Inventario) are provisioned in their own application.
    # CRM remains native to NOXTIUM and does not use this handoff URL.
    external_access_url = db.Column(db.String(1000))
    provisioning_status = db.Column(db.String(30), nullable=False, default="NOT_REQUIRED")
    # Token allowance is snapshotted when payment is approved.
    token_limit = db.Column(db.Integer, nullable=False, default=0)
    tokens_used = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    company = db.relationship("Company", back_populates="subscriptions")
    plan = db.relationship("ServicePlan", back_populates="subscriptions")
    payments = db.relationship("Payment", back_populates="subscription", cascade="all, delete-orphan")


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="PENDING", index=True)
    provider = db.Column(db.String(50), nullable=False, default="manual")
    transaction_id = db.Column(db.String(150), index=True)
    receipt_filename = db.Column(db.String(255))
    paid_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    subscription = db.relationship("Subscription", back_populates="payments")


class WhatsAppConnection(db.Model):
    __tablename__ = "whatsapp_connections"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    waba_id = db.Column(db.String(100), nullable=False, index=True)
    phone_number_id = db.Column(db.String(100), nullable=False, unique=True, index=True)
    display_phone_number = db.Column(db.String(50))
    verified_name = db.Column(db.String(255))
    access_token_encrypted = db.Column(db.Text, nullable=False)
    token_type = db.Column(db.String(80), default="business_integration_system_user", nullable=False)
    status = db.Column(db.String(30), default="active", nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    company = db.relationship("Company", back_populates="whatsapp_connections")
    messages = db.relationship("WhatsAppMessage", back_populates="connection", cascade="all, delete-orphan")


class WhatsAppMessage(db.Model):
    __tablename__ = "whatsapp_messages"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    whatsapp_connection_id = db.Column(db.Integer, db.ForeignKey("whatsapp_connections.id"), nullable=False, index=True)
    message_id = db.Column(db.String(255), nullable=False, unique=True, index=True)
    from_number = db.Column(db.String(50))
    to_number = db.Column(db.String(50))
    message_type = db.Column(db.String(50))
    message_text = db.Column(db.Text)
    raw_payload = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    connection = db.relationship("WhatsAppConnection", back_populates="messages")


class ConsultationRequest(db.Model):
    __tablename__ = "consultation_requests"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_method = db.Column(db.String(20), nullable=False)  # whatsapp | email
    contact_value = db.Column(db.String(255), nullable=False)
    preferred_date = db.Column(db.String(40))
    preferred_time = db.Column(db.String(40))
    modules = db.Column(db.JSON, nullable=False, default=list)
    business_description = db.Column(db.Text)
    status = db.Column(db.String(30), nullable=False, default="PENDING", index=True)
    admin_notes = db.Column(db.Text)
    meeting_url = db.Column(db.String(1000))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    company = db.relationship("Company")
    user = db.relationship("User")


class AgentConfiguration(db.Model):
    __tablename__ = "agent_configurations"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    restaurant_name = db.Column(db.String(150), nullable=False)
    business_type = db.Column(db.String(80), nullable=False, default="Restaurante")
    address = db.Column(db.String(255))
    opening_hours = db.Column(db.Text)
    delivery_zones = db.Column(db.Text)
    menu_items = db.Column(db.JSON, nullable=False, default=list)
    sales_tone = db.Column(db.String(40), nullable=False, default="amable")
    special_rules = db.Column(db.Text)
    welcome_message = db.Column(db.String(500))
    status = db.Column(db.String(30), nullable=False, default="SETUP", index=True)
    n8n_workflow_id = db.Column(db.String(120))
    last_tested_at = db.Column(db.DateTime(timezone=True))
    last_error = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class CRMContact(db.Model):
    __tablename__ = "crm_contacts"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    phone = db.Column(db.String(50), nullable=False)
    contact_name = db.Column(db.String(150))
    status = db.Column(db.String(20), nullable=False, default="NEW", index=True)
    tags = db.Column(db.JSON, nullable=False, default=list)
    notes = db.Column(db.Text)
    last_message_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    __table_args__ = (db.UniqueConstraint("company_id", "phone", name="uq_crm_contacts_company_phone"),)


class LeadInquiry(db.Model):
    """Public product/idea inquiries submitted before a visitor creates an account."""
    __tablename__ = "lead_inquiries"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(255), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="NEW", index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class N8NTokenUsageEvent(db.Model):
    """Idempotent usage events reported by n8n after an AI/model call."""
    __tablename__ = "n8n_token_usage_events"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = db.Column(db.String(200), nullable=False)
    input_tokens = db.Column(db.Integer, nullable=False, default=0)
    output_tokens = db.Column(db.Integer, nullable=False, default=0)
    total_tokens = db.Column(db.Integer, nullable=False, default=0)
    workflow_id = db.Column(db.String(120))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (db.UniqueConstraint("company_id", "event_id", name="uq_n8n_token_event_company_event"),)

# Loyalty cards module (tenant isolated). Consent is stored per channel for auditable campaigns.
from uuid import uuid4 as _loyalty_uuid4

class LoyaltyProgram(db.Model):
    __tablename__ = "loyalty_programs"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    title = db.Column(db.String(120), nullable=False, default="Tarjeta de lealtad")
    business_name = db.Column(db.String(150), nullable=False)
    icon = db.Column(db.String(20), nullable=False, default="⭐")
    color = db.Column(db.String(7), nullable=False, default="#6d5dfc")
    stamps_goal = db.Column(db.Integer, nullable=False, default=5)
    reward_text = db.Column(db.String(255), nullable=False, default="Obtén una recompensa")
    trial_started_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

class LoyaltyCustomer(db.Model):
    __tablename__ = "loyalty_customers"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    program_id = db.Column(db.Integer, db.ForeignKey("loyalty_programs.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(255))
    token = db.Column(db.String(64), nullable=False, unique=True, index=True, default=lambda: _loyalty_uuid4().hex)
    notification_consent = db.Column(db.Boolean, nullable=False, default=False)
    privacy_consent = db.Column(db.Boolean, nullable=False, default=False)
    consent_whatsapp = db.Column(db.Boolean, nullable=False, default=False)
    consent_sms = db.Column(db.Boolean, nullable=False, default=False)
    consent_push = db.Column(db.Boolean, nullable=False, default=False)
    consent_at = db.Column(db.DateTime(timezone=True))
    consent_text_version = db.Column(db.String(30))
    stamps = db.Column(db.Integer, nullable=False, default=0)
    last_visit_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (db.UniqueConstraint("company_id", "phone", name="uq_loyalty_customer_company_phone"),)

class LoyaltyStamp(db.Model):
    __tablename__ = "loyalty_stamps"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("loyalty_customers.id", ondelete="CASCADE"), nullable=False, index=True)
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

class LoyaltyCampaign(db.Model):
    __tablename__ = "loyalty_campaigns"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    sent_count = db.Column(db.Integer, nullable=False, default=0)
    target_type = db.Column(db.String(20), nullable=False, default="mass")
    target_customer_id = db.Column(db.Integer, db.ForeignKey("loyalty_customers.id", ondelete="SET NULL"))
    channel = db.Column(db.String(20), nullable=False, default="push")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

class LoyaltyPushSubscription(db.Model):
    __tablename__ = "loyalty_push_subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("loyalty_customers.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint = db.Column(db.Text, nullable=False, unique=True)
    p256dh = db.Column(db.String(255), nullable=False)
    auth = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

class LoyaltyPlanPurchase(db.Model):
    __tablename__ = "loyalty_plan_purchases"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_code = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="PENDING")
    receipt_filename = db.Column(db.String(255))
    starts_at = db.Column(db.DateTime(timezone=True))
    expires_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
