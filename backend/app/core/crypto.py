"""AES encryption for user API keys (BYOK)."""

import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import settings


def _get_fernet() -> Fernet:
    """Derive a Fernet key from jwt_secret_key."""
    key = hashlib.sha256(settings.jwt_secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_api_key(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()
