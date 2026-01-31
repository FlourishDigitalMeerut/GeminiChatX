from fastapi import APIRouter, Depends, HTTPException, status
from models.api_keys import AllBotAPIKeysResponse, BotAPIKeyResponse
from services.api_key_service import api_key_service
from services.auth import get_current_user
from typing import List
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api-keys", tags=["api-keys"])

@router.post("/generate", response_model=AllBotAPIKeysResponse)
async def generate_all_api_keys(
    current_user: dict = Depends(get_current_user)
):
    """
    Generate ALL 3 bot-type API keys at once (NO INPUT REQUIRED).
    
    Returns: Website, WhatsApp, and Voice API keys (expire in 3 hours)
    """
    user_id = str(current_user["_id"])
    
    try:
        # Generate all 3 keys at once
        all_keys = api_key_service.generate_all_bot_api_keys(user_id)
        
        logger.info(f"Generated all bot API keys for user: {user_id}")
        
        return all_keys
    except Exception as e:
        logger.error(f"Error generating API keys: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to generate API keys"
        )

@router.get("/my-keys", response_model=List[BotAPIKeyResponse])
async def get_my_api_keys(current_user: dict = Depends(get_current_user)):
    """Get all API keys for the current user"""
    user_id = str(current_user["_id"])
    return api_key_service.get_user_api_keys(user_id)

@router.delete("/revoke-all")
async def revoke_all_api_keys(current_user: dict = Depends(get_current_user)):
    """Revoke ALL API keys for the current user"""
    user_id = str(current_user["_id"])
    
    if api_key_service.revoke_all_user_keys(user_id):
        return {"message": "All API keys revoked successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke API keys"
        )