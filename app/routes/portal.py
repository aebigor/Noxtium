from datetime import timedelta
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for, abort
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from app.database import db
from app.models import (Company, Payment, Service, ServicePlan, Subscription, User,
                        WhatsAppConnection, WhatsAppMessage, ConsultationRequest, AgentConfiguration, CRMContact, LeadInquiry, utcnow)

portal_bp = Blueprint("portal", __name__)
ALLOWED_RECEIPT_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = db.session.get(User, user_id)
    if not user or not user.is_active:
        session.clear()
        return None
    return user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Inicia sesión para continuar.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Inicia sesión para continuar.", "error")
            return redirect(url_for("login"))
        if user.role != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def is_admin(user=None):
    user = user or current_user()
    return bool(user and user.role == "admin")


def seed_catalog():
    """Create/update the public catalogue; existing plan prices are synchronized too."""
    service = Service.query.filter_by(slug="crm-chatbot").first()
    if not service:
        service = Service(name="CRM + Agentes comerciales", slug="crm-chatbot", icon="🤖",
            description="Gestiona clientes, conversaciones de WhatsApp y automatizaciones desde un solo lugar.", active=True)
        db.session.add(service)
        db.session.flush()
    else:
        service.name = "CRM + Agentes comerciales"
        service.active = True

    crm_features = [
        "CRM de clientes y seguimiento comercial",
        "Conexión oficial de WhatsApp Business con Meta",
        "Bandeja de conversaciones",
        "Agente comercial y respuestas automáticas",
        "Automatizaciones con n8n",
        "Cupo de tokens de IA incluido para automatizaciones",
    ]
    crm_plans = [
        ("Profesional mensual", 300000, "monthly", current_app.config.get("NOXTIUM_CRM_MONTHLY_TOKENS", 100000)),
        ("Trimestral", 800000, "quarterly", current_app.config.get("NOXTIUM_CRM_QUARTERLY_TOKENS", 300000)),
        ("Anual", 2400000, "annual", current_app.config.get("NOXTIUM_CRM_ANNUAL_TOKENS", 1200000)),
    ]
    for name, price, period, token_quota in crm_plans:
        existing = ServicePlan.query.filter_by(service_id=service.id, billing_period=period).first()
        plan_features = crm_features + [f"{int(token_quota):,}".replace(",", ".") + " tokens de IA para el período contratado"]
        if not existing:
            db.session.add(ServicePlan(service_id=service.id, name=name, price=price,
                billing_period=period, features=plan_features, included_tokens=int(token_quota), active=True))
        else:
            # Update names, prices, quota and benefits on every seed; never leave old prices behind.
            existing.name = name
            existing.price = price
            existing.active = True
            existing.features = plan_features
            existing.included_tokens = int(token_quota)

    catalog = [
        ("Inventario para colegios", "inventario", "📦", "Organiza equipos, materiales, existencias y movimientos del colegio en una aplicación independiente. NOXTIUM coordina la solicitud y la habilitación del acceso.", True),
        ("Software de restaurante", "imperio-del-barril", "🍽️", "Contrata únicamente los módulos que necesitas —menú, meseros, cocina, caja, asistencia, inventario y reportes— o el paquete completo.", True),
        ("Desarrollo de software a la medida", "integracion-modulos", "✦", "Cuéntanos tu idea, el problema que quieres resolver o la función que te gustaría tener. Diseñamos soluciones junto a quienes las van a usar.", True),
        ("Tarjetas de lealtad", "tarjetas-lealtad", "🎟️", "Crea tarjetas digitales personalizadas, fideliza clientes, registra visitas y comparte promociones.", True),
        ("Caja y ventas", "caja-ventas", "💰", "Digitaliza caja, ventas y operación diaria.", False),
        ("Reportes", "reportes", "📊", "Convierte los datos de tu negocio en información útil.", False),
    ]
    for name, slug, icon, description, active in catalog:
        existing = Service.query.filter_by(slug=slug).first()
        if not existing:
            existing = Service(name=name, slug=slug, icon=icon, description=description, active=active)
            db.session.add(existing)
            db.session.flush()
        else:
            existing.name = name
            existing.description = description
            existing.icon = icon
            existing.active = active

    # Inventory prices remain configurable and unavailable until their prices are set.
    inventory = Service.query.filter_by(slug="inventario").first()
    inventory_prices = [
        ("Inventario mensual", current_app.config.get("NOXTIUM_INVENTORY_MONTHLY_PRICE", 180000), "monthly"),
        ("Inventario trimestral", current_app.config.get("NOXTIUM_INVENTORY_QUARTERLY_PRICE", 480000), "quarterly"),
        ("Inventario anual", current_app.config.get("NOXTIUM_INVENTORY_ANNUAL_PRICE", 1800000), "annual"),
    ]
    inventory_features = ["Inventario de equipos y materiales del colegio", "Registro de entradas, salidas y movimientos", "Acceso independiente por institución", "Activación coordinada desde NOXTIUM"]
    for name, price, period in inventory_prices:
        if not price or int(price) < 1:
            continue
        plan = ServicePlan.query.filter_by(service_id=inventory.id, billing_period=period).first()
        if not plan:
            db.session.add(ServicePlan(service_id=inventory.id, name=name, price=int(price), billing_period=period, features=inventory_features, included_tokens=0, active=True))
        else:
            plan.name, plan.price, plan.features, plan.active = name, int(price), inventory_features, True

    # Restaurant modules are one-time activation fees. Ongoing access/maintenance is billed separately
    # through the operating plans below; the internal slug remains for backward compatibility.
    restaurant = Service.query.filter_by(slug="imperio-del-barril").first()
    restaurant_plans = [
        ("Operación mensual", 150000, "monthly", ["Acceso al software de restaurante durante 1 mes", "Actualizaciones y soporte básico", "Los módulos se contratan por separado"]),
        ("Operación trimestral", 420000, "quarterly", ["Acceso al software de restaurante durante 3 meses", "Actualizaciones y soporte básico", "Los módulos se contratan por separado"]),
        ("Operación anual", 1500000, "annual", ["Acceso al software de restaurante durante 12 meses", "Actualizaciones y soporte básico", "Los módulos se contratan por separado"]),
    ]
    for name, price, period, plan_features in restaurant_plans:
        existing = ServicePlan.query.filter_by(service_id=restaurant.id, name=name).first()
        if not existing:
            db.session.add(ServicePlan(service_id=restaurant.id, name=name, price=price,
                billing_period=period, features=plan_features, included_tokens=0, active=True))
        else:
            existing.price = price
            existing.billing_period = period
            existing.features = plan_features
            existing.included_tokens = 0
            existing.active = True

    for name, price, plan_features in [
        ("Menú digital", 100000, ["Menú digital", "Productos, descripciones y precios"]),
        ("Meseros y comandas", 250000, ["Gestión de meseros", "Comandas por mesa y seguimiento de pedidos"]),
        ("Cocina", 250000, ["Panel de cocina", "Preparación y estados de pedidos"]),
        ("Caja y ventas", 350000, ["Caja", "Registro de ventas y cierre de turno"]),
        ("Asistencia del personal", 150000, ["Registro de asistencia", "Control de entradas y salidas"]),
        ("Inventario y alertas", 250000, ["Inventario del restaurante", "Descuento de existencias y alertas de bajo stock"]),
        ("Reportes e indicadores", 150000, ["Reportes operativos", "Indicadores básicos del negocio"]),
        ("Paquete completo", 1500000, ["Incluye menú digital, meseros, cocina, caja, asistencia, inventario y reportes", "Paquete completo para la operación del restaurante"]),
    ]:
        existing = ServicePlan.query.filter_by(service_id=restaurant.id, name=name).first()
        if not existing:
            db.session.add(ServicePlan(service_id=restaurant.id, name=name, price=price, billing_period="one_time", features=plan_features, included_tokens=0, active=True))
        else:
            existing.price, existing.billing_period, existing.features, existing.included_tokens, existing.active = price, "one_time", plan_features, 0, True

    # Existing active CRM customers are granted the plan's token allowance after this migration/seed.
    db.session.flush()
    active_crm = (Subscription.query.join(ServicePlan).join(Service)
        .filter(Subscription.status == "ACTIVE", Service.slug == "crm-chatbot").all())
    for sub in active_crm:
        if not sub.token_limit or sub.token_limit < 1:
            sub.token_limit = int(sub.plan.included_tokens or 0)
    db.session.commit()


def _expire_overdue_subscriptions():
    now = utcnow()
    overdue = Subscription.query.filter(
        Subscription.status == "ACTIVE",
        Subscription.expires_at.isnot(None),
        Subscription.expires_at <= now,
    ).all()
    for subscription in overdue:
        subscription.status = "EXPIRED"
        # Expiring an external product (e.g. Inventario) must never pause the CRM agent.
        if subscription.plan.service.slug == "crm-chatbot":
            agent = AgentConfiguration.query.filter_by(company_id=subscription.company_id).first()
            if agent:
                agent.status = "PAUSED"
                agent.last_error = "La suscripción venció. Renueva el plan para reactivar el servicio."
    if overdue:
        db.session.commit()


def _plan_duration_days(plan):
    period = (plan.billing_period or "monthly").lower()
    if period in {"one_time", "onetime", "lifetime"}:
        return None
    return {"monthly": 30, "month": 30, "quarterly": 90, "3_months": 90,
            "annual": 365, "yearly": 365, "year": 365}.get(period, 30)


def active_subscription(company_id, service_slug="crm-chatbot"):
    now = utcnow()
    return (Subscription.query.join(ServicePlan, Subscription.service_plan_id == ServicePlan.id)
        .join(Service, ServicePlan.service_id == Service.id)
        .filter(Subscription.company_id == company_id, Subscription.status == "ACTIVE",
                Service.slug == service_slug,
                db.or_(Subscription.expires_at.is_(None), Subscription.expires_at > now))
        .order_by(Subscription.created_at.desc()).first())


def pending_subscription(company_id, service_slug="crm-chatbot"):
    return (Subscription.query.join(ServicePlan).join(Service)
        .filter(Subscription.company_id == company_id, Subscription.status == "PENDING_PAYMENT", Service.slug == service_slug)
        .order_by(Subscription.created_at.desc()).first())


@portal_bp.get("/registro")
def register():
    if current_user(): return redirect(url_for("portal.dashboard"))
    selected_product = (request.args.get("producto") or "").strip()
    if selected_product not in {"crm-chatbot", "inventario", "imperio-del-barril", "tarjetas-lealtad"}:
        selected_product = ""
    return render_template("register.html", selected_product=selected_product)


@portal_bp.post("/registro")
def register_post():
    if current_user(): return redirect(url_for("portal.dashboard"))
    name = request.form.get("nombre", "").strip()
    company_name = request.form.get("empresa", "").strip()
    email = request.form.get("correo", "").strip().lower()
    password = request.form.get("password", "")
    selected_product = (request.form.get("producto") or "").strip()
    if selected_product not in {"crm-chatbot", "inventario", "imperio-del-barril", "tarjetas-lealtad"}:
        selected_product = ""
    if not name or not company_name or not email or len(password) < 8:
        flash("Completa todos los campos. La contraseña debe tener mínimo 8 caracteres.", "error")
        return render_template("register.html")
    if User.query.filter_by(email=email).first():
        flash("Ya existe una cuenta con ese correo.", "error")
        return render_template("register.html")
    company = Company(name=company_name, email=email, is_active=True)
    db.session.add(company); db.session.flush()
    user = User(company_id=company.id, full_name=name, email=email,
                password_hash=generate_password_hash(password), role="client")
    db.session.add(user); db.session.commit()
    session.clear(); session["user_id"] = user.id; session["company_id"] = company.id
    flash("Cuenta creada. Continúa con el producto que elegiste o revisa las herramientas disponibles.", "success")
    if selected_product:
        return redirect(url_for("portal.service_detail", slug=selected_product))
    return redirect(url_for("portal.dashboard"))


@portal_bp.post("/login")
def login_post():
    email = request.form.get("correo", "").strip().lower()
    password = request.form.get("password", "")
    user = User.query.filter_by(email=email, is_active=True).first()
    if not user or not check_password_hash(user.password_hash, password):
        flash("Correo o contraseña incorrectos.", "error"); return redirect(url_for("login"))
    # Synchronize the configured owner account to the administrative role.
    if email in current_app.config.get("ADMIN_EMAILS", []):
        user.role = "admin"
        if user.company and user.company.name.strip().lower() != "noxtium":
            user.company.name = "NOXTIUM"
        db.session.commit()
    session.clear(); session["user_id"] = user.id; session["company_id"] = user.company_id
    flash("Bienvenido al panel de NOXTIUM." if user.role == "admin" else "Bienvenido a NOXTIUM.", "success")
    return redirect(url_for("portal.admin_dashboard" if user.role == "admin" else "portal.dashboard"))


@portal_bp.get("/logout")
def logout():
    session.clear(); flash("Sesión cerrada.", "success"); return redirect(url_for("inicio"))


@portal_bp.get("/dashboard")
@login_required
def dashboard():
    user = current_user()
    if user.role == "admin": return redirect(url_for("portal.admin_dashboard"))
    seed_catalog()
    subscription = active_subscription(user.company_id)
    pending = pending_subscription(user.company_id)
    whatsapp = WhatsAppConnection.query.filter_by(company_id=user.company_id, status="active").first()
    agent = AgentConfiguration.query.filter_by(company_id=user.company_id).first()
    recent_messages = (WhatsAppMessage.query.filter_by(company_id=user.company_id)
                       .order_by(WhatsAppMessage.created_at.desc()).limit(20).all())
    crm_counts = {status: CRMContact.query.filter_by(company_id=user.company_id, status=status).count()
                  for status in ("NEW", "OPEN", "WON", "LOST")}
    services = Service.query.filter_by(active=True).order_by(Service.id).all()
    token_limit = (subscription.token_limit or subscription.plan.included_tokens or 0) if subscription else 0
    tokens_used = subscription.tokens_used if subscription else 0
    tokens_remaining = max(0, token_limit - tokens_used)
    consultations = ConsultationRequest.query.filter_by(company_id=user.company_id).order_by(ConsultationRequest.created_at.desc()).all()
    external_subscriptions = (Subscription.query.join(ServicePlan).join(Service)
        .filter(Subscription.company_id == user.company_id, Service.slug != "crm-chatbot")
        .order_by(Subscription.created_at.desc()).all())
    return render_template("dashboard.html", user=user, company=user.company, subscription=subscription,
        pending=pending, whatsapp=whatsapp, agent=agent, recent_messages=recent_messages,
        crm_counts=crm_counts, services=services, consultations=consultations,
        external_subscriptions=external_subscriptions, token_limit=token_limit,
        tokens_used=tokens_used, tokens_remaining=tokens_remaining)


@portal_bp.get("/servicios/<slug>")
@login_required
def service_detail(slug):
    user = current_user()
    if user.role == "admin": return redirect(url_for("portal.admin_dashboard"))
    seed_catalog()
    service = Service.query.filter_by(slug=slug, active=True).first_or_404()
    if service.slug == "tarjetas-lealtad":
        return redirect(url_for("loyalty.dashboard"))
    if service.slug == "integracion-modulos":
        return render_template("service_detail.html", service=service, plans=[], user=user,
            service_subscription=None, active_plan_ids=[], pending_plan_ids=[])
    if service.slug == "inventario" and not ServicePlan.query.filter_by(service_id=service.id, active=True).first():
        return render_template("service_detail.html", service=service, plans=[], user=user,
            service_subscription=None, active_plan_ids=[], pending_plan_ids=[])
    plans = ServicePlan.query.filter_by(service_id=service.id, active=True).order_by(ServicePlan.price).all()
    subs = Subscription.query.filter_by(company_id=user.company_id).all()
    active_plan_ids = [sub.service_plan_id for sub in subs if sub.status == "ACTIVE" and (sub.expires_at is None or sub.expires_at > utcnow())]
    pending_plan_ids = [sub.service_plan_id for sub in subs if sub.status == "PENDING_PAYMENT"]
    service_subscription = active_subscription(user.company_id, service.slug)
    return render_template("service_detail.html", service=service, plans=plans, user=user,
        service_subscription=service_subscription, active_plan_ids=active_plan_ids, pending_plan_ids=pending_plan_ids)


@portal_bp.post("/servicios/<slug>/contratar")
@login_required
def contract_service(slug):
    user = current_user()
    if user.role == "admin": return redirect(url_for("portal.admin_dashboard"))
    seed_catalog()
    service = Service.query.filter_by(slug=slug, active=True).first_or_404()
    if service.slug == "tarjetas-lealtad":
        return redirect(url_for("loyalty.pricing"))
    if service.slug == "integracion-modulos":
        return redirect(url_for("portal.request_consultation", producto=service.slug))
    plan_id_raw = (request.form.get("plan_id") or "").strip()
    try:
        plan_id = int(plan_id_raw)
    except (TypeError, ValueError):
        plan_id = None
    plan = (
        ServicePlan.query.filter_by(id=plan_id, service_id=service.id, active=True).first()
        if plan_id is not None
        else None
    )
    if not plan:
        flash("El plan seleccionado no es válido.", "error"); return redirect(url_for("portal.service_detail", slug=slug))
    is_restaurant = service.slug == "imperio-del-barril"
    now = utcnow()
    if is_restaurant:
        complete_plan = plan.name == "Paquete completo"
        active_restaurant = (Subscription.query.join(ServicePlan).join(Service)
            .filter(Subscription.company_id == user.company_id, Subscription.status == "ACTIVE",
                    Service.slug == service.slug,
                    db.or_(Subscription.expires_at.is_(None), Subscription.expires_at > now)).all())
        if any(sub.plan.name == "Paquete completo" for sub in active_restaurant):
            flash("Tu empresa ya tiene el paquete completo de software de restaurante activo.", "success")
            return redirect(url_for("portal.dashboard"))
        if complete_plan and any(sub.plan.name != "Paquete completo" for sub in active_restaurant):
            # The complete package can replace separately contracted modules after approval.
            pass
        elif any(sub.service_plan_id == plan.id for sub in active_restaurant):
            flash("Este módulo ya está activo para tu empresa.", "success")
            return redirect(url_for("portal.dashboard"))
        pending = (Subscription.query.filter_by(company_id=user.company_id, service_plan_id=plan.id,
                    status="PENDING_PAYMENT").order_by(Subscription.created_at.desc()).first())
    else:
        existing = active_subscription(user.company_id, service.slug)
        if existing and existing.plan.id == plan.id:
            flash("Ya tienes este plan activo.", "success"); return redirect(url_for("portal.dashboard"))
        pending = pending_subscription(user.company_id, service.slug)
    if pending: return redirect(url_for("portal.payment", subscription_id=pending.id))
    subscription = Subscription(company_id=user.company_id, service_plan_id=plan.id, status="PENDING_PAYMENT")
    db.session.add(subscription); db.session.flush()
    db.session.add(Payment(subscription_id=subscription.id, amount=plan.price, status="PENDING", provider="manual"))
    db.session.commit()
    return redirect(url_for("portal.payment", subscription_id=subscription.id))


@portal_bp.get("/pago/<int:subscription_id>")
@login_required
def payment(subscription_id):
    user = current_user()
    if user.role == "admin": return redirect(url_for("portal.admin_dashboard"))
    subscription = db.session.get(Subscription, subscription_id)
    if not subscription or subscription.company_id != user.company_id: abort(404)
    payment = Payment.query.filter_by(subscription_id=subscription.id).order_by(Payment.created_at.desc()).first()
    return render_template("payment.html", subscription=subscription, payment=payment, user=user,
        nequi_phone=current_app.config.get("NEQUI_PHONE", ""),
        nequi_account_name=current_app.config.get("NEQUI_ACCOUNT_NAME", "NOXTIUM"),
        nequi_qr_url=current_app.config.get("NEQUI_QR_URL", "/static/uploads/nequi-qr.png"))


@portal_bp.post("/pago/<int:subscription_id>/comprobante")
@login_required
def upload_receipt(subscription_id):
    user = current_user()
    if user.role == "admin": return redirect(url_for("portal.admin_dashboard"))
    subscription = db.session.get(Subscription, subscription_id)
    if not subscription or subscription.company_id != user.company_id: abort(404)
    payment = Payment.query.filter_by(subscription_id=subscription.id).order_by(Payment.created_at.desc()).first()
    receipt = request.files.get("receipt")
    if not payment or not receipt or not receipt.filename:
        flash("Selecciona el comprobante antes de enviarlo.", "error"); return redirect(url_for("portal.payment", subscription_id=subscription.id))
    safe_name = secure_filename(receipt.filename)
    extension = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if extension not in ALLOWED_RECEIPT_EXTENSIONS:
        flash("Formato no permitido. Usa PNG, JPG, JPEG o PDF.", "error"); return redirect(url_for("portal.payment", subscription_id=subscription.id))
    folder = Path(current_app.config["RECEIPTS_UPLOAD_FOLDER"]); folder.mkdir(parents=True, exist_ok=True)
    unique_name = f"{subscription.id}_{uuid4().hex}_{safe_name}"
    receipt.save(folder / unique_name)
    payment.receipt_filename = unique_name
    payment.provider = "manual"
    payment.status = "UNDER_REVIEW"
    db.session.commit()
    flash("Comprobante enviado. El administrador revisará el pago antes de activar el servicio.", "success")
    return redirect(url_for("portal.dashboard"))


@portal_bp.get("/integracion-modulos")
@login_required
def request_consultation():
    user = current_user()
    if user.role == "admin": return redirect(url_for("portal.admin_dashboard"))
    selected_product = (request.args.get("producto") or "").strip()
    return render_template("consultation.html", user=user, selected_product=selected_product)


@portal_bp.post("/integracion-modulos")
@login_required
def submit_consultation():
    user = current_user()
    if user.role == "admin": return redirect(url_for("portal.admin_dashboard"))
    method = request.form.get("contact_method", "email").strip().lower()
    contact = request.form.get("contact_value", "").strip()
    if method not in {"whatsapp", "email"} or not contact:
        flash("Selecciona WhatsApp o correo e indica el dato de contacto.", "error")
        return redirect(url_for("portal.request_consultation"))
    modules = request.form.getlist("modules")
    selected_product = (request.form.get("selected_product") or "").strip()
    if selected_product in {"inventario", "imperio-del-barril", "integracion-modulos"}:
        product_names = {"inventario": "NOXTIUM Inventario", "imperio-del-barril": "Software de restaurante", "integracion-modulos": "Desarrollo de software a la medida"}
        product_label = product_names[selected_product]
        if product_label not in modules:
            modules.insert(0, product_label)
    consultation = ConsultationRequest(company_id=user.company_id, user_id=user.id, contact_method=method,
        contact_value=contact, preferred_date=request.form.get("preferred_date", "").strip() or None,
        preferred_time=request.form.get("preferred_time", "").strip() or None, modules=modules,
        business_description=request.form.get("business_description", "").strip(), status="PENDING")
    db.session.add(consultation); db.session.commit()
    flash("¡Preconsulta gratuita solicitada! NOXTIUM coordinará contigo la reunión por el medio elegido.", "success")
    return redirect(url_for("portal.dashboard"))


@portal_bp.get("/admin/comprobantes/<int:payment_id>")
@login_required
@admin_required
def admin_receipt(payment_id):
    from flask import send_from_directory
    payment = db.session.get(Payment, payment_id)
    if not payment or not payment.receipt_filename:
        abort(404)
    return send_from_directory(current_app.config["RECEIPTS_UPLOAD_FOLDER"], payment.receipt_filename, as_attachment=False)


@portal_bp.get("/admin/empresas")
@login_required
@admin_required
def admin_companies():
    seed_catalog()
    _expire_overdue_subscriptions()
    now = utcnow()
    companies = Company.query.order_by(Company.created_at.desc()).all()
    rows = []
    for company in companies:
        active = active_subscription(company.id)
        latest = Subscription.query.filter_by(company_id=company.id).order_by(Subscription.created_at.desc()).first()
        last_payment = (Payment.query.join(Subscription).filter(Subscription.company_id == company.id)
                        .order_by(Payment.created_at.desc()).first())
        days_left = max(0, (active.expires_at - now).days) if active and active.expires_at else None
        rows.append({"company": company, "active": active, "latest": latest,
                     "last_payment": last_payment, "days_left": days_left,
                     "expiring_soon": bool(active and days_left is not None and days_left <= 7)})
    return render_template("admin_companies.html", rows=rows, user=current_user())


@portal_bp.post("/admin/empresas/<int:company_id>/suscripciones/<int:subscription_id>/cancelar")
@login_required
@admin_required
def cancel_company_subscription(company_id, subscription_id):
    subscription = db.session.get(Subscription, subscription_id)
    if not subscription or subscription.company_id != company_id:
        abort(404)
    if subscription.status not in {"ACTIVE", "PENDING_PAYMENT"}:
        flash("Esta suscripción ya no está activa ni pendiente.", "error")
        return redirect(url_for("portal.admin_companies"))
    subscription.status = "CANCELLED"
    is_crm = subscription.plan.service.slug == "crm-chatbot"
    if is_crm:
        agent = AgentConfiguration.query.filter_by(company_id=company_id).first()
        if agent:
            agent.status = "PAUSED"
            agent.last_error = "Suscripción cancelada por administración."
    db.session.commit()
    flash(f"Suscripción cancelada para {subscription.company.name}.", "success")
    return redirect(url_for("portal.admin_companies"))


@portal_bp.get("/admin/dashboard")
@login_required
@admin_required
def admin_dashboard():
    pending_payments = (Payment.query.join(Subscription).join(Company).join(ServicePlan, Subscription.service_plan_id == ServicePlan.id)
        .filter(Payment.status.in_(["PENDING", "UNDER_REVIEW"]), Payment.receipt_filename.isnot(None))
        .order_by(Payment.created_at.asc()).all())
    consultations = ConsultationRequest.query.order_by(ConsultationRequest.created_at.desc()).all()
    public_leads = LeadInquiry.query.order_by(LeadInquiry.created_at.desc()).limit(100).all()
    external_setup = (Subscription.query.join(ServicePlan).join(Service)
        .filter(Subscription.status == "ACTIVE", Service.slug != "crm-chatbot",
                Subscription.provisioning_status != "READY")
        .order_by(Subscription.created_at.asc()).all())
    external_ready = (Subscription.query.join(ServicePlan).join(Service)
        .filter(Subscription.status == "ACTIVE", Service.slug != "crm-chatbot",
                Subscription.provisioning_status == "READY")
        .order_by(Subscription.created_at.desc()).limit(50).all())
    return render_template("admin_dashboard.html", user=current_user(), pending_payments=pending_payments,
        consultations=consultations, external_setup=external_setup, external_ready=external_ready,
        public_leads=public_leads)


@portal_bp.post("/admin/pagos/<int:payment_id>/aprobar")
@login_required
@admin_required
def approve_payment(payment_id):
    payment = db.session.get(Payment, payment_id)
    if not payment or not payment.receipt_filename:
        flash("No se puede aprobar: no hay comprobante adjunto.", "error"); return redirect(url_for("portal.admin_dashboard"))
    target = payment.subscription
    if target.status == "CANCELLED":
        flash("Esta compra fue cancelada previamente y no se puede activar. Revisa el caso antes de aprobar el pago.", "error")
        return redirect(url_for("portal.admin_dashboard"))
    now = utcnow()
    target_service_slug = target.plan.service.slug
    if target_service_slug == "imperio-del-barril" and target.plan.name != "Paquete completo":
        active_complete = (Subscription.query.join(ServicePlan).join(Service)
            .filter(Subscription.company_id == target.company_id, Subscription.status == "ACTIVE",
                    Service.slug == target_service_slug, ServicePlan.name == "Paquete completo",
                    db.or_(Subscription.expires_at.is_(None), Subscription.expires_at > now)).first())
        if active_complete:
            flash("La empresa ya tiene el paquete completo activo. No apruebes este módulo por separado; rechaza/cancela esta solicitud y revisa si corresponde una devolución.", "error")
            return redirect(url_for("portal.admin_dashboard"))
    previous_active = (Subscription.query.join(ServicePlan).join(Service)
        .filter(Subscription.company_id == target.company_id,
                Subscription.status == "ACTIVE", Service.slug == target_service_slug,
                Subscription.id != target.id).all())
    if target_service_slug == "imperio-del-barril":
        # A module purchase preserves every other active module. The complete package replaces them all.
        if target.plan.name == "Paquete completo":
            for previous in previous_active:
                previous.status = "CANCELLED"
        else:
            for previous in previous_active:
                if previous.service_plan_id == target.service_plan_id or previous.plan.name == "Paquete completo":
                    previous.status = "CANCELLED"
    else:
        # CRM upgrades renew the CRM only; purchases of another product remain independent.
        for previous in previous_active:
            previous.status = "CANCELLED"
    payment.status = "PAID"
    payment.paid_at = now
    target.status = "ACTIVE"
    target.starts_at = now
    duration = _plan_duration_days(target.plan)
    target.expires_at = now + timedelta(days=duration) if duration is not None else None
    if target_service_slug == "crm-chatbot":
        target.provisioning_status = "NOT_REQUIRED"
        target.token_limit = int(target.plan.included_tokens or 0)
        target.tokens_used = 0
    else:
        target.provisioning_status = "PENDING_SETUP"
        target.external_access_url = None
    db.session.commit()
    if target.plan.service.slug == "crm-chatbot":
        flash(f"Pago verificado. Se activó el CRM con {target.token_limit:,}".replace(",", ".") + f" tokens incluidos para n8n para {target.company.name}.", "success")
    else:
        flash(f"Pago verificado. Registra la empresa en {target.plan.service.name} ({target.plan.name}) y luego guarda su enlace de acceso.", "success")
    return redirect(url_for("portal.admin_dashboard"))


@portal_bp.post("/admin/suscripciones/<int:subscription_id>/entregar-acceso")
@login_required
@admin_required
def deliver_external_access(subscription_id):
    subscription = db.session.get(Subscription, subscription_id)
    if not subscription or subscription.status != "ACTIVE":
        abort(404)
    if subscription.plan.service.slug == "crm-chatbot":
        abort(404)
    access_url = (request.form.get("external_access_url") or "").strip()
    if not access_url.startswith("https://"):
        flash("Por seguridad, el enlace de acceso debe utilizar HTTPS (https://).", "error")
        return redirect(url_for("portal.admin_dashboard"))
    subscription.external_access_url = access_url
    subscription.provisioning_status = "READY"
    db.session.commit()
    flash(f"Enlace de acceso guardado para {subscription.company.name}. El cliente lo verá en su panel de NOXTIUM.", "success")
    return redirect(url_for("portal.admin_dashboard"))


@portal_bp.post("/admin/pagos/<int:payment_id>/rechazar")
@login_required
@admin_required
def reject_payment(payment_id):
    payment = db.session.get(Payment, payment_id)
    if payment:
        payment.status = "REJECTED"
        target = payment.subscription
        full_package_active = False
        if target.plan.service.slug == "imperio-del-barril" and target.plan.name != "Paquete completo":
            full_package_active = (Subscription.query.join(ServicePlan).join(Service)
                .filter(Subscription.company_id == target.company_id, Subscription.status == "ACTIVE",
                        Service.slug == "imperio-del-barril", ServicePlan.name == "Paquete completo",
                        db.or_(Subscription.expires_at.is_(None), Subscription.expires_at > utcnow())).first()) is not None
        # Keep pending so a corrected receipt can be sent, unless the complete package already replaced it.
        target.status = "CANCELLED" if full_package_active else "PENDING_PAYMENT"
        db.session.commit()
    flash("Comprobante rechazado. " + ("La solicitud del módulo se cerró porque la empresa ya tiene paquete completo activo; revisa una posible devolución." if payment and full_package_active else "El cliente puede enviar otro."), "success")
    return redirect(url_for("portal.admin_dashboard"))


@portal_bp.post("/admin/ideas/<int:lead_id>/estado")
@login_required
@admin_required
def update_public_lead(lead_id):
    item = db.session.get(LeadInquiry, lead_id)
    status = (request.form.get("status") or "NEW").strip().upper()
    if item and status in {"NEW", "CONTACTED", "EVALUATING", "CLOSED"}:
        item.status = status
        db.session.commit()
        flash("Estado de la idea actualizado.", "success")
    return redirect(url_for("portal.admin_dashboard"))


@portal_bp.post("/admin/consultas/<int:consultation_id>/estado")
@login_required
@admin_required
def update_consultation(consultation_id):
    item = db.session.get(ConsultationRequest, consultation_id)
    status = request.form.get("status", "PENDING")
    if item and status in {"PENDING", "CONTACTED", "SCHEDULED", "COMPLETED", "CANCELLED"}:
        previous_status = item.status
        previous_link = item.meeting_url
        item.status = status
        item.admin_notes = request.form.get("admin_notes", "").strip() or None
        item.meeting_url = request.form.get("meeting_url", "").strip() or None
        db.session.commit()
        # Optional delivery: n8n can send the meeting link to the client's chosen channel.
        if status == "SCHEDULED" and item.meeting_url and (previous_status != "SCHEDULED" or previous_link != item.meeting_url):
            webhook_url = current_app.config.get("N8N_CONSULTATION_WEBHOOK_URL")
            if webhook_url:
                try:
                    import requests
                    headers = {"Content-Type": "application/json", "X-Noxtium-Event": "consultation.scheduled"}
                    secret = current_app.config.get("N8N_WEBHOOK_SECRET")
                    if secret:
                        headers["Authorization"] = f"Bearer {secret}"
                    response = requests.post(webhook_url, json={
                        "event": "consultation.scheduled",
                        "consultation_id": item.id,
                        "company": item.company.name,
                        "contact_name": item.user.full_name,
                        "contact_method": item.contact_method,
                        "contact_value": item.contact_value,
                        "meeting_url": item.meeting_url,
                        "preferred_date": item.preferred_date,
                        "preferred_time": item.preferred_time,
                        "modules": item.modules,
                    }, headers=headers, timeout=10)
                    response.raise_for_status()
                    flash("Solicitud agendada y enviada al flujo de notificación de n8n.", "success")
                except Exception:
                    current_app.logger.exception("No se pudo notificar la cita a n8n.")
                    flash("La solicitud quedó guardada, pero n8n no confirmó el envío. Revisa el webhook.", "error")
            else:
                flash("Reunión marcada como agendada. Configura N8N_CONSULTATION_WEBHOOK_URL para enviar automáticamente el enlace.", "success")
        else:
            flash("Solicitud de preconsulta actualizada.", "success")
    return redirect(url_for("portal.admin_dashboard"))


@portal_bp.post("/pago/<int:subscription_id>/confirmar-demo")
@login_required
def confirm_demo_payment(subscription_id):
    # Se conserva por compatibilidad, pero la activación demo se deshabilita para evitar saltarse la revisión.
    flash("La activación de prueba está deshabilitada. Envía el comprobante para revisión administrativa.", "error")
    return redirect(url_for("portal.payment", subscription_id=subscription_id))


@portal_bp.route("/crm/agente", methods=["GET", "POST"])
@login_required
def agent_setup():
    user = current_user()
    if user.role == "admin":
        return redirect(url_for("portal.admin_dashboard"))
    if not active_subscription(user.company_id):
        return render_template("service_locked.html"), 403
    agent = AgentConfiguration.query.filter_by(company_id=user.company_id).first()
    if request.method == "POST":
        restaurant_name = request.form.get("restaurant_name", "").strip()
        if not restaurant_name:
            flash("El nombre del restaurante es obligatorio.", "error")
            return redirect(url_for("portal.agent_setup"))
        names = request.form.getlist("item_name[]")
        prices = request.form.getlist("item_price[]")
        descriptions = request.form.getlist("item_description[]")
        items = []
        for idx, name in enumerate(names[:100]):
            name = name.strip()[:120]
            price_raw = prices[idx].strip() if idx < len(prices) else ""
            description = descriptions[idx].strip()[:500] if idx < len(descriptions) else ""
            if not name and not price_raw and not description:
                continue
            try:
                price = int(price_raw.replace(".", "").replace(",", ""))
            except (ValueError, TypeError):
                flash(f"El precio de '{name or 'un producto'}' debe ser un número entero en COP.", "error")
                return redirect(url_for("portal.agent_setup"))
            if not name or price < 0:
                flash("Cada producto debe tener nombre y precio válido.", "error")
                return redirect(url_for("portal.agent_setup"))
            items.append({"name": name, "price_cop": price, "description": description, "available": True})
        if not agent:
            agent = AgentConfiguration(company_id=user.company_id, restaurant_name=restaurant_name)
            db.session.add(agent)
        agent.restaurant_name = restaurant_name
        agent.business_type = request.form.get("business_type", "Restaurante")[:80]
        agent.address = request.form.get("address", "").strip()[:255] or None
        agent.opening_hours = request.form.get("opening_hours", "").strip() or None
        agent.delivery_zones = request.form.get("delivery_zones", "").strip() or None
        agent.menu_items = items
        agent.sales_tone = request.form.get("sales_tone", "amable")[:40]
        agent.welcome_message = request.form.get("welcome_message", "").strip()[:500] or None
        agent.special_rules = request.form.get("special_rules", "").strip() or None
        agent.status = "SETUP"
        agent.last_error = None
        db.session.commit()
        flash("Configuración guardada. Tu panel CRM ya está listo para revisar la actividad y continuar las pruebas.", "success")
        return redirect(url_for("portal.dashboard"))
    if request.args.get("connected") == "1":
        flash("WhatsApp quedó vinculado. Ahora configura los datos del restaurante y el menú.", "success")
    whatsapp = WhatsAppConnection.query.filter_by(company_id=user.company_id, status="active").first()
    messages = WhatsAppMessage.query.filter_by(company_id=user.company_id).order_by(WhatsAppMessage.created_at.desc()).limit(20).all()
    return render_template("agent_setup.html", user=user, company_name=user.company.name, agent=agent, whatsapp=whatsapp, messages=messages)


@portal_bp.route("/crm/contactos")
@login_required
def crm_contacts():
    user = current_user()
    if user.role == "admin":
        return redirect(url_for("portal.admin_dashboard"))
    if not active_subscription(user.company_id):
        return render_template("service_locked.html"), 403
    query = request.args.get("q", "").strip()
    contacts_query = CRMContact.query.filter_by(company_id=user.company_id)
    if query:
        contacts_query = contacts_query.filter(db.or_(CRMContact.phone.ilike(f"%{query}%"), CRMContact.contact_name.ilike(f"%{query}%")))
    contacts = contacts_query.order_by(CRMContact.last_message_at.desc()).limit(200).all()
    counts = {status: CRMContact.query.filter_by(company_id=user.company_id, status=status).count() for status in ("NEW", "OPEN", "WON", "LOST")}
    return render_template("crm_contacts.html", user=user, contacts=contacts, counts=counts, query=query)


@portal_bp.post("/crm/contactos/<int:contact_id>")
@login_required
def update_crm_contact(contact_id):
    user = current_user()
    if user.role == "admin":
        abort(403)
    contact = CRMContact.query.filter_by(id=contact_id, company_id=user.company_id).first_or_404()
    status = request.form.get("status", "NEW")
    if status not in {"NEW", "OPEN", "WON", "LOST"}:
        abort(400)
    contact.status = status
    contact.tags = [tag.strip()[:40] for tag in request.form.get("tags", "").split(",") if tag.strip()][:20]
    contact.notes = request.form.get("notes", "").strip()[:4000] or None
    db.session.commit()
    flash("Contacto actualizado.", "success")
    return redirect(url_for("portal.crm_contacts"))


@portal_bp.post("/crm/agente/activar")
@login_required
def activate_agent():
    user = current_user()
    if user.role == "admin":
        abort(403)
    agent = AgentConfiguration.query.filter_by(company_id=user.company_id).first()
    connection = WhatsAppConnection.query.filter_by(company_id=user.company_id, status="active").first()
    if not active_subscription(user.company_id) or not agent or not agent.menu_items or not connection:
        flash("Para activar: necesitas una suscripción aprobada, catálogo guardado y WhatsApp conectado mediante la API oficial de Meta.", "error")
        return redirect(url_for("portal.agent_setup"))
    crm_subscription = active_subscription(user.company_id)
    provision_url = current_app.config.get("N8N_PROVISION_WEBHOOK_URL", "").strip()
    if not provision_url:
        agent.status = "TESTING"
        agent.last_error = "Configuración lista. Falta configurar N8N_PROVISION_WEBHOOK_URL para confirmar despliegue y pruebas."
        db.session.commit()
        flash("Configuración lista para pruebas, pero n8n aún no confirmó la activación. El agente no se activó.", "error")
        return redirect(url_for("portal.agent_setup"))
    payload = {"event": "agent.activate", "company_id": user.company_id,
        "subscription": {"plan": crm_subscription.plan.name, "token_limit": int(crm_subscription.token_limit or crm_subscription.plan.included_tokens or 0), "tokens_used": int(crm_subscription.tokens_used or 0)},
        "connection": {"phone_number": connection.display_phone_number, "waba_id": connection.waba_id, "phone_number_id": connection.phone_number_id, "provider": "meta_cloud_api"},
        "agent": {"restaurant_name": agent.restaurant_name, "business_type": agent.business_type,
            "address": agent.address, "opening_hours": agent.opening_hours, "delivery_zones": agent.delivery_zones,
            "menu_items": agent.menu_items, "sales_tone": agent.sales_tone,
            "special_rules": agent.special_rules, "welcome_message": agent.welcome_message}}
    try:
        import requests
        headers = {"Content-Type": "application/json"}
        secret = current_app.config.get("N8N_WEBHOOK_SECRET", "")
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        response = requests.post(provision_url, json=payload, headers=headers, timeout=12)
        response.raise_for_status()
        result = response.json()
        if result.get("ready") is not True:
            raise RuntimeError("n8n no confirmó ready=true.")
        agent.status = "ACTIVE"
        agent.n8n_workflow_id = str(result.get("workflow_id", ""))[:120] or None
        agent.last_error = None
        agent.last_tested_at = utcnow()
        db.session.commit()
        flash("n8n confirmó que el agente está listo. Activación completada.", "success")
    except Exception:
        db.session.rollback()
        agent = AgentConfiguration.query.filter_by(company_id=user.company_id).first()
        if agent:
            agent.status = "TESTING"
            agent.last_error = "n8n no confirmó que el flujo esté listo. Revisa el webhook y las pruebas."
            db.session.commit()
        flash("No se activó el agente: n8n no confirmó la preparación real del flujo.", "error")
    return redirect(url_for("portal.agent_setup"))


@portal_bp.post("/crm/agente/pausar")
@login_required
def pause_agent():
    user = current_user()
    if user.role == "admin":
        abort(403)
    agent = AgentConfiguration.query.filter_by(company_id=user.company_id).first()
    if agent:
        agent.status = "PAUSED"
        db.session.commit()
    flash("Agente pausado. Los mensajes no se enviarán a n8n para respuestas automáticas.", "success")
    return redirect(url_for("portal.agent_setup"))
