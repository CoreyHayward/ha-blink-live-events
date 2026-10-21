from __future__ import annotations

import base64
import os
from typing import Optional, Tuple

try:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
except Exception:  # pragma: no cover
    ec = None  # type: ignore
    serialization = None  # type: ignore


def create_keys() -> Tuple[object, object, bytes]:
    if ec is None:
        raise RuntimeError("cryptography package is required for key generation: pip install cryptography")
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    auth_secret = os.urandom(16)
    return private_key, public_key, auth_secret


def encode_private_key_der_b64(priv) -> str:
    if serialization is None:
        raise RuntimeError("cryptography package is required: pip install cryptography")
    der = priv.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.b64encode(der).decode()


def decode_private_key_der_b64(s: str):
    if serialization is None:
        raise RuntimeError("cryptography package is required: pip install cryptography")
    der = base64.b64decode(s)
    return serialization.load_der_private_key(der, password=None)


def public_key_bytes_uncompressed(pub) -> bytes:
    if serialization is None:
        raise RuntimeError("cryptography package is required: pip install cryptography")
    return pub.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )


def b64url_no_pad(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def decrypt_message_webpush(crypto_key: bytes, encryption_salt: bytes, raw_data: bytes, auth_secret: bytes, private_key) -> bytes:
    # Prefer http_ece if available; it implements RFC 8291 derivation correctly
    try:
        import http_ece  # type: ignore

        return http_ece.decrypt(
            raw_data,
            salt=encryption_salt,
            dh=crypto_key,
            private_key=private_key,
            auth_secret=auth_secret,
            version="aesgcm",
        )
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "Decryption requires http_ece (or implement ECE manually). Install with: pip install http_ece"
        ) from e

