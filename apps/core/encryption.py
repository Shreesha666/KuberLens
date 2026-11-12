from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def get_fernet_cipher() -> Fernet:
    key = getattr(settings, "FIELD_ENCRYPTION_KEY", None)
    if not key:
        raise ValueError(
            "FIELD_ENCRYPTION_KEY is not configured in settings. "
            "Please provide a valid 32-byte base64-encoded key."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)

def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string using Fernet authenticated symmetric encryption."""
    if not plaintext:
        return ""
    cipher = get_fernet_cipher()
    encrypted_bytes = cipher.encrypt(plaintext.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")

def decrypt_value(ciphertext: str) -> str:
    """Decrypt a ciphertext string back to plaintext."""
    if not ciphertext:
        return ""
    cipher = get_fernet_cipher()
    try:
        decrypted_bytes = cipher.decrypt(ciphertext.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Invalid or corrupted ciphertext, unable to decrypt.") from exc
