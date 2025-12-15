from fastapi import HTTPException, Header, status, Depends
from pydantic import BaseModel
from services.mongodb import get_users_collection
from sqlmodel import Session, select # pyright: ignore[reportMissingImports]
from models.database import engine
from models.website_bot import WebsiteBotMeta
from models.whatsapp_bot import WhatsAppBotMeta
from models.voice_bot import VoiceBotMeta
from managers.website_bot_manager import website_bot_manager  # Import the instances
from managers.whatsapp_bot_manager import whatsapp_bot_manager
from typing import Optional
from services.api_key_service import api_key_service
# from managers.voice_bot_manager import voice_bot_manager

class APIKeyVerification(BaseModel):
    bot_id: int
    api_key: str

def get_website_bot(bot_id: int):
    bot = website_bot_manager.get(bot_id)  # Use the instance
    if not bot:
        raise HTTPException(404, "Website Bot not found")
    return bot

def get_whatsapp_bot(bot_id: int):
    bot = whatsapp_bot_manager.get(bot_id)  # Use the instance
    if not bot:
        raise HTTPException(404, "WhatsApp Bot not found")
    return bot

def verify_api_key(bot_id: int, authorization: str = Header(None), api_key: str = Header(None)):
    """
    Verify API key from either:
    - Authorization: Bearer <api_key> header (standard)
    - api-key: <api_key> header (legacy support)
    """
    # Extract API key from Authorization header if provided
    if authorization and authorization.startswith("Bearer "):
        api_key_value = authorization.replace("Bearer ", "").strip()
    # Use api-key header if provided
    elif api_key:
        api_key_value = api_key
    else:
        raise HTTPException(401, "Missing API key. Use either 'Authorization: Bearer <api_key>' or 'api-key: <api_key>' header")
    
    # Get the bot and verify the API key
    bot = get_website_bot(bot_id)
    if not bot.meta.api_key == api_key_value:
        raise HTTPException(401, "Invalid API key")
    
    return bot

# Add to existing dependencies
# def get_voice_bot(bot_id: int):
#     bot = voice_bot_manager.get(bot_id)
#     if not bot:
#         raise HTTPException(404, "Voice Bot not found")
#     return bot

# def verify_voice_api_key(authorization: str = Header(None), api_key: str = Header(None)):
#     """Verify API key for voice bots"""
#     if authorization and authorization.startswith("Bearer "):
#         api_key_value = authorization.replace("Bearer ", "").strip()
#     elif api_key:
#         api_key_value = api_key
#     else:
#         raise HTTPException(401, "Missing API key")
    
#     bot = voice_bot_manager.get_by_api_key(api_key_value)
#     if not bot:
#         raise HTTPException(401, "Invalid API key")
    
#     return bot

async def validate_website_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
    """Validate API key for website bots"""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Website API key required. Please provide X-API-Key header"
        )
    
    return api_key_service.validate_api_key(x_api_key, "website")

async def validate_whatsapp_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
    """Validate API key for WhatsApp bots"""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="WhatsApp API key required. Please provide X-API-Key header"
        )
    
    return api_key_service.validate_api_key(x_api_key, "whatsapp")

async def validate_voice_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
    """Validate API key for voice bots"""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Voice API key required. Please provide X-API-Key header"
        )
    
    return api_key_service.validate_api_key(x_api_key, "voice")

async def get_current_user_from_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
    """Get user information from API key (without bot type restriction)"""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required"
        )
    
    # Check if it's a bot-type API key
    try:
        # Try to validate as website key
        result = api_key_service.validate_api_key(x_api_key, "website")
        return result
    except HTTPException:
        pass
    
    try:
        # Try to validate as WhatsApp key
        result = api_key_service.validate_api_key(x_api_key, "whatsapp")
        return result
    except HTTPException:
        pass
    
    try:
        # Try to validate as voice key
        result = api_key_service.validate_api_key(x_api_key, "voice")
        return result
    except HTTPException:
        pass

    try:
        # Try to validate as virtual numbers key
        result = api_key_service.validate_api_key(x_api_key, "virtual_numbers")
        return result
    except HTTPException:
        pass
    
    # Check website bots
    with Session(engine) as session:
        website_bot = session.exec(
            select(WebsiteBotMeta).where(WebsiteBotMeta.api_key == x_api_key)
        ).first()
        if website_bot:
            return {"user_id": website_bot.owner, "bot_type": "website", "bot_id": website_bot.id}
    
    # Check WhatsApp bots
    with Session(engine) as session:
        whatsapp_bot = session.exec(
            select(WhatsAppBotMeta).where(WhatsAppBotMeta.access_token == x_api_key)
        ).first()
        if whatsapp_bot:
            return {"user_id": whatsapp_bot.owner, "bot_type": "whatsapp", "bot_id": whatsapp_bot.id}
    
    # Check voice bots
    with Session(engine) as session:
        voice_bot = session.exec(
            select(VoiceBotMeta).where(VoiceBotMeta.api_key == x_api_key)
        ).first()
        if voice_bot:
            return {"user_id": voice_bot.owner, "bot_type": "voice", "bot_id": voice_bot.id}
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key"
    )

async def validate_virtual_numbers_api_key(api_key: str = Header(..., alias="X-API-Key")):
    """Validate Virtual numbers-scoped API key"""
    try:
        user_info = api_key_service.validate_api_key(api_key, "virtual_numbers")
        return user_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid number API key: {str(e)}")