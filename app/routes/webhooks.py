import hashlib
import hmac
import json
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request, Response
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import func

from app.database import db
from app.models import WhatsAppConnection, WhatsAppMessage, CRMContact, AgentConfiguration, Subscription, ServicePlan, Service
from app.services.n8n_service import N8NService

webhook_bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")


def verify_signature(raw_body: bytes, signature: str | None) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False
    secret = current_app.config.get("META_APP_SECRET", "")
    if not secret:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature.removeprefix("sha256="), expected)


@webhook_bp.get("/whatsapp")
def verify_whatsapp_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    expected = current_app.config.get("META_WEBHOOK_VERIFY_TOKEN", "")
    if expected and mode == "subscribe" and hmac.compare_digest(token or "", expected) and challenge:
        return Response(challenge, status=200, mimetype="text/plain")
    return Response("Forbidden", status=403)


@webhook_bp.post("/whatsapp")
def receive_whatsapp_webhook():
    raw_body = request.get_data(cache=False)
    if not verify_signature(raw_body, request.headers.get("X-Hub-Signature-256")):
        return Response("Invalid signature", status=401)
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return Response("Invalid JSON", status=400)
    try:
        process_whatsapp_payload(payload)
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error procesando webhook oficial de WhatsApp.")
        return Response("Processing error", status=500)
    return jsonify({"success": True})


def process_whatsapp_payload(payload: dict):
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_number_id = str(value.get("metadata", {}).get("phone_number_id") or "")
            if not phone_number_id:
                continue
            connection = (db.session.query(WhatsAppConnection)
                .filter_by(phone_number_id=phone_number_id, status="active").first())
            if not connection:
                current_app.logger.warning("Meta webhook: phone_number_id no registrado en NOXTIUM: %s", phone_number_id)
                continue
            contacts = {str(item.get("wa_id")): item.get("profile", {}).get("name")
                        for item in value.get("contacts", []) if item.get("wa_id")}
            for message in value.get("messages", []):
                process_message(connection, message, payload, contacts.get(str(message.get("from") or "")))
            for status in value.get("statuses", []):
                current_app.logger.info("WhatsApp status company=%s: %s", connection.company_id, status.get("status", "unknown"))


def process_message(connection, message: dict, raw_payload: dict, contact_name=None):
    message_id = message.get("id")
    sender = str(message.get("from") or "").strip()
    if not message_id or not sender:
        return
    if WhatsAppMessage.query.filter_by(message_id=message_id).first():
        return  # Meta may retry the same event.

    message_type = message.get("type")
    message_text = message.get("text", {}).get("body") if message_type == "text" else None
    db.session.add(WhatsAppMessage(
        company_id=connection.company_id,
        whatsapp_connection_id=connection.id,
        message_id=message_id,
        from_number=sender,
        to_number=connection.display_phone_number,
        message_type=message_type,
        message_text=message_text,
        raw_payload=raw_payload,
    ))

    # Upsert contacts so repeat messages never cause uq_crm_contacts_company_phone errors.
    now = datetime.now(timezone.utc)
    statement = pg_insert(CRMContact).values(
        company_id=connection.company_id,
        phone=sender,
        contact_name=contact_name,
        status="NEW",
        tags=[],
        notes=None,
        last_message_at=now,
        created_at=now,
        updated_at=now,
    ).on_conflict_do_update(
        constraint="uq_crm_contacts_company_phone",
        set_={
            "contact_name": func.coalesce(CRMContact.contact_name, contact_name),
            "last_message_at": now,
            "updated_at": now,
        },
    )
    db.session.execute(statement)
    db.session.commit()

    # New users may receive messages before their agent/n8n flow is ready.
    # Store the conversation, but do not trigger sales automation until activation is confirmed.
    agent = AgentConfiguration.query.filter_by(company_id=connection.company_id).first()
    if not agent or agent.status != "ACTIVE":
        current_app.logger.info("Mensaje almacenado sin automatización: empresa %s aún no tiene agente ACTIVE.", connection.company_id)
        return
    now_for_subscription = datetime.now(timezone.utc)
    crm_subscription = (Subscription.query.join(ServicePlan).join(Service)
        .filter(Subscription.company_id == connection.company_id, Subscription.status == "ACTIVE",
                Service.slug == "crm-chatbot",
                db.or_(Subscription.expires_at.is_(None), Subscription.expires_at > now_for_subscription))
        .order_by(Subscription.created_at.desc()).first())
    if not crm_subscription:
        current_app.logger.info("Mensaje almacenado sin automatización: empresa %s sin suscripción CRM activa.", connection.company_id)
        return
    token_limit = int(crm_subscription.token_limit or crm_subscription.plan.included_tokens or 0)
    tokens_used = int(crm_subscription.tokens_used or 0)
    if token_limit < 1 or tokens_used >= token_limit:
        current_app.logger.warning("Mensaje almacenado sin automatización: empresa %s agotó su cupo de tokens (%s/%s).", connection.company_id, tokens_used, token_limit)
        return

    event_payload = {
        "event": "whatsapp.message",
        "company": {"id": connection.company_id},
        "whatsapp": {
            "connection_id": connection.id,
            "waba_id": connection.waba_id,
            "phone_number_id": connection.phone_number_id,
            "display_phone_number": connection.display_phone_number,
            "provider": "meta_cloud_api",
        },
        "message": message,
    }
    try:
        N8NService().send_whatsapp_event(event_payload)
    except Exception:
        # Do not make Meta retry an event that is already persisted; log for admin follow-up.
        current_app.logger.exception("No se pudo entregar a n8n el mensaje %s de empresa %s.", message_id, connection.company_id)
