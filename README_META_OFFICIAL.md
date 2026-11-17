# NOXTIUM — Migración a WhatsApp Business Platform oficial de Meta

## Qué se cambió en el código

- La página de conexión ahora usa Meta Embedded Signup; las rutas `/whatsapp/qr` redirigen a la pantalla oficial.
- `POST /api/meta/embedded-signup` verifica sesión cliente/suscripción, intercambia el código en el servidor, consulta el número por Graph API, suscribe la aplicación al WABA y cifra el token antes de guardarlo en `whatsapp_connections`.
- `GET /webhooks/whatsapp` permite la verificación de Meta; `POST /webhooks/whatsapp` valida `X-Hub-Signature-256`, guarda mensajes y contactos y envía un evento normalizado a `N8N_WEBHOOK_URL`.
- El envío de respuestas de n8n se mantiene compatible con `/webhooks/qr-whatsapp/send` y añade `/webhooks/whatsapp/send`, pero ambas rutas usan Meta Cloud API, nunca Baileys.
- Se conserva el asistente del menú/agente y la lógica de aprovisionamiento `N8N_PROVISION_WEBHOOK_URL`.
- Las tablas y mensajes antiguos del modo QR no se borran. El QR deja de contar como conexión activa para activar el agente; cada empresa debe vincular oficialmente su número.

## 1. Copia de seguridad antes de aplicar

1. Detén Flask y, si se está ejecutando, la terminal de `npm start` de `whatsapp_service`.
2. Haz una copia de toda la carpeta NOXTIUM y una copia de seguridad de PostgreSQL.
3. Descomprime el ZIP del parche y copia sobre el proyecto únicamente los archivos que contiene, respetando las carpetas. No reemplaces tu `.env`.
4. No borres `whatsapp_service/sessions` ni las tablas antiguas durante la primera validación.

## 2. Variables del `.env` principal

Agrega estas claves al `.env` que ya usas; conserva `DATABASE_URL`, `SECRET_KEY`, las variables de pagos y las de n8n:

```env
META_APP_ID=ID_DE_LA_APP_META
META_APP_SECRET=SECRETO_DE_LA_APP_META
META_GRAPH_VERSION=v25.0
META_EMBEDDED_SIGNUP_CONFIG_ID=ID_DE_LA_CONFIGURACION_EMBEDDED_SIGNUP
META_WEBHOOK_VERIFY_TOKEN=UN_TOKEN_ALEATORIO_LARGO
FERNET_KEY=CLAVE_FERNET_GENERADA

WHATSAPP_TEST_MODE=true
WHATSAPP_TEST_RECIPIENTS=573001234567

N8N_WEBHOOK_URL=https://n8n.noxtium.com/webhook/noxtium-whatsapp
N8N_WEBHOOK_SECRET=EL_MISMO_SECRETO_CONFIGURADO_EN_N8N
N8N_PROVISION_WEBHOOK_URL=TU_WEBHOOK_DE_APROVISIONAMIENTO
```

- `META_APP_ID`, `META_APP_SECRET` y el identificador de Embedded Signup provienen de tu aplicación en Meta for Developers.
- La pantalla pide un PIN de 6 dígitos para la verificación en dos pasos y el backend llama a `/{phone_number_id}/register`. El PIN se transmite solo para esa operación; no se guarda en PostgreSQL, no se registra en los logs y no se envía a n8n. Si el endpoint confirma que el número ya estaba registrado en Cloud API, el alta continúa sin repetir el registro.
- No compartas ni pongas `META_APP_SECRET`, `FERNET_KEY`, tokens de acceso ni el `.env` en n8n o en el navegador.
- Si ya existe una `FERNET_KEY` usada en datos cifrados de NOXTIUM, **no la reemplaces**. Si no hay ninguna, genera una con:

```powershell
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

- `WHATSAPP_TEST_RECIPIENTS` debe ser el teléfono del cliente de prueba que enviará mensajes al número comercial, en formato internacional con dígitos solamente. Mientras el modo de prueba esté activo, los mensajes de otros remitentes se guardan pero no se envían a n8n, y las respuestas de n8n a destinos no autorizados se bloquean.
- Las variables `QR_WHATSAPP_*` antiguas pueden quedarse temporalmente en `.env`; el código nuevo ya no las usa para recibir ni enviar los mensajes oficiales. Puedes retirarlas más adelante, cuando hayas comprobado todo el flujo.

## 3. Configurar Meta for Developers

Los nombres exactos de los controles pueden variar con las actualizaciones de Meta, pero la configuración requerida es:

1. Abre la aplicación de Meta for Developers que pertenecerá a NOXTIUM. Añade/configura **WhatsApp** y la función **Embedded Signup** para que cada cliente pueda vincular su propia cuenta.
2. En Embedded Signup crea la configuración destinada a los clientes de NOXTIUM. Copia su `config_id` a `META_EMBEDDED_SIGNUP_CONFIG_ID`. Si los clientes deben mantener el uso de la app WhatsApp Business en ese mismo número, configura explícitamente el flujo de coexistencia admitido por Meta; esta entrega utiliza la ruta estándar de Cloud API, no promete coexistencia automáticamente.
3. Incluye el dominio público donde se sirve NOXTIUM en la configuración de la aplicación y en los dominios permitidos del inicio de sesión de Facebook/JavaScript SDK.
4. En **Webhooks**, configura el objeto **WhatsApp Business Account** con URL de callback `https://TU_DOMINIO_NOXTIUM/webhooks/whatsapp` y como token de verificación el mismo valor de `META_WEBHOOK_VERIFY_TOKEN`. Pulsa verificar/guardar y suscríbete al campo `messages`.
5. Tu aplicación debe poder administrar y enviar mensajes para las cuentas que conectan los clientes. Configura los permisos requeridos (`whatsapp_business_messaging` y `whatsapp_business_management`, además de los permisos que aplique al tipo de proveedor), el acceso de prueba y, antes de venderlo de forma general, los procesos de revisión/validación que Meta exija para tu tipo de proveedor. La documentación de Embedded Signup de Meta advierte que para publicar la solución se requieren App Review y Advanced Access para los permisos correspondientes.
6. Dependiendo de si NOXTIUM opera como Tech Provider/Solution Partner y de quién asume la facturación de WhatsApp, Meta puede exigir operaciones adicionales de partner, gestión de system users o línea de crédito. El parche no inventa IDs ni automatiza esos pasos financieros: completa la conexión técnica base y deja esos requisitos sujetos a tu configuración real en Meta.
6. Confirma que la URL pública use HTTPS válido. Meta no puede enviar webhooks directamente a `127.0.0.1` ni a un servidor local que no sea públicamente accesible.

La autorización, los permisos y la aprobación de Meta dependen de la configuración real de la app y del portafolio comercial. El código no puede saltarse los controles de Meta.

## 4. Ejecutar en Windows

Abre PowerShell en la raíz del proyecto con el entorno `.venv` activado:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m compileall app
.\.venv\Scripts\python.exe app.py
```

La migración inicial ya contiene las tablas `whatsapp_connections` y `whatsapp_messages`; este parche no requiere una migración destructiva ni borra datos existentes. Si tu base está a medio migrar, verifica primero `python -m alembic current` y no edites la tabla `alembic_version` manualmente.

No hace falta ejecutar `npm install` ni `npm start` para el flujo oficial. Conserva la carpeta QR temporalmente por si necesitas revisar el historial; no la expongas a internet.

## 5. Flujo paso a paso del cliente

1. El administrador aprueba el pago del servicio CRM + Chatbot.
2. El cliente entra a **WhatsApp oficial** desde NOXTIUM y pulsa **Vincular con Meta**.
3. En la ventana de Meta elige el portafolio comercial, la cuenta de WhatsApp y el número correctos, concede los permisos y termina el proceso.
4. NOXTIUM intercambia el código de autorización en el backend, confirma el número, suscribe la app al WABA y guarda el token cifrado.
5. NOXTIUM lo redirige a `/crm/agente`, donde el cliente introduce el nombre del restaurante, menú/precios, horarios, zonas de entrega, tono comercial, reglas y mensaje de bienvenida.
6. El cliente envía un mensaje desde el teléfono incluido en `WHATSAPP_TEST_RECIPIENTS`. Meta llama a `/webhooks/whatsapp`; NOXTIUM registra mensaje/contacto y envía el evento normalizado a n8n.
7. Para responder, el workflow n8n hace `POST https://TU_DOMINIO_NOXTIUM/webhooks/whatsapp/send` con `Authorization: Bearer <N8N_WEBHOOK_SECRET>` y JSON `{"company_id":1,"to":"573001234567","text":"Respuesta de prueba"}`. El endpoint responde por Meta Cloud API y guarda el registro de salida.
8. Cuando mensajes, menú y respuesta estén probados, el cliente pulsa **Probar y activar agente**. NOXTIUM conserva el requisito de que n8n confirme `{"ready": true}` en `N8N_PROVISION_WEBHOOK_URL`.

Si tu workflow actual ya usa `/webhooks/qr-whatsapp/send`, puedes mantener esa ruta durante la migración: ahora se conserva como alias que envía mediante Meta. Actualiza más adelante el nombre del nodo en n8n para que diga Meta/Cloud API, no QR.

## 6. Pruebas y solución de problemas

- `La conexión oficial no está configurada`: revisa las cinco variables obligatorias de Meta y `FERNET_KEY`; reinicia Flask tras cambiar `.env`.
- Meta devuelve que el número/cuenta no son accesibles: comprueba el `config_id`, los permisos otorgados, el acceso de la app y que el usuario de Meta eligió el WABA correcto.
- Meta no verifica el webhook: confirma que el dominio es público HTTPS, que `META_WEBHOOK_VERIFY_TOKEN` coincide exactamente y que Flask/ruteo público pueden acceder a `/webhooks/whatsapp`.
- El webhook devuelve `Invalid signature`: `META_APP_SECRET` debe coincidir con el secreto de la app que configuró el webhook. No desactives la validación de firma.
- Mensaje guardado en CRM pero no llega a n8n: confirma que `N8N_WEBHOOK_URL` usa la **Production URL** de un workflow activo, revisa el secreto, y comprueba que el remitente esté en `WHATSAPP_TEST_RECIPIENTS` con indicativo y solo dígitos.
- n8n responde con error de envío: revisa la respuesta/log de Graph API, el `phone_number_id`, el token que otorgó Embedded Signup, permisos y el destinatario autorizado.
- Las respuestas de texto libres de la API se sujetan a las ventanas y políticas de mensajería de WhatsApp. Fuera de la ventana de atención de 24 horas, normalmente debes usar una plantilla aprobada por Meta; no intentes saltarte esa regla desde n8n.

## 7. Seguridad y alcance

Los tokens de cada cliente quedan cifrados en PostgreSQL y nunca se devuelven al navegador ni se pasan al webhook de n8n. El `company_id` del alta se determina por la sesión autenticada de NOXTIUM, no por el navegador. Los eventos entrantes se validan mediante `X-Hub-Signature-256`.

Este parche conecta el onboarding oficial, la recepción Cloud API y la salida de mensajes; no crea ni configura automáticamente el workflow comercial dentro de n8n. La lógica de conversación, el prompt del vendedor, el catálogo y las reglas de cierre siguen editándose en el asistente y en el workflow de n8n.
