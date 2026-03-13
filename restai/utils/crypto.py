import hashlib

from cryptography.fernet import Fernet, InvalidToken

from restai import config

# Load encryption key from dedicated Fernet environment variable
FERNET_KEY = config.RESTAI_FERNET_KEY
if not FERNET_KEY:
    raise RuntimeError("RESTAI_FERNET_KEY environment variable not set.")

fernet = Fernet(FERNET_KEY)

def encrypt_api_key(api_key: str) -> str:
    return fernet.encrypt(api_key.encode()).decode()

def decrypt_api_key(token: str) -> str:
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        raise ValueError("Invalid API key token or decryption failed.")

def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()
