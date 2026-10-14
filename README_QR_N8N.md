# NOXTIUM — Conexión QR y pruebas n8n

## Qué incluye
- Servicio Node.js separado con Baileys para vincular WhatsApp mediante QR.
- Rutas Flask protegidas para iniciar, consultar y cerrar sesión, además de enviar mensajes de prueba.
- Persistencia aislada por `company_id`; credenciales de WhatsApp quedan en `whatsapp_service/sessions/<company_id>` y nunca se envían al navegador ni a n8n.
- Recepción de mensajes, creación/actualización de contactos CRM y envío de eventos a `N8N_WEBHOOK_URL`.
- Página `/whatsapp/qr` y asistente `/crm/agente`.
- Migración `0008_qr_whatsapp` para las conexiones y mensajes QR.
- Flujo de n8n de ejemplo en `n8n/noxtium_qr_test_workflow.json`.

## Advertencia importante
Baileys es una integración no oficial. WhatsApp puede cambiar el protocolo, desconectar sesiones o restringir cuentas. Usa un número autorizado para pruebas, respeta los términos y no prometas disponibilidad equivalente a la API oficial. Para un SaaS comercial estable, evalúa migrar a WhatsApp Cloud API de Meta.

## Instalación Windows / PowerShell

### 1. Haz una copia de seguridad
Copia tu carpeta de proyecto actual. Conserva tu `.env` y tu base de datos existentes. Este ZIP no incluye el `.env`, bases de datos ni comprobantes privados.

### 2. Instala/actualiza las tablas Flask
En la raíz del proyecto y con el entorno virtual activo:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
```

No borres PostgreSQL ni edites `alembic_version` manualmente. La migración nueva crea solo las tablas de la conexión QR.

### 3. Configura secretos
Genera un secreto aleatorio largo. En la raíz, agrega al `.env` existente (no lo reemplaces):

```env
QR_WHATSAPP_SERVICE_URL=http://127.0.0.1:3010
QR_WHATSAPP_API_SECRET=UN_SECRETO_LARGO_ALEATORIO
QR_WHATSAPP_TEST_MODE=true
QR_WHATSAPP_TEST_RECIPIENTS=573001234567
```

Cambia el número de ejemplo por el número de prueba autorizado. El modo de prueba bloquea los mensajes y envíos si no hay un número autorizado configurado. Introduce el número internacional del teléfono que utilizarás para las pruebas.

### 4. Inicia el servicio QR
Instala Node.js 20 o superior. Abre una segunda terminal:

```powershell
cd whatsapp_service
Copy-Item .env.example .env
notepad .env
npm install
npm start
```

En `whatsapp_service/.env`, coloca el mismo valor de `QR_WHATSAPP_API_SECRET` en `QR_WHATSAPP_API_SECRET` y `NOXTIUM_CALLBACK_SECRET`. Mantén `NOXTIUM_CALLBACK_URL=http://127.0.0.1:5000/webhooks/qr-whatsapp` para desarrollo local. No publiques el puerto 3010 en internet; el servicio escucha solo en localhost.

### 5. Inicia Flask
En una terminal diferente, desde la raíz del proyecto:

```powershell
.\.venv\Scripts\python.exe app.py
```

Inicia sesión con una cuenta cliente que tenga el servicio aprobado por administración. Abre **Conectar WhatsApp** o visita `/whatsapp/qr`, pulsa **Generar código QR** y escanéalo desde WhatsApp → Dispositivos vinculados → Vincular un dispositivo.

### 6. Configura n8n para pruebas
Agrega al `.env` de Flask el webhook de n8n que recibirá mensajes:

```env
N8N_WEBHOOK_URL=https://TU_N8N/webhook/noxtium-whatsapp
N8N_WEBHOOK_SECRET=EL_MISMO_SECRETO_CONFIGURADO_EN_N8N
```

Importa `n8n/noxtium_qr_test_workflow.json` en n8n. Antes de activarlo:
1. Cambia la URL del nodo HTTP Request a una dirección que n8n pueda alcanzar para Flask. En Docker local suele ser `http://host.docker.internal:5000/webhooks/qr-whatsapp/send`; en producción usa tu dominio HTTPS.
2. En el nodo `Validar secreto de NOXTIUM`, reemplaza `Bearer REEMPLAZAR_CON_N8N_WEBHOOK_SECRET` por el valor real `Bearer <N8N_WEBHOOK_SECRET>`.
3. En el nodo HTTP Request `Responder por WhatsApp QR`, reemplaza también el placeholder del header Authorization por el mismo secreto.
4. Para una prueba manual, pulsa **Listen for test event** en el nodo Webhook y usa la **Test URL** que muestra n8n como `N8N_WEBHOOK_URL`; el listener de prueba puede ser temporal. Para pruebas persistentes, activa el workflow y usa la **Production URL**.
5. Empieza con el workflow inactivo mientras editas los secretos y la URL; activa o escucha el webhook solo cuando estés listo para probar con el número autorizado. El flujo de ejemplo solo envía una respuesta fija de prueba, no es un agente de ventas de producción.

El endpoint de aprovisionamiento `N8N_PROVISION_WEBHOOK_URL` es independiente. El agente NO se marca como `ACTIVE` si n8n no devuelve `{"ready": true}` tras verificar la preparación real del flujo.

## Flujo esperado
1. Administración aprueba el pago.
2. El cliente completa el menú y los datos en `/crm/agente`.
3. El cliente conecta WhatsApp con QR.
4. Se prueba el flujo de n8n con el número autorizado.
5. Se revisan mensajes, menú, precios y derivación a persona.
6. Solo después se configura el webhook de aprovisionamiento y se solicita activar el agente.

## Solución de problemas
- `No se pudo iniciar la sesión`: verifica que Node esté corriendo y que ambos secretos coincidan.
- QR no aparece: mira los registros de `npm start`; cierra una sesión previa desde el panel y vuelve a generar el QR.
- Mensajes entran pero n8n no responde: confirma `N8N_WEBHOOK_URL`, `N8N_WEBHOOK_SECRET` y que el workflow esté activo.
- No hay acceso al QR: el servicio requiere suscripción activa aprobada por un administrador.
- Si ya había migraciones, ejecuta `alembic current` antes de `alembic upgrade head`.

## Seguridad
Nunca compartas `.env`, `whatsapp_service/sessions`, tokens, credenciales de n8n ni comprobantes. Para producción añade HTTPS, control de acceso al servidor, copias cifradas y un proceso de rotación de secretos.

## Administración de empresas y planes

- El panel administrativo incluye el enlace **Empresas** (`/admin/empresas`) con el plan vigente, pago más reciente y días restantes.
- Las suscripciones vencidas pasan a `EXPIRED` cuando administración consulta la lista de empresas; las consultas de acceso también rechazan suscripciones fuera de fecha.
- Administración puede cancelar una suscripción; el agente se pausa y NOXTIUM intenta cerrar la sesión QR si el servicio Node está disponible.
- Los planes iniciales se crean automáticamente si no existen: mensual COP 120.000 (30 días), trimestral COP 330.000 (90 días) y anual COP 1.200.000 (365 días). Son valores iniciales sugeridos; cambia los precios en `app/routes/portal.py` dentro de `seed_catalog()` antes de venderlos si deseas otra tarifa.
- Si una empresa solicita un plan distinto mientras tiene uno activo, se crea una solicitud pendiente. El cambio solo entra en vigor cuando el administrador aprueba el nuevo comprobante; entonces se cancela el plan anterior y comienza el plazo del nuevo.
- Después de solicitar o activar el servicio, el catálogo principal queda oculto en el panel del cliente. Puede seguir solicitando una preconsulta para otros módulos.

## Actualizar un proyecto existente sin perder datos

1. Haz copia de seguridad de toda la carpeta actual.
2. Extrae este ZIP en una carpeta nueva y copia tu `.env` actual a esa carpeta; no reemplaces el archivo con `.env.example`.
3. Confirma que `DATABASE_URL` apunta a la misma base PostgreSQL que ya usabas.
4. Activa tu entorno virtual e instala requisitos si hace falta, luego ejecuta `python -m alembic upgrade head`.
5. Arranca Flask y el servicio Node en dos terminales. La migración `0008_qr_whatsapp` agrega las tablas de la conexión QR; no borra tablas existentes.
6. No copies las carpetas `whatsapp_service/sessions` entre empresas ni compartas `.env`.
