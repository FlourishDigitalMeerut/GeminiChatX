from sqlmodel import SQLModel, Field # pyright: ignore[reportMissingImports]
from datetime import datetime, timedelta
from typing import Optional, List
import secrets
import uuid

class BotAPIKeyBase(SQLModel):
    """Base model for bot API keys"""
    user_id: str = Field(index=True)  # MongoDB user ID
    bot_type: str = Field(index=True)  # 'website', 'whatsapp', 'voice'
    key_name: str = Field(default="Default API Key")
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(hours=3))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used: Optional[datetime] = None
    is_active: bool = Field(default=True)

class BotAPIKey(BotAPIKeyBase, table=True):
    """Database model for storing API keys"""
    id: Optional[int] = Field(default=None, primary_key=True)
    api_key: str = Field(index=True, unique=True)
    api_key_hash: str = Field(index=True)
    
# NEW: Response model for generating all keys at once
class AllBotAPIKeysResponse(SQLModel):
    """Response model for generating all bot-type API keys"""
    website_key: str
    whatsapp_key: str
    voice_key: str
    virtual_numbers_key: str
    expires_at: datetime
    
class BotAPIKeyResponse(SQLModel):
    """Response model for single API key"""
    id: int
    api_key: str
    bot_type: str
    key_name: str
    expires_at: datetime
    created_at: datetime