from cryptography.fernet import Fernet
from flask import current_app


def _fernet():
    key = current_app.config.get("FERNET_KEY")
    if not key:
        raise RuntimeError(
            "FERNET_KEY no está configurada. "
            "Genera una clave Fernet y colócala en .env."
        )
    return Fernet(key.encode())


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    return _fernet().decrypt(encrypted_token.encode()).decode()
