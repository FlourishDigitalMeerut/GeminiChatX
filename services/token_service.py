from datetime import datetime, timedelta
from config.settings import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS
from utils.security import create_access_token
from services.mongodb import get_refresh_tokens_collection
from bson import ObjectId
import secrets
import logging

logger = logging.getLogger(__name__)

class TokenService:
    
    @staticmethod
    async def create_tokens_for_user(user: dict):
        """Create access and refresh tokens for user"""
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user["email"]}, 
            expires_delta=access_token_expires
        )
        
        # Create refresh token
        refresh_token = secrets.token_urlsafe(32)
        refresh_token_expires = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
        # Store refresh token in database
        refresh_tokens_collection = await get_refresh_tokens_collection()
        await refresh_tokens_collection.insert_one({
            "user_id": user["_id"],
            "refresh_token": refresh_token,
            "expires_at": refresh_token_expires,
            "created_at": datetime.utcnow()
        })
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
    
    @staticmethod
    async def refresh_access_token(refresh_token: str):
        """Refresh access token using refresh token"""
        refresh_tokens_collection = await get_refresh_tokens_collection()
        
        # Find valid refresh token
        token_doc = await refresh_tokens_collection.find_one({
            "refresh_token": refresh_token,
            "expires_at": {"$gt": datetime.utcnow()}
        })
        
        if not token_doc:
            raise ValueError("Invalid or expired refresh token")
        
        # Get user data
        from services.mongodb import get_users_collection
        users_collection = await get_users_collection()
        user = await users_collection.find_one({"_id": token_doc["user_id"]})
        
        if not user:
            raise ValueError("User not found")
        
        # Create new access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user["email"]}, 
            expires_delta=access_token_expires
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
    
    @staticmethod
    async def revoke_refresh_token(refresh_token: str):
        """Revoke a specific refresh token"""
        refresh_tokens_collection = await get_refresh_tokens_collection()
        await refresh_tokens_collection.delete_one({"refresh_token": refresh_token})
    
    @staticmethod
    async def revoke_all_user_tokens(user_id: str):
        """Revoke all refresh tokens for a user"""
        refresh_tokens_collection = await get_refresh_tokens_collection()
        await refresh_tokens_collection.delete_many({"user_id": ObjectId(user_id)})