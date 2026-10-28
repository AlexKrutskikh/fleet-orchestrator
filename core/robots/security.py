import hashlib
import secrets


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str]:
    """Возвращает (ключ, хэш). Ключ показывается один раз, в базе хранится только хэш."""
    raw_key = secrets.token_urlsafe(32)
    return raw_key, hash_api_key(raw_key)