"""
Decrypt tokens stored by TeslaMate using cloak_ecto AES.GCM.256.

Binary layout of the bytea column value:
  byte 0         : version tag (0x01 = AES.GCM.256)
  byte 1         : key-tag length N
  bytes 2..2+N   : key-tag value (ignored here — single-key setup)
  bytes 2+N..+12 : IV / nonce (12 bytes)
  bytes +12..+28 : auth tag (16 bytes)
  bytes +28..end : ciphertext

AAD: b"AES256GCM"
Key: SHA-256(ENCRYPTION_KEY encoded as UTF-8)
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

_AAD = b"AES256GCM"
_IV_LEN = 12
_TAG_LEN = 16


def _derive_key_utf8(encryption_key: str) -> bytes:
    return hashlib.sha256(encryption_key.encode("utf-8")).digest()


def _derive_key_b64(encryption_key: str) -> bytes:
    return hashlib.sha256(base64.b64decode(encryption_key)).digest()


def _decrypt(cipherblob: bytes, key: bytes) -> str:
    _version = cipherblob[0]
    tag_len = cipherblob[1]
    offset = 2 + tag_len
    iv = cipherblob[offset: offset + _IV_LEN]
    auth_tag = cipherblob[offset + _IV_LEN: offset + _IV_LEN + _TAG_LEN]
    ciphertext = cipherblob[offset + _IV_LEN + _TAG_LEN:]
    aesgcm = AESGCM(key)
    # cryptography expects ciphertext || tag concatenated
    plaintext = aesgcm.decrypt(iv, ciphertext + auth_tag, _AAD)
    return plaintext.decode("utf-8")


def decrypt_token(cipherblob: bytes, encryption_key: str) -> str:
    """Decrypt a single token bytea value from TeslaMate's private.tokens table."""
    if isinstance(cipherblob, memoryview):
        cipherblob = bytes(cipherblob)

    # Try UTF-8 key derivation first (most common TeslaMate setup)
    try:
        token = _decrypt(cipherblob, _derive_key_utf8(encryption_key))
        logger.debug("Token decrypted using UTF-8 key derivation")
        return token
    except Exception:
        pass

    # Fall back to base64-decoded key derivation
    try:
        token = _decrypt(cipherblob, _derive_key_b64(encryption_key))
        logger.info("Token decrypted using base64-decoded key derivation")
        return token
    except Exception:
        pass

    raise ValueError(
        "Token decryption failed with both key derivation variants. "
        "Verify that ENCRYPTION_KEY matches the value set in TeslaMate."
    )
