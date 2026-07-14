from __future__ import annotations

import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken

VERSION = "v2"
LEGACY_VERSION = "v1"
NONCE_BYTES = 16
MAC_BYTES = 32


class SecretBox:
    def __init__(self, key: str) -> None:
        if not key.strip():
            msg = "SecretBox key is required."
            raise ValueError(msg)
        self._key = hashlib.sha256(key.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(self._key))

    def seal(self, value: str) -> str:
        encrypted = self._fernet.encrypt(value.encode("utf-8")).decode("ascii")
        return f"{VERSION}:{encrypted}"

    def open(self, sealed_value: str) -> str:
        if sealed_value.startswith(f"{VERSION}:"):
            return self._open_current(sealed_value)
        if sealed_value.startswith(f"{LEGACY_VERSION}:"):
            return self._open_legacy(sealed_value)
        msg = "Unsupported sealed secret version."
        raise ValueError(msg)

    def _open_current(self, sealed_value: str) -> str:
        try:
            return self._fernet.decrypt(
                sealed_value.removeprefix(f"{VERSION}:").encode("ascii")
            ).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as error:
            msg = "Sealed secret authentication failed."
            raise ValueError(msg) from error

    def _open_legacy(self, sealed_value: str) -> str:
        packed = base64.urlsafe_b64decode(
            sealed_value.removeprefix(f"{LEGACY_VERSION}:").encode("ascii")
        )
        if len(packed) < NONCE_BYTES + MAC_BYTES:
            msg = "Sealed secret payload is invalid."
            raise ValueError(msg)
        nonce = packed[:NONCE_BYTES]
        mac = packed[NONCE_BYTES : NONCE_BYTES + MAC_BYTES]
        encrypted = packed[NONCE_BYTES + MAC_BYTES :]
        expected_mac = hmac.new(self._key, nonce + encrypted, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected_mac):
            msg = "Sealed secret authentication failed."
            raise ValueError(msg)
        decrypted = _xor_bytes(encrypted, _keystream(self._key, nonce, len(encrypted)))
        return decrypted.decode("utf-8")


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < length:
        block = hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        output.extend(block)
        counter += 1
    return bytes(output[:length])


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(left_byte ^ right_byte for left_byte, right_byte in zip(left, right, strict=True))
