import requests
from flask import current_app


class MetaAPIError(Exception):
    pass


class MetaService:
    @property
    def version(self):
        return current_app.config["META_GRAPH_VERSION"]

    @property
    def base_url(self):
        return f"https://graph.facebook.com/{self.version}"

    def _request(self, method, path, **kwargs):
        response = requests.request(
            method,
            f"{self.base_url}/{path.lstrip('/')}",
            timeout=30,
            **kwargs,
        )
        if not response.ok:
            raise MetaAPIError(
                f"Meta API {response.status_code}: {response.text}"
            )
        return response.json()

    def exchange_code(self, code: str) -> dict:
        return self._request(
            "GET",
            "/oauth/access_token",
            params={
                "client_id": current_app.config["META_APP_ID"],
                "client_secret": current_app.config["META_APP_SECRET"],
                "code": code,
            },
        )

    def debug_token(self, access_token: str) -> dict:
        app_id = current_app.config["META_APP_ID"]
        app_secret = current_app.config["META_APP_SECRET"]

        return self._request(
            "GET",
            "/debug_token",
            params={"input_token": access_token},
            headers={
                "Authorization": f"Bearer {app_id}|{app_secret}",
            },
        )

    def get_phone_number(self, phone_number_id: str, access_token: str) -> dict:
        return self._request(
            "GET",
            f"/{phone_number_id}",
            params={
                "fields": "id,display_phone_number,verified_name",
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )

    def subscribe_waba(self, waba_id: str, access_token: str) -> dict:
        return self._request(
            "POST",
            f"/{waba_id}/subscribed_apps",
            headers={"Authorization": f"Bearer {access_token}"},
        )
