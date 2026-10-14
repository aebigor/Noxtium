# NOXTIUM — agente de ventas y CRM por empresa

Esta versión añade el asistente de configuración del restaurante, catálogo de productos básico, contactos CRM por empresa, estados del agente, envío seguro de mensajes por WhatsApp desde Flask y migraciones Alembic. No incluye secretos, base de datos local ni `.env`.

## 1. Aplicar cambios

En la carpeta raíz del proyecto, con el entorno virtual activado:

```powershell
pip install -r requirements.txt
python -m alembic upgrade head
```

La nueva cadena termina en `0007_crm_contacts`. No borres la base de datos ni edites `alembic_version` manualmente.

## 2. Configuración `.env`

Conserva tu `.env` local existente. Agrega esta variable nueva:

```env
N8N_PROVISION_WEBHOOK_URL=
```

Esta URL debe apuntar a un webhook separado en n8n para recibir eventos `agent.configured` y `agent.activate`. El webhook de mensajes continúa siendo `N8N_WEBHOOK_URL`.

`N8N_WEBHOOK_SECRET` debe ser un secreto largo y aleatorio compartido entre Flask y n8n. En producción, usa HTTPS para ambos endpoints y limita el acceso a los webhooks.

## 3. Rutas nuevas

- `/crm/agente`: asistente para datos del restaurante, menú y reglas de venta.
- `/crm/contactos`: contactos creados desde mensajes entrantes de WhatsApp; permite buscar, etiquetar, agregar notas y moverlos entre Nuevo, Seguimiento, Venta ganada y No convertido.
- `/crm/agente/activar`: solicita la validación de activación al webhook de aprovisionamiento.
- `/crm/agente/pausar`: pausa el agente en NOXTIUM.
- `/webhooks/send-message`: endpoint autenticado para que n8n solicite el envío de un mensaje. Flask obtiene el token cifrado del restaurante y llama a Meta; el token no se entrega a n8n.

## 4. Contrato del webhook de aprovisionamiento n8n

NOXTIUM enviará JSON similar a:

```json
{
  "event": "agent.activate",
  "company_id": 17,
  "connection": {
    "waba_id": "ID_WABA",
    "phone_number_id": "ID_TELEFONO"
  },
  "agent": {
    "restaurant_name": "Restaurante Demo",
    "business_type": "Restaurante",
    "menu_items": [
      {"name": "Hamburguesa BBQ", "price_cop": 25000, "description": "Carne, queso y salsa BBQ", "available": true}
    ],
    "sales_tone": "amable"
  }
}
```

El evento `agent.configured` se envía al guardar cambios. `agent.activate` se envía al pulsar el botón de activación. **Solo responde `{"ready": true, "workflow_id": "..."}` después de verificar que el flujo real esté desplegado, activo y preparado para esa empresa.** No respondas `ready: true` como simple acuse de recibo; NOXTIUM lo interpreta como confirmación de activación.

En n8n crea y prueba dos flujos reutilizables:

### A. Flujo de mensajes (Webhook `N8N_WEBHOOK_URL`)

1. Webhook POST recibe `event=whatsapp.message`.
2. Comprueba el secreto `Authorization: Bearer ...`.
3. Usa `company.id` como ámbito obligatorio; procesa solo el `agent` que llega en ese evento.
4. Deduplica con `idempotency_key`.
5. Para mensajes de texto, consulta el menú incluido en `agent.menu_items` y genera una respuesta con IA. Instrucción clave: no inventar productos/precios, no confirmar pedidos no guardados y escalar alergias/reclamos/dudas a un humano.
6. Envía la respuesta mediante `POST https://TU-DOMINIO/webhooks/send-message` con `Authorization: Bearer N8N_WEBHOOK_SECRET` y JSON `{"company_id": 17, "to": "NUMERO_CLIENTE", "text": "RESPUESTA"}`.
7. Guarda el resultado y los errores. Si la respuesta no puede enviarse, registra el evento para reintento.

El flujo de n8n no necesita ni debe recibir el access token de WhatsApp. El backend Flask lo descifra y lo usa al llamar a Meta.

### B. Flujo de aprovisionamiento (webhook `N8N_PROVISION_WEBHOOK_URL`)

1. Valida el secreto y el evento.
2. Confirma que existe una plantilla real de agente y que los componentes/credenciales requeridos están listos.
3. Crea o actualiza la configuración por empresa usando el `company_id`; no clones credenciales de otro restaurante.
4. Ejecuta una prueba de salud/validación.
5. Para `agent.activate`, responde `{"ready": true, "workflow_id": "ID_REAL_DEL_FLUJO"}` solo después de que la activación sea real. Si falla, responde un error HTTP y un mensaje claro.

El webhook de aprovisionamiento debe usar la API de n8n desde el servidor y una clave de API almacenada como secreto si necesita crear/activar workflows. La API key nunca debe llegar al navegador ni al payload de WhatsApp.

## 5. WhatsApp / Meta

La conexión oficial de Embedded Signup requiere que tu aplicación de Meta, configuración, permisos y webhooks estén aprobados y configurados. La ruta `/webhooks/whatsapp` necesita HTTPS público y `META_APP_SECRET` para validar `X-Hub-Signature-256`. No uses tokens de prueba como credenciales globales para todos los clientes.

## 6. Pruebas manuales recomendadas

1. `python -m alembic current` y `python -m alembic upgrade head`.
2. Inicia Flask e inicia sesión con una empresa cuyo CRM esté activo.
3. Abre `/crm/agente`, registra 2 productos y guarda.
4. Comprueba que `/crm/contactos` no muestra datos de otras empresas.
5. Conecta WhatsApp de prueba y comprueba que llega el webhook de Meta.
6. Confirma que una empresa con agente pausado o suscripción inactiva no envía eventos a n8n.
7. Prueba mensajes duplicados y comprueba que n8n deduplica `idempotency_key`.
8. Comprueba que la activación falla de forma segura si `N8N_PROVISION_WEBHOOK_URL` no está configurada o n8n no devuelve `ready: true`.
9. Revisa límites de archivos y el acceso al comprobante antes de producción.

## Importante

Esta entrega prepara el lado NOXTIUM y define el contrato de integración. Para que la IA atienda realmente, todavía debes importar/crear y probar en tu instancia de n8n los dos flujos descritos, configurar el proveedor de IA y completar la configuración oficial de Meta. No se marca como activo si el webhook de aprovisionamiento no confirma la activación.
