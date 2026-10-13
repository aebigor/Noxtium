from app import create_app
from app.database import db
from app.models import Company

app = create_app()
with app.app_context():
    company = Company(name="IMPERIO DEL BARRIL", email="demo@imperiodelbarril.local")
    db.session.add(company)
    db.session.commit()
    print(f"Empresa creada. company_id={company.id}")
