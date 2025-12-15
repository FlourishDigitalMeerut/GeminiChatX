from fastapi import Depends, HTTPException, status, Header
from jose import JWTError, jwt # pyright: ignore[reportMissingModuleSource]
from config.settings import SECRET_KEY, ALGORITHM
from services.mongodb import get_users_collection
from utils.security import verify_password
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

async def get_current_user(authorization: str = Header(None)):
    """
    Get current user from JWT token
    Accepts both 'Authorization' and 'authorization' header names
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"}
    )
    
    # Check if authorization header exists
    if not authorization:
        logger.error("Missing Authorization header")
        raise credentials_exception
    
    try:
        # Extract token from "Bearer <token>" format
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logger.error(f"Invalid Authorization header format: {authorization}")
            raise credentials_exception
            
        token = parts[1]
        
        # Decode JWT token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        
        if email is None:
            logger.error("No email in token payload")
            raise credentials_exception
            
    except JWTError as e:
        logger.error(f"JWT token error: {e}")
        raise credentials_exception
    except Exception as e:
        logger.error(f"Unexpected error in token validation: {e}")
        raise credentials_exception
    
    # Get user from database
    users_collection = await get_users_collection()
    user = await users_collection.find_one({"email": email})
    
    if user is None:
        logger.error(f"User not found for email: {email}")
        raise credentials_exception
        
    return user

async def authenticate_user(email: str, password: str):
    users_collection = await get_users_collection()
    user = await users_collection.find_one({"email": email})
    if not user or not verify_password(password, user.get('hashed_password', '')):
        return False
    return user