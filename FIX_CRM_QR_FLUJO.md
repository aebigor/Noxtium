# NOXTIUM — Corrección CRM y flujo QR

Este parche corrige el registro repetido de contactos y el recorrido del cliente después de vincular WhatsApp.

## Cambios incluidos

- El webhook QR registra mensajes de forma idempotente en PostgreSQL y crea/actualiza el contacto con `ON CONFLICT`, respetando `uq_crm_contacts_company_phone`.
- Los eventos repetidos de WhatsApp ya no deben crear contactos ni mensajes duplicados.
- Se guarda el nombre de perfil de WhatsApp cuando Baileys lo proporciona.
- Al detectar la conexión QR, la pantalla redirige a `/crm/agente` para configurar restaurante, menú y reglas.
- Al guardar la configuración, el cliente vuelve a `/dashboard`.
- El dashboard muestra los últimos mensajes y el resumen de contactos por estado, con enlaces al seguimiento CRM y a las pruebas del agente.
- La pantalla QR conserva un modo de administración accesible desde el dashboard mediante `?manage=1`.

## Cómo aplicarlo en Windows

1. Detén Flask y el servicio Node con `Ctrl+C` en sus terminales.
2. Haz una copia de seguridad de estos archivos de tu proyecto actual:
   - `app/routes/qr_whatsapp.py`
   - `app/routes/portal.py`
   - `templates/dashboard.html`
   - `templates/whatsapp_qr.html`
   - `whatsapp_service/server.js`
3. Extrae este ZIP sobre `C:\laragon\www\Noxtium`, conservando tu `.env`, PostgreSQL y la carpeta `whatsapp_service/sessions`.
4. No hace falta una migración nueva: este parche no cambia el esquema de la base de datos.
5. En una terminal, inicia Flask desde la raíz del proyecto usando el comando que ya utilizas.
6. En otra terminal, entra a `C:\laragon\www\Noxtium\whatsapp_service` y ejecuta `npm start`.
7. Prueba primero con el número autorizado de `QR_WHATSAPP_TEST_RECIPIENTS`. Comprueba que Flask responda `200` a `POST /webhooks/qr-whatsapp` y que los mensajes aparezcan en el dashboard.

## Importante

Este paquete no contiene `.env`, contraseñas, secretos ni credenciales de WhatsApp. No reemplaces tu `.env` ni borres las sesiones guardadas. El envío a n8n sigue dependiendo de `N8N_WEBHOOK_URL` y de un workflow publicado/configurado; esta corrección deja estable el registro CRM y el recorrido de configuración.
