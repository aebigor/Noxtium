from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    session,
    redirect,
    url_for,
)

from app.crypto import encrypt_token
from app.database import db
from app.models import Company, WhatsAppConnection, User, Subscription, ServicePlan, Service
from app.services.meta_service import MetaService, MetaAPIError

meta_bp = Blueprint("meta", __name__, url_prefix="/api/meta")


@meta_bp.get("/whatsapp")
def whatsapp_page():
    # Compatibility redirect for old bookmarks and templates. NOXTIUM now uses QR mode.
    return redirect(url_for("qr_whatsapp.qr_whatsapp_page"), code=302)


@meta_bp.post("/embedded-signup")
def embedded_signup():
    return jsonify({
        "error": "NOXTIUM está configurado para conexión por QR en esta versión. Usa /whatsapp/qr."
    }), 410
