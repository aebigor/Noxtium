NOXTIUM - revisión de carga de variables y asistente guiado

CAMBIOS:
1) whatsapp_service/server.js carga dotenv con `import 'dotenv/config';` antes de leer process.env. Esta era la causa principal: el servicio leía process.env pero no cargaba whatsapp_service/.env.
2) agent_setup.html ahora presenta la configuración en 3 pasos visuales: negocio, menú, estilo del agente. Incluye Siguiente/Anterior y Guardar configuración al final.
3) static/css/style.css incorpora estilos responsive para el asistente.

IMPORTANTE:
- Este ZIP se entrega saneado: NO incluye archivos .env reales, sesiones QR de WhatsApp, node_modules, cachés ni comprobantes de pago.
- Copia estos tres archivos a tu proyecto, reemplazando los originales:
  whatsapp_service/server.js
  templates/agent_setup.html
  static/css/style.css
- Conserva tus .env actuales. No copies secretos del .env.example.
- Después, desde C:\laragon\www\Noxtium\whatsapp_service ejecuta `npm start`.
- Si el secreto sigue sin cargarse, confirma que whatsapp_service/.env existe y que la variable está escrita exactamente `QR_WHATSAPP_API_SECRET=...` en una sola línea.
- El botón final de activación seguirá dependiendo de que WhatsApp esté conectado, el menú guardado, la suscripción activa y n8n responda ready=true. No se marca activo por una respuesta vacía.
