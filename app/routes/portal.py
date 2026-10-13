from datetime import timedelta
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for, abort
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from app.database import db
from app.models import (Company, Payment, Service, ServicePlan, Subscription, User,
                        WhatsAppConnection, ConsultationRequest, utcnow)

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
        db.session.add(ServicePlan(service_id=service.id, name="Profesional", price=120000,
            billing_period="monthly", features=["CRM de clientes", "WhatsApp Business", "Bandeja de conversaciones",
            "Chatbot y respuestas automáticas", "Automatizaciones con n8n", "Etiquetas y respuestas rápidas"], active=True))
    extras = [
        ("Inventario", "inventario", "📦", "Controla existencias, movimientos y productos."),
        ("Caja y ventas", "caja-ventas", "💰", "Digitaliza caja, ventas y operación diaria."),
        ("Reportes", "reportes", "📊", "Convierte los datos de tu negocio en información útil."),
        ("Integración de módulos", "integracion-modulos", "🧩", "Preconsulta gratuita para diseñar un software adaptado a tu tienda o empresa.")]
    for name, slug, icon, description in extras:
        existing = Service.query.filter_by(slug=slug).first()
        if not existing:
            db.session.add(Service(name=name, slug=slug, icon=icon, description=description, active=True if slug == "integracion-modulos" else False))
        elif slug == "integracion-modulos":
            existing.active = True
    db.session.commit()


def active_subscription(company_id):
    return (Subscription.query.join(ServicePlan, Subscription.service_plan_id == ServicePlan.id)
        .join(Service, ServicePlan.service_id == Service.id)
        .filter(Subscription.company_id == company_id, Subscription.status == "ACTIVE", Service.slug == "crm-chatbot")
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
    whatsapp = WhatsAppConnection.query.filter_by(company_id=user.company_id, status="active").first()
    services = Service.query.filter_by(active=True).order_by(Service.id).all()
    consultations = ConsultationRequest.query.filter_by(company_id=user.company_id).order_by(ConsultationRequest.created_at.desc()).all()
    return render_template("dashboard.html", user=user, company=user.company, subscription=subscription,
        pending=pending, whatsapp=whatsapp, services=services, consultations=consultations)


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
    plan = ServicePlan.query.filter_by(id=request.form.get("plan_id"), service_id=service.id, active=True).first()
    if not plan:
        flash("El plan seleccionado no es válido.", "error"); return redirect(url_for("portal.service_detail", slug=slug))
    existing = active_subscription(user.company_id)
    if existing and existing.plan.service_id == service.id:
        flash("Ya tienes este servicio activo.", "success"); return redirect(url_for("portal.dashboard"))
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
    payment.status = "PAID"; payment.paid_at = utcnow(); payment.subscription.status = "ACTIVE"
    payment.subscription.starts_at = utcnow(); payment.subscription.expires_at = utcnow() + timedelta(days=30)
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
