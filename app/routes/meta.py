from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    session,
)

from app.crypto import encrypt_token
from app.database import db
from app.models import Company, WhatsAppConnection, User, Subscription, ServicePlan, Service
from app.services.meta_service import MetaService, MetaAPIError

meta_bp = Blueprint("meta", __name__, url_prefix="/api/meta")


@meta_bp.get("/whatsapp")
def whatsapp_page():
    user_id = session.get("user_id")
    if not user_id:
        return render_template("login.html"), 401
    user = db.session.get(User, user_id)
    active = (Subscription.query.join(ServicePlan).join(Service).filter(Subscription.company_id == user.company_id, Subscription.status == "ACTIVE", Service.slug == "crm-chatbot").first() if user else None)
    if not active:
        return render_template("service_locked.html"), 403
    return render_template(
        "whatsapp.html",
        meta_app_id=current_app.config["META_APP_ID"],
        meta_version=current_app.config["META_GRAPH_VERSION"],
        config_id=current_app.config["META_EMBEDDED_SIGNUP_CONFIG_ID"],
    )


@meta_bp.post("/embedded-signup")
def embedded_signup():
    data = request.get_json(silent=True) or {}

    code = data.get("code")
    waba_id = data.get("waba_id")
    phone_number_id = data.get("phone_number_id")

    if not code:
        return jsonify({"error": "Falta code."}), 400

    if not waba_id or not phone_number_id:
        return jsonify({
            "error": "Faltan waba_id o phone_number_id."
        }), 400

    # DEMO: permite usar NOXTIUM_DEMO_COMPANY_ID.
    # En producción reemplazar por el company_id del usuario autenticado.
    company_id = session.get("company_id")
    if not company_id:
        company_id = current_app.config.get("DEMO_COMPANY_ID")

    if not company_id:
        return jsonify({
            "error": (
                "No hay empresa activa. "
                "Inicia sesión o configura DEMO_COMPANY_ID para pruebas."
            )
        }), 401

    company = db.session.get(Company, int(company_id))
    if not company:
        return jsonify({"error": "Empresa no encontrada."}), 404

    active_service = (
        Subscription.query.join(ServicePlan).join(Service)
        .filter(
            Subscription.company_id == company.id,
            Subscription.status == "ACTIVE",
            Service.slug == "crm-chatbot",
        )
        .first()
    )
    if not active_service:
        return jsonify({"error": "El servicio CRM + Chatbot no está activo."}), 403

    meta = MetaService()

    try:
        token_response = meta.exchange_code(code)
        access_token = token_response.get("access_token")
        if not access_token:
            raise MetaAPIError("Meta no devolvió access_token.")

        # Validación opcional pero recomendable.
        debug = meta.debug_token(access_token)
        current_app.logger.info(
            "Meta token debug recibido: %s",
            debug,
        )

        phone = meta.get_phone_number(
            phone_number_id,
            access_token,
        )

        # Evitar duplicar el mismo número.
        connection = (
            db.session.query(WhatsAppConnection)
            .filter_by(phone_number_id=phone_number_id)
            .first()
        )

        encrypted = encrypt_token(access_token)

        if connection:
            connection.company_id = company.id
            connection.waba_id = waba_id
            connection.display_phone_number = phone.get("display_phone_number")
            connection.verified_name = phone.get("verified_name")
            connection.access_token_encrypted = encrypted
            connection.status = "active"
        else:
            connection = WhatsAppConnection(
                company_id=company.id,
                waba_id=waba_id,
                phone_number_id=phone_number_id,
                display_phone_number=phone.get("display_phone_number"),
                verified_name=phone.get("verified_name"),
                access_token_encrypted=encrypted,
                status="active",
            )
            db.session.add(connection)

        db.session.commit()

        # Suscripción de la WABA a la app.
        # Si Meta devuelve error aquí, hacemos rollback para no dejar
        # una conexión que no esté lista para recibir webhooks.
        meta.subscribe_waba(waba_id, access_token)

        return jsonify({
            "success": True,
            "connection_id": connection.id,
            "company_id": company.id,
            "waba_id": waba_id,
            "phone_number_id": phone_number_id,
            "display_phone_number": phone.get("display_phone_number"),
            "verified_name": phone.get("verified_name"),
        })

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error en Embedded Signup.")
        return jsonify({
            "error": "No fue posible completar la conexión con Meta."
        }), 500


@meta_bp.post("/demo/company")
def create_demo_company():
    data = request.get_json(silent=True) or {}

    name = data.get("name", "Empresa Demo")
    email = data.get("email", "demo@noxtium.local")

    company = Company(name=name, email=email)
    db.session.add(company)
    db.session.commit()

    # Para facilitar la prueba local desde el navegador.
    session["company_id"] = company.id

    return jsonify({
        "success": True,
        "company_id": company.id,
        "name": company.name,
    })
