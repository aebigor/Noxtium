import os
from pathlib import Path

from dotenv import load_dotenv


# ============================================================
# RUTAS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

# Cargar SIEMPRE el .env ubicado en la raíz del proyecto
ENV_FILE = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_FILE, override=True)


# ============================================================
# CONFIGURACIÓN
# ============================================================

class Config:
    # --------------------------------------------------------
    # Flask
    # --------------------------------------------------------

    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "NOXTIUM_CHANGE_THIS_SECRET_KEY",
    )

    # --------------------------------------------------------
    # PostgreSQL
    # --------------------------------------------------------

    DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

    # NO permitimos que NOXTIUM caiga silenciosamente en SQLite.
    if not DATABASE_URL:
        raise RuntimeError(
            "NOXTIUM: no se encontró DATABASE_URL en el archivo .env. "
            "Configura PostgreSQL antes de iniciar Flask."
        )

    if DATABASE_URL.startswith("sqlite"):
        raise RuntimeError(
            "NOXTIUM: DATABASE_URL está configurada como SQLite. "
            "Este proyecto utiliza PostgreSQL. "
            "Revisa el archivo .env."
        )

    # Compatibilidad con URLs PostgreSQL tradicionales.
    # psycopg 3 utiliza postgresql+psycopg.
    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --------------------------------------------------------
    # Meta / WhatsApp
    # --------------------------------------------------------

    META_APP_ID = os.getenv(
        "META_APP_ID",
        "",
    )

    META_APP_SECRET = os.getenv(
        "META_APP_SECRET",
        "",
    )

    META_GRAPH_VERSION = os.getenv(
        "META_GRAPH_VERSION",
        "v25.0",
    )

    META_EMBEDDED_SIGNUP_CONFIG_ID = os.getenv(
        "META_EMBEDDED_SIGNUP_CONFIG_ID",
        "",
    )

    META_WEBHOOK_VERIFY_TOKEN = os.getenv(
        "META_WEBHOOK_VERIFY_TOKEN",
        "",
    )

    # --------------------------------------------------------
    # Meta - números de prueba
    # --------------------------------------------------------

    META_TEST_PHONE_NUMBER_ID = os.getenv(
        "META_TEST_PHONE_NUMBER_ID",
        "",
    )

    META_TEST_WABA_ID = os.getenv(
        "META_TEST_WABA_ID",
        "",
    )

    # --------------------------------------------------------
    # n8n
    # --------------------------------------------------------

    N8N_WEBHOOK_URL = os.getenv(
        "N8N_WEBHOOK_URL",
        "",
    )

    N8N_WEBHOOK_SECRET = os.getenv(
        "N8N_WEBHOOK_SECRET",
        "",
    )
    N8N_PROVISION_WEBHOOK_URL = os.getenv("N8N_PROVISION_WEBHOOK_URL", "").strip()

    # --------------------------------------------------------
    # Cifrado
    # --------------------------------------------------------

    FERNET_KEY = os.getenv(
        "FERNET_KEY",
        "",
    )

    # --------------------------------------------------------
    # Administración y comprobantes
    # --------------------------------------------------------
    ADMIN_EMAILS = [
        email.strip().lower()
        for email in os.getenv("ADMIN_EMAILS", "noxtium@noxtium.com").split(",")
        if email.strip()
    ]
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
    RECEIPTS_UPLOAD_FOLDER = str(BASE_DIR / "static" / "uploads" / "receipts")
    NEQUI_PHONE = os.getenv("NEQUI_PHONE", "")
    NEQUI_ACCOUNT_NAME = os.getenv("NEQUI_ACCOUNT_NAME", "NOXTIUM")
    NEQUI_QR_URL = os.getenv("NEQUI_QR_URL", "/static/uploads/nequi-qr.png")
    # Optional product pricing. Leave inventory at 0 until the commercial price is decided.
    NOXTIUM_INVENTORY_MONTHLY_PRICE = int(os.getenv("NOXTIUM_INVENTORY_MONTHLY_PRICE", "0") or 0)
    NOXTIUM_INVENTORY_QUARTERLY_PRICE = int(os.getenv("NOXTIUM_INVENTORY_QUARTERLY_PRICE", "0") or 0)
    NOXTIUM_INVENTORY_ANNUAL_PRICE = int(os.getenv("NOXTIUM_INVENTORY_ANNUAL_PRICE", "0") or 0)
    # Default token allowances are configurable per CRM subscription period.
    NOXTIUM_CRM_MONTHLY_TOKENS = max(0, int(os.getenv("NOXTIUM_CRM_MONTHLY_TOKENS", "100000") or 0))
    NOXTIUM_CRM_QUARTERLY_TOKENS = max(0, int(os.getenv("NOXTIUM_CRM_QUARTERLY_TOKENS", "300000") or 0))
    NOXTIUM_CRM_ANNUAL_TOKENS = max(0, int(os.getenv("NOXTIUM_CRM_ANNUAL_TOKENS", "1200000") or 0))
    CONSULTATION_WHATSAPP = os.getenv("CONSULTATION_WHATSAPP", "")
    N8N_CONSULTATION_WEBHOOK_URL = os.getenv("N8N_CONSULTATION_WEBHOOK_URL", "")

    # --------------------------------------------------------
    # Desarrollo
    # --------------------------------------------------------

    DEMO_COMPANY_ID = os.getenv(
        "DEMO_COMPANY_ID",
        "",
    )

    DEVELOPMENT_PAYMENT_DEMO = (
        os.getenv(
            "DEVELOPMENT_PAYMENT_DEMO",
            "true",
        ).strip().lower()
        == "true"
    )

    # Web Push para campañas de tarjetas de lealtad.
    VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
    VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
    VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:soporte@noxtium.com")
