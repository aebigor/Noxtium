from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, render_template, request, session, redirect, url_for
from sqlalchemy.exc import IntegrityError
import hmac

from app.crypto import encrypt_token, decrypt_token
from app.database import db
from app.models import WhatsAppConnection, WhatsAppMessage, AgentConfiguration, User, Subscription, ServicePlan, Service, N8NTokenUsageEvent
from app.services.meta_service import MetaService, MetaAPIError

meta_bp = Blueprint("meta", __name__, url_prefix="/api/meta")


def _current_client():
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id else None
    if not user or not user.is_active or user.role == "admin":
        return None
    return user


def _active_crm_subscription(company_id, lock=False):
    now = datetime.now(timezone.utc)
    query = (Subscription.query.join(ServicePlan, Subscription.service_plan_id == ServicePlan.id)
        .join(Service, ServicePlan.service_id == Service.id)
        .filter(Subscription.company_id == company_id,
                Subscription.status == "ACTIVE", Service.slug == "crm-chatbot",
                db.or_(Subscription.expires_at.is_(None), Subscription.expires_at > now))
        .order_by(Subscription.created_at.desc()))
    if lock:
        query = query.with_for_update()
    return query.first()


def _has_active_crm(user):
    return _active_crm_subscription(user.company_id) is not None


def _n8n_authorized():
    expected_secret = current_app.config.get("N8N_WEBHOOK_SECRET", "")
    received_secret = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return bool(expected_secret and hmac.compare_digest(received_secret, expected_secret))


def _token_quota(subscription):
    if not subscription:
        return 0
    return max(0, int(subscription.token_limit or subscription.plan.included_tokens or 0))


@meta_bp.get("/whatsapp")
def whatsapp_page():
    user = _current_client()
    if not user:
        return redirect(url_for("login"))
    if not _has_active_crm(user):
        return render_template("service_locked.html"), 403
    connection = WhatsAppConnection.query.filter_by(company_id=user.company_id, status="active").first()
    return render_template(
        "whatsapp.html",
        user=user,
        connection=connection,
        meta_app_id=current_app.config.get("META_APP_ID", ""),
        meta_graph_version=current_app.config.get("META_GRAPH_VERSION", "v25.0"),
        meta_configured=bool(current_app.config.get("META_APP_ID") and current_app.config.get("META_EMBEDDED_SIGNUP_CONFIG_ID")),
        meta_config_id=current_app.config.get("META_EMBEDDED_SIGNUP_CONFIG_ID", ""),
    )


@meta_bp.post("/embedded-signup")
def embedded_signup():
    user = _current_client()
    if not user:
        return jsonify({"error": "Inicia sesión con una cuenta de cliente para conectar WhatsApp."}), 401
    if not _has_active_crm(user):
        return jsonify({"error": "Necesitas una suscripción CRM activa y aprobada para conectar WhatsApp."}), 403

    body = request.get_json(silent=True) or {}
    code = (body.get("code") or "").strip()
    waba_id = str(body.get("waba_id") or "").strip()
    phone_number_id = str(body.get("phone_number_id") or "").strip()
    if not code or not waba_id.isdigit() or not phone_number_id.isdigit():
        return jsonify({"error": "Meta no entregó todos los datos necesarios. Repite el registro desde el botón oficial."}), 400
    if not current_app.config.get("META_APP_ID") or not current_app.config.get("META_APP_SECRET"):
        return jsonify({"error": "La integración de Meta aún no está configurada por el administrador de NOXTIUM."}), 503
    if not current_app.config.get("FERNET_KEY"):
        return jsonify({"error": "Falta configurar el cifrado seguro de credenciales (FERNET_KEY). Contacta al administrador."}), 503

    try:
        service = MetaService()
        token_data = service.exchange_code(code)
        access_token = token_data.get("access_token")
        if not access_token:
            raise MetaAPIError("Meta no devolvió un token de acceso.")
        phone_data = service.get_phone_number(phone_number_id, access_token)
        # The phone ID must be accessible with the token issued for this signup.
        if str(phone_data.get("id", "")) != phone_number_id:
            raise MetaAPIError("Meta no confirmó el número elegido.")
        connection = WhatsAppConnection.query.filter_by(company_id=user.company_id).first()
        other_company = WhatsAppConnection.query.filter_by(phone_number_id=phone_number_id).first()
        if other_company and other_company.company_id != user.company_id:
            return jsonify({"error": "Ese número ya está asociado a otra empresa en NOXTIUM. Contacta soporte si crees que es un error."}), 409
        service.subscribe_waba(waba_id, access_token)
        if connection and connection.phone_number_id != phone_number_id:
            # Do not silently overwrite a different company's number; this row belongs to this company.
            connection.waba_id = waba_id
            connection.phone_number_id = phone_number_id
        elif not connection:
            connection = WhatsAppConnection(company_id=user.company_id, waba_id=waba_id, phone_number_id=phone_number_id)
            db.session.add(connection)
        connection.waba_id = waba_id
        connection.phone_number_id = phone_number_id
        connection.display_phone_number = phone_data.get("display_phone_number")
        connection.verified_name = phone_data.get("verified_name")
        connection.access_token_encrypted = encrypt_token(access_token)
        connection.token_type = token_data.get("token_type", "business_integration_system_user")
        connection.status = "active"
        db.session.commit()
        return jsonify({
            "success": True,
            "connection_id": connection.id,
            "display_phone_number": connection.display_phone_number,
            "verified_name": connection.verified_name,
            "next_url": url_for("portal.agent_setup", connected=1),
        })
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Ese número de WhatsApp ya está conectado en NOXTIUM. Verifica la empresa asociada."}), 409
    except MetaAPIError as exc:
        db.session.rollback()
        current_app.logger.warning("Meta Embedded Signup no completado para empresa %s: %s", user.company_id, exc)
        return jsonify({"error": "Meta no pudo verificar la conexión. Revisa los permisos de la aplicación y vuelve a intentarlo."}), 502
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error conectando Meta WhatsApp para empresa %s", user.company_id)
        return jsonify({"error": "No se pudo completar la conexión. Revisa la configuración de Meta y vuelve a intentarlo."}), 500


@meta_bp.get("/n8n/token-balance")
def n8n_token_balance():
    """Balance lookup for n8n before invoking an AI/model node."""
    if not _n8n_authorized():
        return jsonify({"error": "No autorizado."}), 401
    try:
        company_id = int(request.args.get("company_id", ""))
    except (TypeError, ValueError):
        return jsonify({"error": "company_id es obligatorio."}), 400
    active = _active_crm_subscription(company_id)
    if not active:
        return jsonify({"error": "La suscripción CRM de esta empresa no está activa.", "allowed": False}), 403
    limit = _token_quota(active)
    used = max(0, int(active.tokens_used or 0))
    remaining = max(0, limit - used)
    return jsonify({
        "company_id": company_id,
        "subscription_id": active.id,
        "plan": active.plan.name,
        "token_limit": limit,
        "tokens_used": used,
        "tokens_remaining": remaining,
        "allowed": remaining > 0,
    })


@meta_bp.post("/n8n/token-usage")
def n8n_record_token_usage():
    """Idempotently record the input/output tokens reported by an n8n model node."""
    if not _n8n_authorized():
        return jsonify({"error": "No autorizado."}), 401
    body = request.get_json(silent=True) or {}
    try:
        company_id = int(body.get("company_id"))
        input_tokens = int(body.get("input_tokens", 0) or 0)
        output_tokens = int(body.get("output_tokens", 0) or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "company_id, input_tokens y output_tokens deben ser números enteros."}), 400
    event_id = str(body.get("event_id") or "").strip()[:200]
    workflow_id = str(body.get("workflow_id") or "").strip()[:120] or None
    if not event_id or input_tokens < 0 or output_tokens < 0 or input_tokens + output_tokens < 1:
        return jsonify({"error": "Indica event_id y un consumo positivo de tokens de entrada/salida."}), 400

    # Serialize quota increments by company and make retries idempotent.
    active = _active_crm_subscription(company_id, lock=True)
    if not active:
        return jsonify({"error": "La suscripción CRM de esta empresa no está activa."}), 403
    existing = N8NTokenUsageEvent.query.filter_by(company_id=company_id, event_id=event_id).first()
    if existing:
        quota = _token_quota(active)
        used = max(0, int(active.tokens_used or 0))
        return jsonify({"success": True, "duplicate": True, "event_id": event_id,
                        "token_limit": quota, "tokens_used": used,
                        "tokens_remaining": max(0, quota-used), "allowed": quota > 0 and used <= quota})

    total_tokens = input_tokens + output_tokens
    event = N8NTokenUsageEvent(company_id=company_id, subscription_id=active.id,
        event_id=event_id, input_tokens=input_tokens, output_tokens=output_tokens,
        total_tokens=total_tokens, workflow_id=workflow_id)
    db.session.add(event)
    active.tokens_used = int(active.tokens_used or 0) + total_tokens
    db.session.commit()
    quota = _token_quota(active)
    used = int(active.tokens_used or 0)
    remaining = max(0, quota - used)
    return jsonify({"success": True, "duplicate": False, "event_id": event_id,
                    "tokens_added": total_tokens, "token_limit": quota,
                    "tokens_used": used, "tokens_remaining": remaining,
                    "allowed": quota > 0 and used <= quota, "limit_exceeded": used > quota})


@meta_bp.post("/send-message")
def send_message_from_n8n():
    """Secure server-to-server send endpoint for the NOXTIUM n8n workflow."""
    if not _n8n_authorized():
        return jsonify({"error": "No autorizado."}), 401

    body = request.get_json(silent=True) or {}
    try:
        company_id = int(body.get("company_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "company_id es obligatorio."}), 400
    recipient = "".join(ch for ch in str(body.get("to") or "") if ch.isdigit())
    message_text = str(body.get("text") or "").strip()
    if not (8 <= len(recipient) <= 15) or not message_text or len(message_text) > 4096:
        return jsonify({"error": "Indica un destinatario con indicativo de país y un mensaje de hasta 4096 caracteres."}), 400

    agent = AgentConfiguration.query.filter_by(company_id=company_id).first()
    if not agent or agent.status != "ACTIVE":
        return jsonify({"error": "El agente de esta empresa no está activo en NOXTIUM."}), 409
    now = datetime.now(timezone.utc)
    active = _active_crm_subscription(company_id)
    if not active:
        return jsonify({"error": "La suscripción CRM de esta empresa no está activa."}), 403
    quota = _token_quota(active)
    if quota < 1 or int(active.tokens_used or 0) > quota:
        return jsonify({"error": "La empresa agotó su cupo de tokens de IA para n8n.",
                        "token_limit": quota, "tokens_used": int(active.tokens_used or 0),
                        "tokens_remaining": 0}), 402
    connection = WhatsAppConnection.query.filter_by(company_id=company_id, status="active").first()
    if not connection:
        return jsonify({"error": "La empresa no tiene una conexión oficial de WhatsApp activa."}), 409

    try:
        token = decrypt_token(connection.access_token_encrypted)
        result = MetaService().send_text_message(connection.phone_number_id, token, recipient, message_text)
        sent = (result.get("messages") or [{}])[0]
        message_id = sent.get("id")
        if message_id:
            existing = WhatsAppMessage.query.filter_by(message_id=message_id).first()
            if not existing:
                db.session.add(WhatsAppMessage(
                    company_id=company_id,
                    whatsapp_connection_id=connection.id,
                    message_id=message_id,
                    from_number=connection.display_phone_number,
                    to_number=recipient,
                    message_type="text",
                    message_text=message_text,
                    raw_payload={"source": "n8n", "meta_response": result},
                ))
                db.session.commit()
        return jsonify({"success": True, "message_id": message_id, "status": "accepted_by_meta"})
    except MetaAPIError:
        db.session.rollback()
        current_app.logger.exception("Meta rechazó un envío solicitado por n8n para empresa %s.", company_id)
        return jsonify({"error": "Meta no aceptó el mensaje. Comprueba el formato del número, el estado de la cuenta, la ventana de atención y las plantillas aprobadas."}), 502
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error enviando mensaje de n8n por Meta para empresa %s.", company_id)
        return jsonify({"error": "No se pudo enviar el mensaje a través de Meta."}), 500
