"""AES-256-GCM encryption of stored student files (NFR-02: data encrypted at rest).

Files are sealed in place right after upload and opened through `plain()`, which
decrypts into a private temporary file for the duration of a `with` block.

Format: MAGIC | 8-byte random nonce prefix | chunks, each chunk being
    4-byte big-endian ciphertext length | AES-GCM(ciphertext + 16-byte tag)
with nonce = prefix + 4-byte chunk counter and the header plus a final-chunk flag
as associated data, so chunks cannot be reordered, dropped or truncated unnoticed.

Without STORAGE_ENCRYPTION_KEY nothing is encrypted (development); files sealed
earlier still need the key to be read.
"""

import base64
import contextlib
import os
import struct
import tempfile
from collections.abc import Iterator
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

MAGIC = b"MHKENC1\n"
CHUNK = 1024 * 1024
_LEN = struct.Struct(">I")


class EncryptionError(RuntimeError):
    pass


def _key() -> bytes | None:
    raw = get_settings().storage_encryption_key
    if not raw:
        return None
    try:
        key = base64.b64decode(raw, validate=True)
    except ValueError as exc:
        raise EncryptionError("STORAGE_ENCRYPTION_KEY must be base64") from exc
    if len(key) != 32:
        raise EncryptionError("STORAGE_ENCRYPTION_KEY must decode to 32 bytes (AES-256)")
    return key


def enabled() -> bool:
    return _key() is not None


def is_sealed(path: Path) -> bool:
    with open(path, "rb") as handle:
        return handle.read(len(MAGIC)) == MAGIC


def _aad(prefix: bytes, last: bool) -> bytes:
    return MAGIC + prefix + (b"\x01" if last else b"\x00")


def seal(path: Path) -> None:
    """Encrypt `path` in place (atomic replace). No-op without a key or if already sealed."""
    key = _key()
    if key is None or not path.exists() or is_sealed(path):
        return
    aes = AESGCM(key)
    prefix = os.urandom(8)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".seal-")
    try:
        with os.fdopen(fd, "wb") as sink, open(path, "rb") as source:
            sink.write(MAGIC + prefix)
            counter = 0
            chunk = source.read(CHUNK)
            while True:
                following = source.read(CHUNK)
                last = not following
                nonce = prefix + _LEN.pack(counter)
                sealed = aes.encrypt(nonce, chunk, _aad(prefix, last))
                sink.write(_LEN.pack(len(sealed)) + sealed)
                if last:
                    break
                chunk, counter = following, counter + 1
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _decrypt_to(source_path: Path, sink) -> None:
    key = _key()
    if key is None:
        raise EncryptionError("This file is encrypted but STORAGE_ENCRYPTION_KEY is not set")
    aes = AESGCM(key)
    with open(source_path, "rb") as source:
        source.read(len(MAGIC))
        prefix = source.read(8)
        counter = 0
        header = source.read(_LEN.size)
        while header:
            (size,) = _LEN.unpack(header)
            sealed = source.read(size)
            header = source.read(_LEN.size)
            last = not header
            try:
                sink.write(aes.decrypt(prefix + _LEN.pack(counter), sealed, _aad(prefix, last)))
            except InvalidTag as exc:
                raise EncryptionError(f"{source_path.name} is corrupted or was tampered") from exc
            counter += 1
        if counter == 0:
            raise EncryptionError(f"{source_path.name} is truncated")


@contextlib.contextmanager
def plain(path: Path | str) -> Iterator[Path]:
    """The readable file: `path` itself, or a temporary decrypted copy (deleted afterwards)."""
    path = Path(path)
    if not is_sealed(path):
        yield path
        return
    fd, tmp = tempfile.mkstemp(prefix="mihakk-", suffix=path.suffix)  # mode 0600
    try:
        with os.fdopen(fd, "wb") as sink:
            _decrypt_to(path, sink)
        yield Path(tmp)
    finally:
        Path(tmp).unlink(missing_ok=True)


def read_bytes(path: Path | str) -> bytes:
    with plain(path) as readable:
        return readable.read_bytes()
