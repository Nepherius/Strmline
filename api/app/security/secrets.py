from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

VERSION = "v1"
NONCE_BYTES = 16
MAC_BYTES = 32


class SecretBox:
    def __init__(self, key: str) -> None:
        if not key.strip():
            msg = "SecretBox key is required."
            raise ValueError(msg)
        self._key = hashlib.sha256(key.encode("utf-8")).digest()

    def seal(self, value: str) -> str:
        nonce = secrets.token_bytes(NONCE_BYTES)
        payload = value.encode("utf-8")
        encrypted = _xor_bytes(payload, _keystream(self._key, nonce, len(payload)))
        mac = hmac.new(self._key, nonce + encrypted, hashlib.sha256).digest()
        packed = nonce + mac + encrypted
        encoded = base64.urlsafe_b64encode(packed).decode("ascii")
        return f"{VERSION}:{encoded}"

    def open(self, sealed_value: str) -> str:
        prefix = f"{VERSION}:"
        if not sealed_value.startswith(prefix):
            msg = "Unsupported sealed secret version."
            raise ValueError(msg)
        packed = base64.urlsafe_b64decode(sealed_value.removeprefix(prefix).encode("ascii"))
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
