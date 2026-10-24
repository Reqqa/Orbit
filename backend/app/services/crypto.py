"""Phone number privacy (docs/SPEC.md section 10, decision log 4).

A phone number is stored twice:
  * `phone_hmac` - a keyed HMAC, indexed, used for lookup. Keyed, not a plain hash,
    because the space of Malaysian mobile numbers is small enough to brute-force.
  * `phone_enc`  - encrypted, decrypted only when we need to send a reply.
"""

import base64
import hashlib
import hmac
import re

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

_NON_DIGITS = re.compile(r"\D")


def normalise_phone(number: str) -> str:
    """Reduce a number to digits so the same phone always hashes the same.

    '+60 12-345 6789', '012-3456789' and '60123456789' all normalise to '60123456789'.
    """
    digits = _NON_DIGITS.sub("", str(number))
    if digits.startswith("0"):
        digits = "60" + digits[1:]
    return digits


def phone_hmac(number: str) -> str:
    """Stable, keyed lookup value for a phone number."""
    key = get_settings().phone_hmac_key.encode()
    return hmac.new(key, normalise_phone(number).encode(), hashlib.sha256).hexdigest()


def _fernet() -> Fernet:
    settings = get_settings()
    key = settings.phone_enc_key.strip()
    if not key:
        # Keeps a fresh checkout runnable without key setup. Derived from the HMAC key,
        # so it is stable across restarts but is NOT a substitute for a real key.
        derived = hashlib.sha256(b"orbit-phone-enc:" + settings.phone_hmac_key.encode()).digest()
        key = base64.urlsafe_b64encode(derived).decode()
    return Fernet(key.encode())


def encrypt_phone(number: str) -> str:
    return _fernet().encrypt(normalise_phone(number).encode()).decode()


def decrypt_phone(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("phone number could not be decrypted with the current key") from exc


def mask_phone(number: str) -> str:
    """Display form: only the last four digits, per data minimisation."""
    digits = normalise_phone(number)
    return f"*******{digits[-4:]}" if len(digits) >= 4 else "*" * len(digits)
