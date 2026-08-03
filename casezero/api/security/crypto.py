"""Application-level field encryption, on top of Supabase's at-rest encryption.

The spec asks for "encryption at rest and in transit". Supabase already provides
both, so doing only that would be a checkbox. NRICs and account numbers are
additionally encrypted with a key the database never sees, which means a database
dump alone does not expose a single identity document number.

Masking is separate and always available: the UI shows `880412-14-****` without
ever needing the key, so the common case requires no decryption at all.
"""

from __future__ import annotations

import re
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from api.config import get_settings

NRIC_PATTERN = re.compile(r"\b(\d{6})-?(\d{2})-?(\d{4})\b")
ACCOUNT_PATTERN = re.compile(r"\b(\d{9,16})\b")


class CryptoError(RuntimeError):
    pass


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    if not settings.fernet_key:
        raise CryptoError(
            "FERNET_KEY is not set. Generate one with:\n"
            '  python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(settings.fernet_key.encode())
    except Exception as exc:  # noqa: BLE001
        raise CryptoError(f"FERNET_KEY is not a valid Fernet key: {exc}") from exc


def encrypt(plaintext: str | None) -> str | None:
    if plaintext is None or plaintext == "":
        return None
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise CryptoError(
            "Could not decrypt. The FERNET_KEY has changed since this row was written."
        ) from exc


# ─── Masking ────────────────────────────────────────────────────────────────


def mask_nric(nric: str | None) -> str:
    """880412-14-5521 -> 880412-14-****

    Birth date and state code stay visible because an investigator legitimately
    needs them; the unique serial is what gets hidden.
    """
    if not nric:
        return "—"
    match = NRIC_PATTERN.search(nric)
    if not match:
        return "****"
    return f"{match.group(1)}-{match.group(2)}-****"


def mask_account(account_no: str | None) -> str:
    """7142556890 -> ******6890"""
    if not account_no:
        return "—"
    digits = re.sub(r"\D", "", account_no)
    if len(digits) <= 4:
        return "*" * len(digits)
    return "*" * (len(digits) - 4) + digits[-4:]


def last4(value: str | None) -> str:
    if not value:
        return ""
    digits = re.sub(r"\D", "", value)
    return digits[-4:]


def redact_pii(text: str) -> str:
    """Strip identifiers before text is sent to a model or written to a log.

    Applied to prompt payloads so a customer's NRIC is never transmitted to an
    external provider — the classifier does not need it to do its job.
    """
    text = NRIC_PATTERN.sub(lambda m: f"{m.group(1)}-{m.group(2)}-****", text)
    return ACCOUNT_PATTERN.sub(lambda m: mask_account(m.group(1)), text)
