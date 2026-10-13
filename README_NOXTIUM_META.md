# NOXTIUM CRM — PostgreSQL local + Alembic + Meta + n8n

## Qué cambia

La base ya no crea tablas automáticamente con `db.create_all()`. El esquema se controla con **Alembic**.

La base local será:

```text
PostgreSQL
└── noxtium
    ├── companies
    ├── whatsapp_connections
    └── whatsapp_messages
```

Esto permite crecer después a contactos, conversaciones, agentes, campañas, etiquetas y automatizaciones.

## Tus datos de Meta de la captura

```text
phone_number_id = 1260269987179989
waba_id         = 1664973758592789
```

Los dejamos como `META_TEST_*` solo para pruebas. En el CRM real NO deben ser variables globales porque cada empresa tendrá sus propios IDs y token.

El access token de cada cliente se cifra y se guarda en `whatsapp_connections.access_token_encrypted`.

## 1. Crear PostgreSQL local

En pgAdmin o psql:

```sql
CREATE DATABASE noxtium;
```

Luego en `.env`:

```env
DATABASE_URL=postgresql+psycopg://postgres:TU_PASSWORD@localhost:5432/noxtium
```

No estamos usando ninguna base web en esta etapa.

## 2. Instalar

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 3. Crear `.env`

Copia `.env.example` a `.env` y completa:

```env
META_APP_ID=
META_APP_SECRET=
META_EMBEDDED_SIGNUP_CONFIG_ID=
META_WEBHOOK_VERIFY_TOKEN=
FERNET_KEY=
```

Genera la clave:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 4. Migraciones

Primera vez:

```powershell
alembic upgrade head
```

Comprobar:

```powershell
alembic current
alembic history
```

Para una modificación futura:

```powershell
alembic revision --autogenerate -m "add contacts"
alembic upgrade head
```

Alembic está diseñado para mantener revisiones de esquema y su `--autogenerate` compara los metadatos de SQLAlchemy con el esquema existente para crear una migración candidata que debe revisarse antes de aplicar. citeturn0search0turn0search1turn0search6

## 5. Crear empresa demo

```powershell
python scripts/create_demo_company.py
```

Luego coloca el ID mostrado:

```env
DEMO_COMPANY_ID=1
```

Esto es solo para probar Embedded Signup antes de implementar el login real de Noxtium.

## 6. Ejecutar

```powershell
python app.py
```

Abrir:

```text
http://127.0.0.1:5000/api/meta/whatsapp
```

## 7. Flujo que estamos construyendo

```text
Usuario
   |
   v
NOXTIUM
   |
   | Conectar WhatsApp
   v
Meta Embedded Signup
   |
   +--> WABA ID
   +--> phone_number_id
   +--> authorization code
   |
   v
NOXTIUM Backend
   |
   +--> intercambia code por access token
   +--> consulta teléfono
   +--> suscribe WABA
   +--> cifra token
   |
   v
PostgreSQL
   |
   v
whatsapp_connections
```

Después:

```text
WhatsApp
   |
   v
Meta
   |
   v
/webhooks/whatsapp
   |
   v
phone_number_id
   |
   v
whatsapp_connections
   |
   v
company_id
   |
   v
n8n
```

## 8. Por qué NO ponemos WABA_ID y PHONE_NUMBER_ID globales

Porque NOXTIUM será multiempresa:

```text
Empresa A
  WABA A
  phone A
  token A

Empresa B
  WABA B
  phone B
  token B

Empresa C
  WABA C
  phone C
  token C
```

Todos viven en `whatsapp_connections`.

Lo global en `.env` es la identidad de nuestra aplicación:

```text
META_APP_ID
META_APP_SECRET
META_EMBEDDED_SIGNUP_CONFIG_ID
```

## 9. Webhook local

Meta necesita poder llegar a un endpoint HTTPS público.

Tu Flask puede correr localmente, pero para recibir el webhook desde Meta necesitaremos en la siguiente prueba un túnel HTTPS hacia:

```text
http://127.0.0.1:5000/webhooks/whatsapp
```

No hace falta desplegar Noxtium en una base web todavía.

## 10. n8n

Para n8n local:

```env
N8N_WEBHOOK_URL=http://localhost:5678/webhook/noxtium-whatsapp
```

Noxtium enviará el `company_id`, `waba_id`, `phone_number_id` y mensaje.

El token de Meta NO se manda a n8n.

## 11. Seguridad

No subir:

```text
.env
META_APP_SECRET
FERNET_KEY
access tokens
```

a Git.

En producción, `company_id` debe provenir del usuario autenticado, no de un campo enviado por JavaScript.
