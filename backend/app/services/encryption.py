"""pgcrypto PII Encryption Helpers — phone, email, address column encryption.

Uses PostgreSQL pgcrypto extension (pgp_sym_encrypt / pgp_sym_decrypt) via raw SQL
to keep encryption at the database layer. Compatible with the existing phone_enc/email_enc
BYTEA columns on the patients table.

Usage:
    from app.services.encryption import encrypt_value, decrypt_value, EncryptionService

    # Encrypt before storing
    ciphertext = await encrypt_value(db, "+91-9876543210", "patient-phone")

    # Decrypt when reading
    plaintext = await decrypt_value(db, ciphertext, "patient-phone")

Or use the service class for context-managed operations across multiple fields.

Key Management:
    The encryption passphrase comes from settings.ENCRYPTION_KEY. In production,
    rotate the key periodically. Old data remains decryptable with the old key
    until re-encrypted (pgp_sym_decrypt takes the passphrase, not a key ID).
"""

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

# ─── Column-level context tags for audit ───
ENCRYPTION_CONTEXTS = {
    "patient-phone": "patients.phone_enc",
    "patient-email": "patients.email_enc",
    "patient-address": "patients.address_enc",  # future column
}


async def encrypt_value(
    db: AsyncSession,
    plaintext: str,
    context: str,
    key: Optional[str] = None,
) -> bytes:
    """Encrypt a plaintext value using pgp_sym_encrypt.

    Args:
        db: Active database session.
        plaintext: The value to encrypt (phone, email, address, etc.).
        context: A label for audit purposes (e.g. "patient-phone").
        key: Optional encryption passphrase. Defaults to settings.ENCRYPTION_KEY.

    Returns:
        Encrypted bytes (pgp_sym_encrypt output, store in BYTEA column).

    Raises:
        ValueError: If no encryption key is configured.
        RuntimeError: If the pgcrypto extension is unavailable.
    """
    passphrase = key or settings.ENCRYPTION_KEY
    if not passphrase:
        raise ValueError("ENCRYPTION_KEY not configured. Set it in .env or environment variables.")

    try:
        result = await db.execute(
            text("SELECT pgp_sym_encrypt(:plaintext, :key)"),
            {"plaintext": plaintext, "key": passphrase},
        )
        ciphertext = result.scalar_one()
        logger.debug("Encrypted %s (%d chars → %d bytes)", context, len(plaintext), len(ciphertext))
        return ciphertext
    except Exception as exc:
        error_msg = str(exc)
        if "pgcrypto" in error_msg or "does not exist" in error_msg:
            raise RuntimeError(
                "pgcrypto extension not available. Run: CREATE EXTENSION IF NOT EXISTS pgcrypto;"
            ) from exc
        logger.error("Encryption failed for %s: %s", context, error_msg)
        raise


async def decrypt_value(
    db: AsyncSession,
    ciphertext: bytes,
    context: str,
    key: Optional[str] = None,
) -> str:
    """Decrypt a pgp_sym_encrypt ciphertext back to plaintext.

    Args:
        db: Active database session.
        ciphertext: Encrypted bytes from the BYTEA column.
        context: A label for audit purposes (e.g. "patient-phone").
        key: Optional encryption passphrase. Defaults to settings.ENCRYPTION_KEY.

    Returns:
        Decrypted plaintext string.

    Raises:
        ValueError: If no encryption key is configured, or ciphertext is empty.
        RuntimeError: If decryption fails (wrong key or corrupted data).
    """
    if not ciphertext:
        raise ValueError(f"Cannot decrypt empty ciphertext for {context}")

    passphrase = key or settings.ENCRYPTION_KEY
    if not passphrase:
        raise ValueError("ENCRYPTION_KEY not configured. Set it in .env or environment variables.")

    try:
        result = await db.execute(
            text("SELECT pgp_sym_decrypt(:ciphertext, :key)"),
            {"ciphertext": ciphertext, "key": passphrase},
        )
        plaintext = result.scalar_one()
        logger.debug("Decrypted %s successfully", context)
        return plaintext
    except Exception as exc:
        error_msg = str(exc)
        if "Wrong key" in error_msg or "decrypt" in error_msg.lower():
            raise RuntimeError(
                f"Decryption failed for {context}: wrong key or corrupted data. "
                "Verify ENCRYPTION_KEY matches the key used at encryption time."
            ) from exc
        logger.error("Decryption failed for %s: %s", context, error_msg)
        raise


class EncryptionService:
    """High-level encryption service for patient PII fields.

    Handles the common pattern of encrypting/decrypting phone, email,
    and address columns with automatic context tagging and audit readiness.
    """

    def __init__(self, db: AsyncSession, key: Optional[str] = None):
        self.db = db
        self.key = key or settings.ENCRYPTION_KEY

    # ─── Encrypt Helpers ───

    async def encrypt_phone(self, phone: str) -> bytes:
        return await encrypt_value(self.db, phone, "patient-phone", self.key)

    async def encrypt_email(self, email: str) -> bytes:
        return await encrypt_value(self.db, email, "patient-email", self.key)

    async def encrypt_address(self, address: str) -> bytes:
        return await encrypt_value(self.db, address, "patient-address", self.key)

    # ─── Decrypt Helpers ───

    async def decrypt_phone(self, ciphertext: bytes) -> str:
        return await decrypt_value(self.db, ciphertext, "patient-phone", self.key)

    async def decrypt_email(self, ciphertext: bytes) -> str:
        return await decrypt_value(self.db, ciphertext, "patient-email", self.key)

    async def decrypt_address(self, ciphertext: bytes) -> str:
        return await decrypt_value(self.db, ciphertext, "patient-address", self.key)

    # ─── Batch Operations ───

    async def encrypt_patient_pii(
        self,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
    ) -> dict:
        """Encrypt multiple PII fields in one call.

        Returns a dict with only the fields that were provided:
            {"phone_enc": bytes, "email_enc": bytes, "address_enc": bytes}
        """
        result = {}
        if phone:
            result["phone_enc"] = await self.encrypt_phone(phone)
        if email:
            result["email_enc"] = await self.encrypt_email(email)
        if address:
            result["address_enc"] = await self.encrypt_address(address)
        return result

    async def decrypt_patient_pii(
        self,
        phone_enc: Optional[bytes] = None,
        email_enc: Optional[bytes] = None,
        address_enc: Optional[bytes] = None,
    ) -> dict:
        """Decrypt multiple PII fields in one call.

        Returns a dict with only the fields that were provided:
            {"phone": str, "email": str, "address": str}
        """
        result = {}
        if phone_enc:
            result["phone"] = await self.decrypt_phone(phone_enc)
        if email_enc:
            result["email"] = await self.decrypt_email(email_enc)
        if address_enc:
            result["address"] = await self.decrypt_address(address_enc)
        return result

    # ─── Health ───

    async def verify_pgcrypto(self) -> bool:
        """Verify the pgcrypto extension is available and the key works."""
        try:
            test_text = "pgcrypto-health-check"
            encrypted = await encrypt_value(self.db, test_text, "health-check", self.key)
            decrypted = await decrypt_value(self.db, encrypted, "health-check", self.key)
            return decrypted == test_text
        except Exception as exc:
            logger.error("pgcrypto health check failed: %s", exc)
            return False
