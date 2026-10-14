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


class QRWhatsAppConnection(db.Model):
    __tablename__ = "qr_whatsapp_connections"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    phone_number = db.Column(db.String(50))
    verified_name = db.Column(db.String(255))
    status = db.Column(db.String(30), nullable=False, default="disconnected", index=True)
    last_error = db.Column(db.Text)
    linked_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    @property
    def display_phone_number(self):
        return self.phone_number


class QRWhatsAppMessage(db.Model):
    __tablename__ = "qr_whatsapp_messages"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    connection_id = db.Column(db.Integer, db.ForeignKey("qr_whatsapp_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = db.Column(db.String(255), nullable=False, unique=True, index=True)
    from_number = db.Column(db.String(50))
    to_number = db.Column(db.String(50))
    message_text = db.Column(db.Text)
    direction = db.Column(db.String(12), nullable=False, default="IN")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
