"""Crea o convierte la cuenta NOXTIUM en administradora."""
import sys
from pathlib import Path

# Al ejecutar `python scripts\\create_admin.py`, Python agrega scripts/ a
# sys.path, no necesariamente la raíz del proyecto.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import getpass
from app import create_app
from app.database import db
from app.models import Company, User
from werkzeug.security import generate_password_hash

EMAIL = "noxtium@noxtium.com"
app = create_app()

with app.app_context():
    # Evita consultar User.role antes de que exista la columna en PostgreSQL.
    inspector = db.inspect(db.engine)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "role" not in user_columns:
        raise SystemExit(
            "Falta la columna users.role. Ejecuta primero: "
            "python -m alembic upgrade head"
        )

    company = Company.query.filter(db.func.lower(Company.name) == "noxtium").first()
    user = User.query.filter_by(email=EMAIL).first()

    if not company:
        company = Company(name="NOXTIUM", email=EMAIL, is_active=True)
        db.session.add(company)
        db.session.flush()

    company.name = "NOXTIUM"
    company.is_active = True

    if not user:
        password = getpass.getpass("Contraseña para noxtium@noxtium.com (mínimo 12 caracteres): ")
        confirm = getpass.getpass("Confirmar contraseña: ")
        if len(password) < 12 or password != confirm:
            raise SystemExit("Contraseña demasiado corta o las contraseñas no coinciden.")
        user = User(
            company_id=company.id,
            full_name="Administrador NOXTIUM",
            email=EMAIL,
            password_hash=generate_password_hash(password),
            role="admin",
            is_active=True,
        )
        db.session.add(user)
    else:
        user.company_id = company.id
        user.role = "admin"
        user.is_active = True
        reset = input("¿Restablecer la contraseña? [s/N]: ").strip().lower() == "s"
        if reset:
            password = getpass.getpass("Nueva contraseña (mínimo 12 caracteres): ")
            confirm = getpass.getpass("Confirmar contraseña: ")
            if len(password) < 12 or password != confirm:
                raise SystemExit("Contraseña demasiado corta o las contraseñas no coinciden.")
            user.password_hash = generate_password_hash(password)

    db.session.commit()
    print(f"Administrador listo: {EMAIL} | empresa: NOXTIUM | role={user.role}")
