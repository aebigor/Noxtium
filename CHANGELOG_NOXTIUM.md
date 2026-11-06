# Cambios incluidos

- Corrección del `plan_id` enviado como texto al consultar `service_plans.id` entero.
- Migración `0006_agent_setup`: configuración por empresa del agente de ventas y su menú.
- Migración `0007_crm_contacts`: contactos CRM separados por empresa.
- Nuevo asistente `/crm/agente` para ficha del restaurante, menú, tono y reglas de venta.
- Nueva sección `/crm/contactos` con búsqueda, etiquetas, notas y estados comerciales.
- El webhook entrante guarda mensajes y crea/actualiza contactos; solo pasa mensajes a n8n si el servicio y el agente están activos.
- Endpoint autenticado `/webhooks/send-message` para que n8n solicite envíos sin recibir el token de WhatsApp.
- La activación del agente exige conexión, suscripción, menú y confirmación real `{"ready": true}` del webhook de aprovisionamiento.
- Se impide reasignar silenciosamente un mismo número de WhatsApp entre empresas.
- El ZIP de entrega excluye `.env`, bases de datos locales, cachés y ZIPs anidados.
