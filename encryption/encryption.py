from cryptography.fernet import Fernet
import os

from dotenv import load_dotenv

load_dotenv()

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    raise ValueError("Не найден ENCRYPTION_KEY в .env")

fernet = Fernet(ENCRYPTION_KEY.encode())

async def encrypt_password(password: str) -> str:
    return fernet.encrypt(password.encode()).decode()

async def decrypt_password(encrypted_password: str) -> str:
    return fernet.decrypt(encrypted_password.encode()).decode()

async def encrypt_data(data: str) -> str:
    return fernet.encrypt(data.encode()).decode()

async def decrypt_data(encrypted_data: str) -> str:
    return fernet.decrypt(encrypted_data.encode()).decode()