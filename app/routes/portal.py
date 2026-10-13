from datetime import timedelta
from functools import wraps

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.database import db
from app.models import Company, Payment, Service, ServicePlan, Subscription, User, WhatsAppConnection, utcnow

portal_bp = Blueprint("portal", __name__)


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Inicia sesión para continuar.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def seed_catalog():
    service = Service.query.filter_by(slug="crm-chatbot").first()
    if not service:
        service = Service(
            name="CRM + Chatbot",
            slug="crm-chatbot",
            icon="🤖",
            description="Gestiona clientes, conversaciones de WhatsApp y automatizaciones desde un solo lugar.",
            active=True,
        )
        db.session.add(service)
        db.session.flush()
        db.session.add(ServicePlan(
            service_id=service.id,
            name="Profesional",
            price=120000,
            billing_period="monthly",
            features=[
                "CRM de clientes",
                "WhatsApp Business",
                "Bandeja de conversaciones",
                "Chatbot y respuestas automáticas",
                "Automatizaciones con n8n",
                "Etiquetas y respuestas rápidas",
            ],
            active=True,
        ))
        db.session.commit()

    # Catálogo inicial para ampliar posteriormente sin cambiar la arquitectura.
    extras = [
        ("Inventario", "inventario", "📦", "Controla existencias, movimientos y productos."),
        ("Caja y ventas", "caja-ventas", "💰", "Digitaliza caja, ventas y operación diaria."),
        ("Reportes", "reportes", "📊", "Convierte los datos de tu negocio en información útil."),
    ]
    changed = False
    for name, slug, icon, description in extras:
        if not Service.query.filter_by(slug=slug).first():
            db.session.add(Service(name=name, slug=slug, icon=icon, description=description, active=False))
            changed = True
    if changed:
        db.session.commit()


def active_subscription(company_id):
    return (
        Subscription.query.join(ServicePlan, Subscription.service_plan_id == ServicePlan.id)
        .join(Service, ServicePlan.service_id == Service.id)
        .filter(
            Subscription.company_id == company_id,
            Subscription.status == "ACTIVE",
            Service.slug == "crm-chatbot",
        )
        .order_by(Subscription.created_at.desc())
        .first()
    )


@portal_bp.get("/registro")
def register():
    if current_user():
        return redirect(url_for("portal.dashboard"))
    return render_template("register.html")


@portal_bp.post("/registro")
def register_post():
    if current_user():
        return redirect(url_for("portal.dashboard"))

    name = request.form.get("nombre", "").strip()
    company_name = request.form.get("empresa", "").strip()
    email = request.form.get("correo", "").strip().lower()
    password = request.form.get("password", "")

    if not name or not company_name or not email or len(password) < 8:
        flash("Completa todos los campos. La contraseña debe tener mínimo 8 caracteres.", "error")
        return render_template("register.html")

    if User.query.filter_by(email=email).first():
        flash("Ya existe una cuenta con ese correo.", "error")
        return render_template("register.html")

    company = Company(name=company_name, email=email)
    db.session.add(company)
    db.session.flush()
    user = User(
        company_id=company.id,
        full_name=name,
        email=email,
        password_hash=generate_password_hash(password),
    )
    db.session.add(user)
    db.session.commit()

    session.clear()
    session["user_id"] = user.id
    session["company_id"] = company.id
    flash("Cuenta creada. Ahora elige el servicio que quieres contratar.", "success")
    return redirect(url_for("portal.dashboard"))


@portal_bp.post("/login")
def login_post():
    email = request.form.get("correo", "").strip().lower()
    password = request.form.get("password", "")
    user = User.query.filter_by(email=email, is_active=True).first()

    if not user or not check_password_hash(user.password_hash, password):
        flash("Correo o contraseña incorrectos.", "error")
        return redirect(url_for("login"))

    session.clear()
    session["user_id"] = user.id
    session["company_id"] = user.company_id
    flash("Bienvenido a NOXTIUM.", "success")
    return redirect(url_for("portal.dashboard"))


@portal_bp.get("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada.", "success")
    return redirect(url_for("inicio"))


@portal_bp.get("/dashboard")
@login_required
def dashboard():
    seed_catalog()
    user = current_user()
    subscription = active_subscription(user.company_id)
    pending = (
        Subscription.query.join(ServicePlan).join(Service)
        .filter(Subscription.company_id == user.company_id, Subscription.status == "PENDING_PAYMENT")
        .order_by(Subscription.created_at.desc()).first()
    )
    whatsapp = WhatsAppConnection.query.filter_by(company_id=user.company_id, status="active").first()
    services = Service.query.filter_by(active=True).order_by(Service.id).all()
    return render_template(
        "dashboard.html",
        user=user,
        company=user.company,
        subscription=subscription,
        pending=pending,
        whatsapp=whatsapp,
        services=services,
    )


@portal_bp.get("/servicios/<slug>")
@login_required
def service_detail(slug):
    seed_catalog()
    user = current_user()
    service = Service.query.filter_by(slug=slug, active=True).first_or_404()
    plans = ServicePlan.query.filter_by(service_id=service.id, active=True).order_by(ServicePlan.price).all()
    return render_template("service_detail.html", service=service, plans=plans, user=user)


@portal_bp.post("/servicios/<slug>/contratar")
@login_required
def contract_service(slug):
    seed_catalog()
    user = current_user()
    service = Service.query.filter_by(slug=slug, active=True).first_or_404()
    plan = ServicePlan.query.filter_by(id=request.form.get("plan_id"), service_id=service.id, active=True).first()
    if not plan:
        flash("El plan seleccionado no es válido.", "error")
        return redirect(url_for("portal.service_detail", slug=slug))

    existing = active_subscription(user.company_id)
    if existing and existing.plan.service_id == service.id:
        flash("Ya tienes este servicio activo.", "success")
        return redirect(url_for("portal.dashboard"))

    pending = Subscription.query.filter_by(company_id=user.company_id, status="PENDING_PAYMENT").first()
    if pending:
        return redirect(url_for("portal.payment", subscription_id=pending.id))

    subscription = Subscription(company_id=user.company_id, service_plan_id=plan.id, status="PENDING_PAYMENT")
    db.session.add(subscription)
    db.session.flush()
    db.session.add(Payment(subscription_id=subscription.id, amount=plan.price, status="PENDING", provider="pending_provider"))
    db.session.commit()
    return redirect(url_for("portal.payment", subscription_id=subscription.id))


@portal_bp.get("/pago/<int:subscription_id>")
@login_required
def payment(subscription_id):
    user = current_user()
    subscription = db.session.get(Subscription, subscription_id)
    if not subscription or subscription.company_id != user.company_id:
        flash("Suscripción no encontrada.", "error")
        return redirect(url_for("portal.dashboard"))
    payment = Payment.query.filter_by(subscription_id=subscription.id).order_by(Payment.created_at.desc()).first()
    return render_template("payment.html", subscription=subscription, payment=payment, user=user)


@portal_bp.post("/pago/<int:subscription_id>/confirmar-demo")
@login_required
def confirm_demo_payment(subscription_id):
    # Ruta temporal para pruebas locales. Sustituiremos esto por Wompi/PayU/Stripe.
    if not current_app.config.get("DEVELOPMENT_PAYMENT_DEMO", False):
        flash("La confirmación de pago de prueba está desactivada.", "error")
        return redirect(url_for("portal.dashboard"))
    user = current_user()
    subscription = db.session.get(Subscription, subscription_id)
    if not subscription or subscription.company_id != user.company_id:
        flash("Suscripción no encontrada.", "error")
        return redirect(url_for("portal.dashboard"))
    if subscription.status == "ACTIVE":
        return redirect(url_for("portal.dashboard"))

    payment = Payment.query.filter_by(subscription_id=subscription.id).order_by(Payment.created_at.desc()).first()
    subscription.status = "ACTIVE"
    subscription.starts_at = utcnow()
    subscription.expires_at = utcnow() + timedelta(days=30)
    if payment:
        payment.status = "PAID"
        payment.provider = "development"
        payment.transaction_id = f"DEMO-{subscription.id}-{int(utcnow().timestamp())}"
        payment.paid_at = utcnow()
    db.session.commit()
    flash("Pago de prueba confirmado. El servicio ya está activo.", "success")
    return redirect(url_for("portal.dashboard"))
