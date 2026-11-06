import requests
from flask import current_app


class N8NService:
    def send_whatsapp_event(self, payload: dict):
        url = current_app.config.get("N8N_WEBHOOK_URL")
        if not url:
            current_app.logger.warning("N8N_WEBHOOK_URL no está configurada.")
            return None

        headers = {
            "Content-Type": "application/json",
            "X-Noxtium-Event": "whatsapp.message",
        }

        secret = current_app.config.get("N8N_WEBHOOK_SECRET")
        if secret:
            headers["Authorization"] = f"Bearer {secret}"

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        return response
