"""
Шифрование чувствительных данных (пароли, cookies) через Fernet.

Ключ берётся из ENCRYPTION_KEY в .env.
"""

import os

from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    raise ValueError("Не найден ENCRYPTION_KEY в .env")

# Глобальный экземпляр шифра, используется всеми storage-функциями
fernet = Fernet(ENCRYPTION_KEY.encode())


async def encrypt_data(data: str) -> str:
    """Шифрует строку и возвращает текст в base64."""
    return fernet.encrypt(data.encode()).decode()


async def decrypt_data(encrypted_data: str) -> str:
    """Дешифрует текст, полученный от encrypt_data, и возвращает исходную строку."""
    return fernet.decrypt(encrypted_data.encode()).decode()