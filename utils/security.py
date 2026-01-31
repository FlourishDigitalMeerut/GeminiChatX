import secrets
import logging
from datetime import datetime, timedelta
from passlib.context import CryptContext  # pyright: ignore[reportMissingModuleSource]
from jose import JWTError, jwt  # pyright: ignore[reportMissingModuleSource]
from config.settings import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

# ==========================
# Logging setup
# ==========================
logger = logging.getLogger(__name__)

# ==========================
# Password hashing setup
# ==========================
# Using argon2 instead of bcrypt to avoid compatibility issues
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# ==========================
# API Key Utilities
# ==========================
def generate_api_key() -> str:
    """Generate a secure API key."""
    return "aIWeBCb_" + secrets.token_hex(32)

def validate_api_key(api_key: str) -> bool:
    """Validate API key format."""
    return api_key.startswith("aIWeBCb_") and len(api_key) > 40

# ==========================
# Password Utilities
# ==========================
# ==========================
# Password Utilities
# ==========================
def get_password_hash(password: str) -> str:
    """Hash the password with argon2."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)

# ==========================
# JWT Utilities
# ==========================
def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """
    Create a JWT access token with optional expiration.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str):
    """
    Verify a JWT token and return the payload.
    Returns None if verification fails.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.error(f"JWT verification failed: {e}")
        return None
