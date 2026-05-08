"""Fernet encryption for user BYOK API keys, with versioned KDF support.

Two key derivation versions live side-by-side during the v1→v2 migration:

* ``KDF_VERSION_V1`` (legacy) — Fernet key = SHA-256(JWT_SECRET_KEY).  This
  shares a secret with the JWT signing key, which means rotating the JWT
  secret silently invalidates every stored API key (P0-1 audit).  Kept
  here only as a read-side fallback while ``scripts/migrate_api_keys.py``
  re-encrypts existing rows.

* ``KDF_VERSION_V2`` (current) — Fernet key = ``API_KEY_ENCRYPTION_KEY``,
  an independent secret managed in env.  All new writes go through v2.

Callers should never decide which version to use — they pass through
``encrypt_api_key`` (always v2) and ``decrypt_api_key(blob, version)``
(dispatches by stored version).
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

KDF_VERSION_V1 = 1
KDF_VERSION_V2 = 2

# Default version for any user row that pre-dates the
# ``api_key_kdf_version`` column.  Migration 0130 backfills NULL → 1.
DEFAULT_KDF_VERSION = KDF_VERSION_V1


def _get_v1_fernet() -> Fernet:
    """Legacy KDF — derives from JWT secret.  Read-only after migration."""
    key = hashlib.sha256(settings.jwt_secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _get_v2_fernet() -> Fernet:
    """Current KDF — uses the standalone ``API_KEY_ENCRYPTION_KEY``."""
    # ``api_key_encryption_key`` is validated at boot in production and
    # generated on-the-fly in dev, so by the time we reach here it must
    # be a valid Fernet key.  We let any malformation surface as the
    # native cryptography exception rather than wrapping it.
    return Fernet(settings.api_key_encryption_key.encode())


def encrypt_api_key(plaintext: str) -> tuple[str, int]:
    """Encrypt ``plaintext`` with the current KDF.

    Returns ``(ciphertext, kdf_version)``.  Callers must persist *both*
    values on the user row — the version is required to decrypt later.
    """
    cipher = _get_v2_fernet().encrypt(plaintext.encode()).decode()
    return cipher, KDF_VERSION_V2


def decrypt_api_key(ciphertext: str, version: int = DEFAULT_KDF_VERSION) -> str:
    """Decrypt ``ciphertext`` produced by ``encrypt_api_key``.

    During the migration window v2 ciphertexts may briefly arrive on
    callers that defaulted to ``version=1`` (the column hasn't been
    backfilled yet).  We try the requested version first and fall back
    to the *other* version on ``InvalidToken`` so chat doesn't break
    mid-migration.  After ``migrate_api_keys`` runs everything is v2 and
    the fallback is a no-op.
    """
    if version == KDF_VERSION_V2:
        try:
            return _get_v2_fernet().decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            return _get_v1_fernet().decrypt(ciphertext.encode()).decode()
    if version == KDF_VERSION_V1:
        try:
            return _get_v1_fernet().decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            return _get_v2_fernet().decrypt(ciphertext.encode()).decode()
    raise ValueError(f"Unknown KDF version: {version!r}")
