from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

VERSION = "v2"


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
        if not sealed_value.startswith(f"{VERSION}:"):
            msg = "Unsupported sealed secret version."
            raise ValueError(msg)
        try:
            return self._fernet.decrypt(
                sealed_value.removeprefix(f"{VERSION}:").encode("ascii")
            ).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as error:
            msg = "Sealed secret authentication failed."
            raise ValueError(msg) from error
