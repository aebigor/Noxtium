import re
from datetime import datetime, timezone

import requests
from sqlalchemy.dialects.postgresql import insert as pg_insert
from flask import Blueprint, current_app, jsonify, render_template, request, session, abort

from app.database import db
from app.models import (AgentConfiguration, CRMContact, QRWhatsAppConnection,
                        QRWhatsAppMessage, Service, ServicePlan, Subscription, User)
from app.services.n8n_service import N8NService

qr_whatsapp_bp = Blueprint("qr_whatsapp", __name__)


def _user():
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id else None
    if not user or not user.is_active or user.role == "admin":
        return None
    return user


def _active(user):
    return (Subscription.query.join(ServicePlan, Subscription.service_plan_id == ServicePlan.id)
            .join(Service, ServicePlan.service_id == Service.id)
            .filter(Subscription.company_id == user.company_id,
                    Subscription.status == "ACTIVE", Service.slug == "crm-chatbot",
                    db.or_(Subscription.expires_at.is_(None), Subscription.expires_at > datetime.now(timezone.utc))).first())


def _service_request(method, path, **kwargs):
    base = current_app.config.get("QR_WHATSAPP_SERVICE_URL", "").rstrip("/")
    secret = current_app.config.get("QR_WHATSAPP_API_SECRET", "")
    if not base or not secret:
        raise RuntimeError("Configura QR_WHATSAPP_SERVICE_URL y QR_WHATSAPP_API_SECRET en .env.")
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {secret}"
    response = requests.request(method, base + path, headers=headers, timeout=12, **kwargs)
    try:
        payload = response.json()
    except ValueError:
        payload = {"error": "El servicio QR devolvió una respuesta no válida."}
    if not response.ok:
        raise RuntimeError(payload.get("error", f"Servicio QR respondió HTTP {response.status_code}."))
    return payload


@qr_whatsapp_bp.get("/whatsapp/qr")
def qr_whatsapp_page():
    user = _user()
    if not user:
        return render_template("login.html"), 401
    if not _active(user):
        return render_template("service_locked.html"), 403
    connection = QRWhatsAppConnection.query.filter_by(company_id=user.company_id).first()
    return render_template("whatsapp_qr.html", connection=connection, test_mode=current_app.config.get("QR_WHATSAPP_TEST_MODE", True))


@qr_whatsapp_bp.post("/api/qr-whatsapp/start")
def start_session():
    user = _user()
    if not user:
        return jsonify({"error": "Inicia sesión como cliente."}), 401
    if not _active(user):
        return jsonify({"error": "El servicio debe estar activo y el pago aprobado."}), 403
    try:
        result = _service_request("POST", "/sessions/start", json={"company_id": user.company_id})
        return jsonify(result)
    except Exception as exc:
        current_app.logger.warning("No se pudo iniciar sesión QR para empresa %s: %s", user.company_id, exc)
        return jsonify({"error": str(exc)}), 503


@qr_whatsapp_bp.get("/api/qr-whatsapp/status")
def session_status():
    user = _user()
    if not user:
        return jsonify({"error": "Inicia sesión como cliente."}), 401
    if not _active(user):
        return jsonify({"error": "El servicio debe estar activo."}), 403
    try:
        result = _service_request("GET", f"/sessions/{user.company_id}/status")
        connection = QRWhatsAppConnection.query.filter_by(company_id=user.company_id).first()
        if result.get("status") == "connected":
            if not connection:
                connection = QRWhatsAppConnection(company_id=user.company_id)
                db.session.add(connection)
            connection.status = "connected"
            connection.phone_number = result.get("phone_number") or connection.phone_number
            connection.verified_name = result.get("verified_name") or connection.verified_name
            connection.linked_at = connection.linked_at or datetime.now(timezone.utc)
            connection.last_error = None
            db.session.commit()
        elif connection and result.get("status") in {"disconnected", "logged_out", "error"}:
            connection.status = result.get("status")
            connection.last_error = result.get("last_error")
            db.session.commit()
        return jsonify(result)
    except Exception as exc:
        current_app.logger.warning("No se pudo consultar sesión QR empresa %s: %s", user.company_id, exc)
        return jsonify({"error": str(exc), "status": "unavailable"}), 503


@qr_whatsapp_bp.post("/api/qr-whatsapp/disconnect")
def disconnect_session():
    user = _user()
    if not user:
        return jsonify({"error": "Inicia sesión como cliente."}), 401
    try:
        result = _service_request("POST", f"/sessions/{user.company_id}/disconnect", json={})
        connection = QRWhatsAppConnection.query.filter_by(company_id=user.company_id).first()
        if connection:
            connection.status = "disconnected"
            connection.last_error = None
            db.session.commit()
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503


@qr_whatsapp_bp.post("/api/qr-whatsapp/test-message")
def send_test_message():
    user = _user()
    if not user:
        return jsonify({"error": "Inicia sesión como cliente."}), 401
    if not current_app.config.get("QR_WHATSAPP_TEST_MODE", True):
        return jsonify({"error": "El modo de prueba está desactivado."}), 403
    if not _active(user):
        return jsonify({"error": "El servicio debe estar activo."}), 403
    data = request.get_json(silent=True) or {}
    to = re.sub(r"\D", "", str(data.get("to", "")))
    text = str(data.get("text", "")).strip()[:1000]
    allowed = current_app.config.get("QR_WHATSAPP_TEST_RECIPIENTS", [])
    allowed_numbers = [re.sub(r"\D", "", n) for n in allowed]
    if not to or not text:
        return jsonify({"error": "Indica el número y el mensaje de prueba."}), 400
    if not allowed_numbers or to not in allowed_numbers:
        return jsonify({"error": "Configura ese número autorizado en QR_WHATSAPP_TEST_RECIPIENTS antes de enviar pruebas."}), 403
    try:
        result = _service_request("POST", f"/sessions/{user.company_id}/send", json={"to": to, "text": text})
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503


@qr_whatsapp_bp.post("/webhooks/qr-whatsapp")
def receive_qr_event():
    secret = current_app.config.get("QR_WHATSAPP_API_SECRET", "")
    received = request.headers.get("X-Noxtium-Secret", "")
    import hmac
    if not secret or not hmac.compare_digest(received, secret):
        return jsonify({"error": "No autorizado."}), 401
    payload = request.get_json(silent=True) or {}
    company_id = payload.get("company_id")
    if not isinstance(company_id, int):
        return jsonify({"error": "company_id inválido."}), 400
    from app.models import Company
    company = db.session.get(Company, company_id)
    if not company:
        return jsonify({"error": "Empresa no encontrada."}), 404
    event = payload.get("event")
    connection = QRWhatsAppConnection.query.filter_by(company_id=company_id).first()
    if not connection:
        connection = QRWhatsAppConnection(company_id=company_id)
        db.session.add(connection)
        db.session.flush()
    if event == "connection.update":
        status = payload.get("status", "disconnected")
        connection.status = status if status in {"connecting", "connected", "disconnected", "logged_out", "error"} else "disconnected"
        connection.phone_number = payload.get("phone_number") or connection.phone_number
        connection.verified_name = payload.get("verified_name") or connection.verified_name
        connection.last_error = payload.get("last_error")
        if connection.status == "connected":
            connection.linked_at = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({"ok": True})
    if event != "whatsapp.message":
        return jsonify({"ok": True, "ignored": True})
    active = (Subscription.query.join(ServicePlan, Subscription.service_plan_id == ServicePlan.id)
              .join(Service, ServicePlan.service_id == Service.id)
              .filter(Subscription.company_id == company_id, Subscription.status == "ACTIVE",
                      Service.slug == "crm-chatbot",
                      db.or_(Subscription.expires_at.is_(None), Subscription.expires_at > datetime.now(timezone.utc)))
              .first())
    if not active:
        return jsonify({"ok": True, "subscription_inactive": True})
    message_id = str(payload.get("message_id", ""))
    if not message_id:
        return jsonify({"error": "message_id requerido."}), 400
    from_number = str(payload.get("from_number", "")).strip()[:50]
    if not from_number:
        return jsonify({"error": "from_number requerido."}), 400
    text = payload.get("text")
    contact_name = str(payload.get("contact_name") or "").strip()[:150] or None
    now = datetime.now(timezone.utc)

    # Idempotencia a nivel de base de datos: dos callbacks simultáneos o un
    # reintento del servicio no deben insertar el mismo mensaje dos veces.
    message_insert = pg_insert(QRWhatsAppMessage).values(
        company_id=company_id,
        connection_id=connection.id,
        message_id=message_id,
        from_number=from_number,
        to_number=connection.phone_number,
        message_text=text,
        direction="IN",
        created_at=now,
    ).on_conflict_do_nothing(index_elements=["message_id"]).returning(QRWhatsAppMessage.id)
    inserted_message_id = db.session.execute(message_insert).scalar_one_or_none()
    if inserted_message_id is None:
        db.session.rollback()
        return jsonify({"ok": True, "duplicate": True})

    # Upsert del contacto para respetar uq_crm_contacts_company_phone incluso
    # cuando WhatsApp reintenta eventos concurrentes para el mismo teléfono.
    contact_values = {
        "company_id": company_id,
        "phone": from_number,
        "contact_name": contact_name,
        "status": "NEW",
        "tags": [],
        "last_message_at": now,
        "created_at": now,
        "updated_at": now,
    }
    contact_insert = pg_insert(CRMContact).values(**contact_values)
    contact_update = {"last_message_at": now, "updated_at": now}
    if contact_name:
        contact_update["contact_name"] = contact_name
    db.session.execute(contact_insert.on_conflict_do_update(
        index_elements=["company_id", "phone"],
        set_=contact_update,
    ))
    db.session.commit()
    agent = AgentConfiguration.query.filter_by(company_id=company_id).first()
    test_mode = current_app.config.get("QR_WHATSAPP_TEST_MODE", True)
    if test_mode:
        allowed = [re.sub(r"\D", "", n) for n in current_app.config.get("QR_WHATSAPP_TEST_RECIPIENTS", [])]
        if not allowed or re.sub(r"\D", "", from_number) not in allowed:
            return jsonify({"ok": True, "test_recipient_blocked": True})
    elif not agent or agent.status != "ACTIVE":
        return jsonify({"ok": True, "agent_paused": True})
    try:
        N8NService().send_whatsapp_event({
            "event": "whatsapp.message", "source": "baileys_qr", "test_mode": test_mode,
            "company": {"id": company_id, "name": company.name},
            "whatsapp": {"connection_id": connection.id, "phone_number": connection.phone_number},
            "message": {"id": message_id, "from": from_number, "type": "text", "text": {"body": text or ""}},
            "agent": ({"restaurant_name": agent.restaurant_name, "business_type": agent.business_type,
                       "address": agent.address, "opening_hours": agent.opening_hours,
                       "delivery_zones": agent.delivery_zones, "menu_items": agent.menu_items,
                       "sales_tone": agent.sales_tone, "special_rules": agent.special_rules,
                       "welcome_message": agent.welcome_message, "status": agent.status} if agent else None),
            "idempotency_key": f"qr:{message_id}",
        })
    except Exception:
        current_app.logger.exception("Evento QR guardado, pero no se pudo enviar a n8n (empresa %s).", company_id)
        return jsonify({"ok": True, "n8n": "unavailable"})
    return jsonify({"ok": True})


@qr_whatsapp_bp.post("/webhooks/qr-whatsapp/send")
def send_from_n8n():
    secret = current_app.config.get("N8N_WEBHOOK_SECRET", "")
    received = request.headers.get("Authorization", "")
    import hmac
    if not secret or not hmac.compare_digest(received, f"Bearer {secret}"):
        return jsonify({"error": "No autorizado."}), 401
    payload = request.get_json(silent=True) or {}
    company_id = payload.get("company_id")
    to = re.sub(r"\D", "", str(payload.get("to", "")))
    text = str(payload.get("text", "")).strip()[:4000]
    if not isinstance(company_id, int) or not to or not text:
        return jsonify({"error": "company_id, to y text son obligatorios."}), 400
    active = (Subscription.query.join(ServicePlan, Subscription.service_plan_id == ServicePlan.id)
              .join(Service, ServicePlan.service_id == Service.id)
              .filter(Subscription.company_id == company_id, Subscription.status == "ACTIVE", Service.slug == "crm-chatbot").first())
    if not active:
        return jsonify({"error": "La suscripción de esa empresa no está activa."}), 403
    connection = QRWhatsAppConnection.query.filter_by(company_id=company_id, status="connected").first()
    if not connection:
        return jsonify({"error": "WhatsApp QR no está conectado para esa empresa."}), 409
    if current_app.config.get("QR_WHATSAPP_TEST_MODE", True):
        allowed = [re.sub(r"\D", "", n) for n in current_app.config.get("QR_WHATSAPP_TEST_RECIPIENTS", [])]
        if not allowed or to not in allowed:
            return jsonify({"error": "El destino no está autorizado para pruebas."}), 403
    else:
        agent = AgentConfiguration.query.filter_by(company_id=company_id, status="ACTIVE").first()
        if not agent:
            return jsonify({"error": "El agente de esa empresa no está activo."}), 403
    try:
        result = _service_request("POST", f"/sessions/{company_id}/send", json={"to": to, "text": text})
        msgid = result.get("message_id") or f"out:{company_id}:{datetime.now(timezone.utc).timestamp()}"
        db.session.add(QRWhatsAppMessage(company_id=company_id, connection_id=connection.id,
                        message_id=msgid, from_number=connection.phone_number, to_number=to,
                        message_text=text, direction="OUT"))
        db.session.commit()
        return jsonify({"ok": True, "result": result})
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("n8n no pudo enviar mensaje QR empresa %s", company_id)
        return jsonify({"error": str(exc)}), 503
