import hashlib
import hmac
import os
import secrets

from pwdlib import PasswordHash


password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(
        plain_password: str,
        hashed_password: str
    ) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Hash a session token for storage.

    Only the hash is stored in the database. A leaked database
    therefore does not by itself give a usable Bearer token: the
    hash is not accepted as a token, and the original token is
    256 bits of randomness.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- Broadcast signing (Phase 3) ---
#
# Broadcasts are signed by the server with HMAC-SHA256 so a stored
# broadcast can be checked for tampering through the verify
# endpoint. This is server-side tamper evidence, not public-key
# verification: anyone who holds the signing key can sign, and
# clients verify through the server, not independently. See
# docs/SECURITY.md for the honest limits of this design.
_EPHEMERAL_SIGNING_KEY = None


def get_signing_key() -> bytes:
    """Return the broadcast signing key.

    Prefer NIRAPODNET_SIGNING_KEY from the environment: with an
    ephemeral key, signatures made before a restart cannot be
    verified after it. The environment key is the production path.
    """
    global _EPHEMERAL_SIGNING_KEY

    env_key = os.environ.get("NIRAPODNET_SIGNING_KEY", "").strip()

    if env_key:
        return env_key.encode("utf-8")

    if _EPHEMERAL_SIGNING_KEY is None:
        _EPHEMERAL_SIGNING_KEY = secrets.token_bytes(32)

    return _EPHEMERAL_SIGNING_KEY


def broadcast_canonical_string(
    broadcast_id: int,
    issued_by: int,
    broadcast_type: str,
    message: str,
    priority: str,
    created_at_iso: str,
) -> str:
    return "|".join([
        str(broadcast_id),
        str(issued_by),
        broadcast_type,
        message,
        priority,
        created_at_iso,
    ])


def sign_broadcast(canonical: str) -> str:
    return hmac.new(
        get_signing_key(),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_broadcast_signature(
    canonical: str,
    signature: str | None,
) -> bool:
    if not signature:
        return False

    expected = sign_broadcast(canonical)

    return hmac.compare_digest(expected, signature)


def contains_control_characters(value: str) -> bool:
    """True if value has control characters other than tab/newline.

    Tab, LF and CR are allowed in free text; NUL and every other
    C0/C1 control character are rejected at the schema layer.
    """
    for char in value:
        code = ord(char)

        if code < 32 and char not in ("\t", "\n", "\r"):
            return True

        if 127 <= code <= 159:
            return True

    return False
