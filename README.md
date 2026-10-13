# NOXTIUM CRM + Chatbot

Primera versión del portal comercial de NOXTIUM: registro de clientes, catálogo de servicios, suscripciones, bloqueo hasta pago, conexión de WhatsApp y base para automatizaciones con n8n.

## Flujo actual

1. El visitante crea una cuenta.
2. Entra al dashboard sin servicios activos.
3. Selecciona **CRM + Chatbot**.
4. Se crea una suscripción `PENDING_PAYMENT`.
5. El CRM y WhatsApp permanecen bloqueados.
6. La página de pago queda preparada para conectar una pasarela real.
7. Para pruebas locales existe **Confirmar pago de prueba**.
8. Al pasar a `ACTIVE`, se habilita **Conectar WhatsApp Business**.
9. Meta Embedded Signup guarda la conexión por empresa.

## Migración

Después de copiar el proyecto y configurar `.env`:

```powershell
alembic upgrade head
python app.py
```

La nueva migración es `0002_billing_portal`. No se usa `db.create_all()` como autoridad del esquema.

## Prueba rápida

```text
http://127.0.0.1:5000/registro
```

Crea una cuenta, entra al dashboard y contrata CRM + Chatbot. Para esta etapa utiliza el botón de pago de prueba. Después reemplazaremos ese botón por una pasarela real (por ejemplo Wompi/PayU/Stripe) y la activación dependerá del webhook de pago.

## Seguridad

Los tokens de WhatsApp siguen almacenándose cifrados. Las credenciales por cliente no deben colocarse en `.env`; allí solo van las credenciales globales de la aplicación Meta y n8n.


## Roles, revisión manual y preconsultas

- El usuario `noxtium@noxtium.com` debe tener `role=admin`; créalo con `python scripts/create_admin.py`. El seed solicita la contraseña en consola.
- El administrador entra a `/admin/dashboard`, donde solo ve comprobantes enviados y preconsultas. No ve catálogo ni puede conectar WhatsApp como cliente.
- Los clientes pueden ver el catálogo. Para CRM + Chatbot deben subir un comprobante válido; la activación ocurre solo al aprobarlo desde el panel.
- La integración de módulos no cobra ni activa un servicio: crea una preconsulta gratuita para coordinar reunión por WhatsApp o correo.
- Después de copiar el proyecto: `alembic upgrade head`. La migración `0003_roles_receipts_consultations` agrega roles, comprobantes y solicitudes.
- Configura `ADMIN_EMAILS`, `NEQUI_PHONE`, `NEQUI_ACCOUNT_NAME` y `NEQUI_QR_URL` en tu `.env`. Coloca el QR en `static/uploads/nequi-qr.png` si usas la ruta predeterminada.
- El archivo `.env` real nunca debe compartirse ni incluirse en ZIP.
