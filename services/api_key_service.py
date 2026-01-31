import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from sqlmodel import Session, select # pyright: ignore[reportMissingImports]
from models.database import engine
from models.api_keys import BotAPIKey, AllBotAPIKeysResponse, BotAPIKeyResponse
from fastapi import HTTPException, status
import logging

logger = logging.getLogger(__name__)

class APIKeyService:
    @staticmethod
    def generate_api_key(prefix: str = "bot") -> str:
        """Generate a secure API key with prefix"""
        return f"{prefix}_{secrets.token_urlsafe(32)}"
    
    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """Hash the API key for storage"""
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    @staticmethod
    def generate_all_bot_api_keys(user_id: str) -> AllBotAPIKeysResponse:
        """Generate ALL 3 bot-type API keys at once for a user"""
        
        with Session(engine) as session:
            # Deactivate any existing active keys for this user
            existing_keys = session.exec(
                select(BotAPIKey).where(
                    BotAPIKey.user_id == user_id,
                    BotAPIKey.is_active == True
                )
            ).all()
            
            for key in existing_keys:
                key.is_active = False
                session.add(key)
            
            # Calculate expiration (3 hours from now)
            expires_at = datetime.utcnow() + timedelta(hours=3)
            
            # Generate all 3 API keys
            bot_types = ["website", "whatsapp", "voice", "virtual_numbers"]
            key_names = {
                "website": "Website Bot API Key",
                "whatsapp": "WhatsApp Bot API Key", 
                "voice": "Voice Bot API Key",
                "virtual_numbers": "Virtual Numbers API Key"
            }
            generated_keys = {}
            
            for bot_type in bot_types:
                # Generate API key
                api_key = APIKeyService.generate_api_key(f"bot_{bot_type[:2]}")
                api_key_hash = APIKeyService.hash_api_key(api_key)
                
                # Create new API key record
                new_key = BotAPIKey(
                    user_id=user_id,
                    bot_type=bot_type,
                    key_name=key_names[bot_type],
                    api_key=api_key,
                    api_key_hash=api_key_hash,
                    expires_at=expires_at,
                    is_active=True
                )
                
                session.add(new_key)
                session.flush()  # Get the ID but don't commit yet
                
                # Store in response dict
                generated_keys[f"{bot_type}_key"] = api_key
            
            session.commit()
            
            logger.info(f"Generated all bot-type API keys for user {user_id}")
            
            return AllBotAPIKeysResponse(
                website_key=generated_keys["website_key"],
                whatsapp_key=generated_keys["whatsapp_key"],
                voice_key=generated_keys["voice_key"],
                virtual_numbers_key=generated_keys["virtual_numbers_key"],
                expires_at=expires_at
            )
    
    @staticmethod
    def validate_api_key(api_key: str, required_bot_type: str) -> Dict:
        """Validate API key and check if it matches the required bot type"""
        with Session(engine) as session:
            api_key_hash = APIKeyService.hash_api_key(api_key)
            
            # Find the API key
            key_record = session.exec(
                select(BotAPIKey).where(
                    BotAPIKey.api_key_hash == api_key_hash,
                    BotAPIKey.is_active == True
                )
            ).first()
            
            if not key_record:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid API key"
                )
            
            # Check expiration
            if key_record.expires_at < datetime.utcnow():
                key_record.is_active = False
                session.add(key_record)
                session.commit()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API key has expired"
                )
            
            # Check bot type
            if key_record.bot_type != required_bot_type:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"This API key is only valid for {key_record.bot_type} bots, not {required_bot_type}"
                )
            
            # Update last used timestamp
            key_record.last_used = datetime.utcnow()
            session.add(key_record)
            session.commit()
            
            return {
                "user_id": key_record.user_id,
                "bot_type": key_record.bot_type,
                "key_name": key_record.key_name
            }
    
    @staticmethod
    def get_user_api_keys(user_id: str) -> List[BotAPIKeyResponse]:
        """Get all API keys for a user"""
        with Session(engine) as session:
            keys = session.exec(
                select(BotAPIKey).where(
                    BotAPIKey.user_id == user_id
                ).order_by(BotAPIKey.created_at.desc())
            ).all()
            
            return [
                BotAPIKeyResponse(
                    id=key.id,
                    api_key=f"{key.api_key[:8]}...{key.api_key[-4:]}" if key.api_key else "********",
                    bot_type=key.bot_type,
                    key_name=key.key_name,
                    expires_at=key.expires_at,
                    created_at=key.created_at
                )
                for key in keys
            ]
    
    @staticmethod
    def revoke_all_user_keys(user_id: str) -> bool:
        """Revoke ALL API keys for a user"""
        with Session(engine) as session:
            keys = session.exec(
                select(BotAPIKey).where(
                    BotAPIKey.user_id == user_id,
                    BotAPIKey.is_active == True
                )
            ).all()
            
            for key in keys:
                key.is_active = False
                session.add(key)
            
            session.commit()
            
            logger.info(f"Revoked all API keys for user {user_id}")
            return True

# Global instance
api_key_service = APIKeyService()