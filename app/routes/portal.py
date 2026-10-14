from datetime import timedelta
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for, abort
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from app.database import db
from app.models import (Company, Payment, Service, ServicePlan, Subscription, User,
                        WhatsAppConnection, ConsultationRequest, AgentConfiguration, CRMContact, QRWhatsAppConnection, QRWhatsAppMessage, utcnow)

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
    service = Service.query.filter_by(slug="crm-chatbot").first()
    if not service:
        service = Service(name="CRM + Chatbot", slug="crm-chatbot", icon="🤖",
            description="Gestiona clientes, conversaciones de WhatsApp y automatizaciones desde un solo lugar.", active=True)
        db.session.add(service)
        db.session.flush()
    features = ["CRM de clientes", "WhatsApp por QR", "Bandeja de conversaciones",
                "Chatbot y respuestas automáticas", "Automatizaciones con n8n", "Etiquetas y seguimiento comercial"]
    plans = [
        ("Profesional mensual", 120000, "monthly"),
        ("Trimestral", 330000, "quarterly"),
        ("Anual", 1200000, "annual"),
    ]
    for name, price, period in plans:
        existing = ServicePlan.query.filter_by(service_id=service.id, billing_period=period).first()
        if not existing:
            db.session.add(ServicePlan(service_id=service.id, name=name, price=price,
                billing_period=period, features=features, active=True))
        elif not existing.features:
            existing.features = features
    extras = [
        ("Inventario", "inventario", "📦", "Controla existencias, movimientos y productos."),
        ("Caja y ventas", "caja-ventas", "💰", "Digitaliza caja, ventas y operación diaria."),
        ("Reportes", "reportes", "📊", "Convierte los datos de tu negocio en información útil."),
        ("Integración de módulos", "integracion-modulos", "🧩", "Preconsulta gratuita para diseñar un software adaptado a tu tienda o empresa.")]
    for name, slug, icon, description in extras:
        existing = Service.query.filter_by(slug=slug).first()
        if not existing:
            db.session.add(Service(name=name, slug=slug, icon=icon, description=description, active=(slug == "integracion-modulos")))
        elif slug == "integracion-modulos":
            existing.active = True
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
        agent = AgentConfiguration.query.filter_by(company_id=subscription.company_id).first()
        if agent:
            agent.status = "PAUSED"
            agent.last_error = "La suscripción venció. Renueva el plan para reactivar el servicio."
    if overdue:
        db.session.commit()


def _plan_duration_days(plan):
    period = (plan.billing_period or "monthly").lower()
    return {"monthly": 30, "month": 30, "quarterly": 90, "3_months": 90,
            "annual": 365, "yearly": 365, "year": 365}.get(period, 30)


def active_subscription(company_id):
    now = utcnow()
    return (Subscription.query.join(ServicePlan, Subscription.service_plan_id == ServicePlan.id)
        .join(Service, ServicePlan.service_id == Service.id)
        .filter(Subscription.company_id == company_id, Subscription.status == "ACTIVE",
                Service.slug == "crm-chatbot",
                db.or_(Subscription.expires_at.is_(None), Subscription.expires_at > now))
        .order_by(Subscription.created_at.desc()).first())


def pending_subscription(company_id):
    return (Subscription.query.join(ServicePlan).join(Service)
        .filter(Subscription.company_id == company_id, Subscription.status == "PENDING_PAYMENT", Service.slug == "crm-chatbot")
        .order_by(Subscription.created_at.desc()).first())


@portal_bp.get("/registro")
def register():
    if current_user(): return redirect(url_for("portal.dashboard"))
    return render_template("register.html")


@portal_bp.post("/registro")
def register_post():
    if current_user(): return redirect(url_for("portal.dashboard"))
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
    company = Company(name=company_name, email=email, is_active=True)
    db.session.add(company); db.session.flush()
    user = User(company_id=company.id, full_name=name, email=email,
                password_hash=generate_password_hash(password), role="client")
    db.session.add(user); db.session.commit()
    session.clear(); session["user_id"] = user.id; session["company_id"] = company.id
    flash("Cuenta creada. Puedes consultar los servicios y solicitar acceso.", "success")
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
    whatsapp = QRWhatsAppConnection.query.filter_by(company_id=user.company_id, status="connected").first() or WhatsAppConnection.query.filter_by(company_id=user.company_id, status="active").first()
    agent = AgentConfiguration.query.filter_by(company_id=user.company_id).first()
    recent_messages = (QRWhatsAppMessage.query.filter_by(company_id=user.company_id)
                       .order_by(QRWhatsAppMessage.created_at.desc()).limit(20).all())
    crm_counts = {status: CRMContact.query.filter_by(company_id=user.company_id, status=status).count()
                  for status in ("NEW", "OPEN", "WON", "LOST")}
    services = Service.query.filter_by(active=True).order_by(Service.id).all() if not subscription and not pending else []
    consultations = ConsultationRequest.query.filter_by(company_id=user.company_id).order_by(ConsultationRequest.created_at.desc()).all()
    return render_template("dashboard.html", user=user, company=user.company, subscription=subscription,
        pending=pending, whatsapp=whatsapp, agent=agent, recent_messages=recent_messages,
        crm_counts=crm_counts, services=services, consultations=consultations)


@portal_bp.get("/servicios/<slug>")
@login_required
def service_detail(slug):
    user = current_user()
    if user.role == "admin": return redirect(url_for("portal.admin_dashboard"))
    seed_catalog()
    service = Service.query.filter_by(slug=slug, active=True).first_or_404()
    if service.slug == "integracion-modulos":
        return render_template("service_detail.html", service=service, plans=[], user=user)
    plans = ServicePlan.query.filter_by(service_id=service.id, active=True).order_by(ServicePlan.price).all()
    return render_template("service_detail.html", service=service, plans=plans, user=user)


@portal_bp.post("/servicios/<slug>/contratar")
@login_required
def contract_service(slug):
    user = current_user()
    if user.role == "admin": return redirect(url_for("portal.admin_dashboard"))
    seed_catalog()
    service = Service.query.filter_by(slug=slug, active=True).first_or_404()
    if service.slug == "integracion-modulos":
        return redirect(url_for("portal.request_consultation"))
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
    existing = active_subscription(user.company_id)
    if existing and existing.plan.id == plan.id:
        flash("Ya tienes este plan activo.", "success"); return redirect(url_for("portal.dashboard"))
    pending = pending_subscription(user.company_id)
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
    return render_template("consultation.html", user=user)


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
    agent = AgentConfiguration.query.filter_by(company_id=company_id).first()
    if agent:
        agent.status = "PAUSED"
        agent.last_error = "Suscripción cancelada por administración."
    db.session.commit()
    # Best-effort logout from QR service; cancellation is saved even if Node is offline.
    base = current_app.config.get("QR_WHATSAPP_SERVICE_URL", "").rstrip("/")
    secret = current_app.config.get("QR_WHATSAPP_API_SECRET", "")
    if base and secret:
        try:
            import requests
            requests.post(f"{base}/sessions/{company_id}/disconnect",
                          headers={"Authorization": f"Bearer {secret}"}, timeout=3)
        except Exception:
            current_app.logger.warning("Suscripción %s cancelada; no se pudo cerrar la sesión QR en ese momento.", subscription_id)
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
    return render_template("admin_dashboard.html", user=current_user(), pending_payments=pending_payments, consultations=consultations)


@portal_bp.post("/admin/pagos/<int:payment_id>/aprobar")
@login_required
@admin_required
def approve_payment(payment_id):
    payment = db.session.get(Payment, payment_id)
    if not payment or not payment.receipt_filename:
        flash("No se puede aprobar: no hay comprobante adjunto.", "error"); return redirect(url_for("portal.admin_dashboard"))
    now = utcnow()
    target = payment.subscription
    # If this is an upgrade/renewal, replace the prior active subscription for this service.
    for previous in Subscription.query.join(ServicePlan).join(Service).filter(
        Subscription.company_id == target.company_id,
        Subscription.status == "ACTIVE",
        Service.slug == target.plan.service.slug,
        Subscription.id != target.id,
    ).all():
        previous.status = "CANCELLED"
    payment.status = "PAID"
    payment.paid_at = now
    target.status = "ACTIVE"
    target.starts_at = now
    target.expires_at = now + timedelta(days=_plan_duration_days(target.plan))
    db.session.commit()
    flash(f"Pago verificado. Se activó el servicio para {payment.subscription.company.name}.", "success")
    return redirect(url_for("portal.admin_dashboard"))


@portal_bp.post("/admin/pagos/<int:payment_id>/rechazar")
@login_required
@admin_required
def reject_payment(payment_id):
    payment = db.session.get(Payment, payment_id)
    if payment:
        payment.status = "REJECTED"
        # Keep subscription pending so the client can upload a corrected receipt.
        payment.subscription.status = "PENDING_PAYMENT"
        db.session.commit()
    flash("El comprobante fue rechazado. El cliente puede enviar otro.", "success")
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
    whatsapp = QRWhatsAppConnection.query.filter_by(company_id=user.company_id, status="connected").first() or WhatsAppConnection.query.filter_by(company_id=user.company_id, status="active").first()
    messages = QRWhatsAppMessage.query.filter_by(company_id=user.company_id).order_by(QRWhatsAppMessage.created_at.desc()).limit(20).all()
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
    connection = QRWhatsAppConnection.query.filter_by(company_id=user.company_id, status="connected").first()
    if not active_subscription(user.company_id) or not agent or not agent.menu_items or not connection:
        flash("Para activar: necesitas pago aprobado, menú guardado y WhatsApp conectado por QR.", "error")
        return redirect(url_for("portal.agent_setup"))
    provision_url = current_app.config.get("N8N_PROVISION_WEBHOOK_URL", "").strip()
    if not provision_url:
        agent.status = "TESTING"
        agent.last_error = "Configuración lista. Falta configurar N8N_PROVISION_WEBHOOK_URL para confirmar despliegue y pruebas."
        db.session.commit()
        flash("Configuración lista para pruebas, pero n8n aún no confirmó la activación. El agente no se activó.", "error")
        return redirect(url_for("portal.agent_setup"))
    payload = {"event": "agent.activate", "company_id": user.company_id,
        "connection": {"phone_number": connection.phone_number},
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
