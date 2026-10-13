from logging.config import fileConfig
from pathlib import Path
import os

from alembic import context
from sqlalchemy import create_engine, pool

from dotenv import load_dotenv

from app.database import db
from app import models  # noqa: F401


# ============================================================
# RUTA DEL PROYECTO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

ENV_FILE = BASE_DIR / ".env"

load_dotenv(
    dotenv_path=ENV_FILE,
    override=True,
)


# ============================================================
# CONFIGURACIÓN ALEMBIC
# ============================================================

config = context.config


# ============================================================
# LOGGING
# ============================================================

if config.config_file_name:
    try:
        fileConfig(config.config_file_name)
    except (KeyError, ValueError):
        pass


# ============================================================
# BASE DE DATOS
# ============================================================

database_url = os.getenv("DATABASE_URL", "").strip()

if not database_url:
    raise RuntimeError(
        "NOXTIUM: DATABASE_URL no está definida en .env"
    )


# Convertir URL PostgreSQL antigua si fuera necesario
if database_url.startswith("postgresql://"):
    database_url = database_url.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1,
    )


# Evitar que Alembic utilice SQLite
if database_url.startswith("sqlite"):
    raise RuntimeError(
        "NOXTIUM: Alembic está intentando utilizar SQLite. "
        "DATABASE_URL debe apuntar a PostgreSQL."
    )


# Mostrar solamente información segura
safe_url = database_url

if "@" in safe_url and "://" in safe_url:
    prefix, suffix = safe_url.split("@", 1)

    if ":" in prefix:
        scheme, credentials = prefix.split("://", 1)

        if ":" in credentials:
            username = credentials.split(":", 1)[0]
            safe_url = f"{scheme}://{username}:********@{suffix}"


print()
print("=" * 70)
print("NOXTIUM - ALEMBIC")
print("=" * 70)
print(f"Base de datos: {safe_url}")
print("=" * 70)
print()


# ============================================================
# METADATA
# ============================================================

target_metadata = db.metadata


# ============================================================
# MIGRACIÓN OFFLINE
# ============================================================

def run_migrations_offline():

    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named"
        },
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ============================================================
# MIGRACIÓN ONLINE
# ============================================================

def run_migrations_online():

    engine = create_engine(
        database_url,
        poolclass=pool.NullPool,
        future=True,
    )

    try:

        with engine.connect() as connection:

            print(
                "Conexión PostgreSQL establecida correctamente."
            )

            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )

            with context.begin_transaction():

                context.run_migrations()

    finally:

        engine.dispose()


# ============================================================
# EJECUCIÓN
# ============================================================

if context.is_offline_mode():

    run_migrations_offline()

else:

    run_migrations_online()