import hashlib
import hmac
import json

from flask import Blueprint, current_app, jsonify, request, Response

from app.database import db
from app.models import WhatsAppConnection, WhatsAppMessage
from app.services.n8n_service import N8NService

webhook_bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")


def verify_signature(raw_body: bytes, signature: str | None) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False

    received = signature.removeprefix("sha256=")
    secret = current_app.config.get("META_APP_SECRET", "")

    expected = hmac.new(
        secret.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(received, expected)


@webhook_bp.get("/whatsapp")
def verify_whatsapp_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    expected = current_app.config.get("META_WEBHOOK_VERIFY_TOKEN", "")

    if mode == "subscribe" and token == expected and challenge:
        return Response(challenge, status=200, mimetype="text/plain")

    return Response("Forbidden", status=403)


@webhook_bp.post("/whatsapp")
def receive_whatsapp_webhook():
    raw_body = request.get_data(cache=False)

    if not verify_signature(
        raw_body,
        request.headers.get("X-Hub-Signature-256"),
    ):
        return Response("Invalid signature", status=401)

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return Response("Invalid JSON", status=400)

    try:
        process_whatsapp_payload(payload)
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error procesando webhook de WhatsApp.")
        return Response("Processing error", status=500)

    return jsonify({"success": True})


def process_whatsapp_payload(payload: dict):
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            metadata = value.get("metadata", {})
            phone_number_id = metadata.get("phone_number_id")

            if not phone_number_id:
                continue

            connection = (
                db.session.query(WhatsAppConnection)
                .filter_by(
                    phone_number_id=phone_number_id,
                    status="active",
                )
                .first()
            )

            if not connection:
                current_app.logger.warning(
                    "phone_number_id no registrado: %s",
                    phone_number_id,
                )
                continue

            for message in value.get("messages", []):
                process_message(connection, message, payload)

            for status in value.get("statuses", []):
                current_app.logger.info(
                    "WhatsApp status company=%s: %s",
                    connection.company_id,
                    status,
                )


def process_message(connection, message: dict, raw_payload: dict):
    message_id = message.get("id")
    if not message_id:
        return

    # Meta puede reintentar eventos: no duplicamos por message_id.
    existing = (
        db.session.query(WhatsAppMessage)
        .filter_by(message_id=message_id)
        .first()
    )
    if existing:
        return

    message_type = message.get("type")
    message_text = None

    if message_type == "text":
        message_text = message.get("text", {}).get("body")

    db_message = WhatsAppMessage(
        company_id=connection.company_id,
        whatsapp_connection_id=connection.id,
        message_id=message_id,
        from_number=message.get("from"),
        to_number=connection.display_phone_number,
        message_type=message_type,
        message_text=message_text,
        raw_payload=raw_payload,
    )

    db.session.add(db_message)
    db.session.commit()

    payload = {
        "event": "whatsapp.message",
        "company": {
            "id": connection.company_id,
        },
        "whatsapp": {
            "connection_id": connection.id,
            "waba_id": connection.waba_id,
            "phone_number_id": connection.phone_number_id,
            "display_phone_number": connection.display_phone_number,
        },
        "message": message,
        "raw": raw_payload,
    }

    N8NService().send_whatsapp_event(payload)
