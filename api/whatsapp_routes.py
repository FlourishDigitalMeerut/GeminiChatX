from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Header, Response, Query, Request
from typing import Optional, List, Dict
import requests
import hashlib
import hmac
import json
from sqlmodel import Session, select  # pyright: ignore[reportMissingImports]
from pydantic import BaseModel
from managers.whatsapp_bot_manager import WhatsAppBotManager
from models.database import engine
from models.whatsapp_bot import WhatsAppBotMeta
from managers.whatsapp_bot_manager import whatsapp_bot_manager
from utils.file_handlers import process_uploaded_files, process_website_content
from core.text_processing import split_documents
from services.whatsapp_api import WhatsAppAPIService
from config.settings import (
    BATCH_SIZE, DEFAULT_FALLBACK, META_APP_ID, META_APP_SECRET, 
    META_REDIRECT_URL, WHATSAPP_API_VERSION, META_WEBHOOK_VERIFY_TOKEN
)
from api.dependencies import validate_whatsapp_api_key
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bots/whatsapp", tags=["whatsapp-bots"])

# Pydantic Models
class CreateBotReq(BaseModel):
    name: str
    owner: Optional[str] = None
    fallback_response: str = DEFAULT_FALLBACK

class UpdateFallbackReq(BaseModel):
    fallback_response: str

class ChatRequest(BaseModel):
    message: str

class BotCreateResponse(BaseModel):
    bot_id: int
    persist_dir: str
    fallback_response: str
    whatsapp_status: str
    is_active: bool = False  # Default inactive

class FallbackUpdateResponse(BaseModel):
    bot_id: int
    fallback_response: str
    message: str

class UploadDocsResponse(BaseModel):
    message: str
    sources: List[str]

class BotResponse(BaseModel):
    bot_response: str

class OAuthStartResponse(BaseModel):
    oauth_url: str

class OAuthCallbackResponse(BaseModel):
    message: str
    meta_user: dict
    access_token: str
    waba_details: Optional[dict] = None

class WhatsAppStatusResponse(BaseModel):
    bot_id: int
    whatsapp_status: str
    phone_number: Optional[str] = None
    is_active: bool
    webhook_configured: bool
    last_active_toggle: Optional[datetime] = None
    details: Optional[dict] = None

class ToggleActiveRequest(BaseModel):
    active: bool

class ToggleActiveResponse(BaseModel):
    message: str
    bot_id: int
    is_active: bool
    whatsapp_status: str
    phone_number: Optional[str] = None
    last_active_toggle: Optional[datetime] = None

@router.post("/create-bot", response_model=BotCreateResponse)
async def create_whatsapp_bot(
    req: CreateBotReq,
    access_token: Optional[str] = None,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Create a new WhatsApp bot (requires WhatsApp API key)"""
    
    # Validate WhatsApp API key and get user info
    api_key_info = await validate_whatsapp_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    # Set owner to user ID if not provided
    owner = user_id
    
    # Create bot with pending status and inactive by default
    bot_meta = whatsapp_bot_manager.create(
        name=req.name, 
        owner=owner, 
        access_token=access_token, 
        fallback_response=req.fallback_response
    )
    
    return BotCreateResponse(
        bot_id=bot_meta.id,
        persist_dir=bot_meta.persist_dir,
        fallback_response=bot_meta.fallback_response,
        whatsapp_status=bot_meta.whatsapp_status,
        is_active=bot_meta.is_active
    )

@router.patch("/{bot_id}/fallback", response_model=FallbackUpdateResponse)
async def update_whatsapp_bot_fallback(
    bot_id: int, 
    req: UpdateFallbackReq,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Update fallback response for a WhatsApp bot (requires WhatsApp API key)"""
    
    # Validate WhatsApp API key and get user info
    api_key_info = await validate_whatsapp_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    bot = whatsapp_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "WhatsApp Bot not found")
    
    # Verify the bot belongs to the user
    with Session(engine) as session:
        db_bot = session.exec(select(WhatsAppBotMeta).where(
            WhatsAppBotMeta.id == bot_id,
            WhatsAppBotMeta.owner == user_id
        )).first()
        if not db_bot:
            raise HTTPException(404, "WhatsApp Bot not found or you don't have permission")
        
        db_bot.fallback_response = req.fallback_response
        session.add(db_bot)
        session.commit()
        session.refresh(db_bot)
        
    bot.meta.fallback_response = req.fallback_response
    if bot.enhanced_chatbot:
        bot.enhanced_chatbot.fallback_response = req.fallback_response
        
    return FallbackUpdateResponse(
        bot_id=bot_id, 
        fallback_response=req.fallback_response, 
        message="Fallback response updated successfully"
    )

@router.post("/{bot_id}/upload_docs", response_model=UploadDocsResponse)
async def upload_docs(
    bot_id: int,
    website_url: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Upload documents to WhatsApp bot knowledge base (requires WhatsApp API key)"""
    
    # Validate WhatsApp API key and get user info
    api_key_info = await validate_whatsapp_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    bot = whatsapp_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")
    
    # Verify the bot belongs to the user
    with Session(engine) as session:
        db_bot = session.exec(select(WhatsAppBotMeta).where(
            WhatsAppBotMeta.id == bot_id,
            WhatsAppBotMeta.owner == user_id
        )).first()
        if not db_bot:
            raise HTTPException(403, "You don't have permission to modify this bot")

    # Clear existing knowledge base
    bot.clear_knowledge_base()
    bot.ensure_vector_store()
    
    all_docs = []

    # Process website content
    if website_url:
        website_docs = await process_website_content(website_url)
        all_docs.extend(website_docs)

    # Process uploaded files
    if files:
        file_docs = await process_uploaded_files(files)
        all_docs.extend(file_docs)

    if not all_docs:
        raise HTTPException(400, "No valid documents or website content provided")

    # Split documents into chunks
    chunks = split_documents(all_docs, BATCH_SIZE)
    
    # Add to vector store in batches
    if chunks:
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i:i+BATCH_SIZE]
            bot.vector_store.add_documents(batch)
        bot.vector_store.persist()

    sources = [f.filename for f in files] if files else [website_url] if website_url else []
    return UploadDocsResponse(
        message=f"Uploaded {len(chunks)} chunks to WhatsApp knowledge base for bot {bot_id}. Old knowledge base was cleared.",
        sources=sources
    )

@router.get("/{bot_id}/oauth/start", response_model=OAuthStartResponse)
async def start_meta_oauth(
    bot_id: int,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Start Meta OAuth for WhatsApp (requires WhatsApp API key)"""
    
    # Validate WhatsApp API key
    await validate_whatsapp_api_key(x_api_key)
    
    if not META_APP_ID or not META_REDIRECT_URL:
        raise HTTPException(500, "Meta app configuration missing")
    
    # Verify bot exists and belongs to user
    with Session(engine) as session:
        db_bot = session.get(WhatsAppBotMeta, bot_id)
        if not db_bot:
            raise HTTPException(404, "Bot not found")
    
    # Include bot_id in state for callback
    state = f"{bot_id}|{x_api_key}"
    
    oauth_url = (
        f"https://www.facebook.com/{WHATSAPP_API_VERSION}/dialog/oauth?"
        f"client_id={META_APP_ID}"
        f"&redirect_uri={META_REDIRECT_URL}"
        f"&scope=whatsapp_business_messaging,whatsapp_business_management,business_management"
        f"&state={state}"
    )
    return OAuthStartResponse(oauth_url=oauth_url)

@router.get("/oauth/callback", response_model=OAuthCallbackResponse)
async def meta_oauth_callback(
    code: str, 
    state: str,
    request: Request
):
    """Handle Meta OAuth callback"""
    
    try:
        # Parse state to get bot_id and api_key
        state_parts = state.split("|")
        if len(state_parts) != 2:
            raise HTTPException(400, "Invalid state parameter")
        
        bot_id = int(state_parts[0])
        api_key = state_parts[1]
        
        # Validate API key
        api_key_info = await validate_whatsapp_api_key(api_key)
        user_id = api_key_info["user_id"]
        
        if not META_APP_ID or not META_APP_SECRET or not META_REDIRECT_URL:
            raise HTTPException(500, "Meta app configuration missing")
        
        # Exchange code for access token
        token_url = "https://graph.facebook.com/v20.0/oauth/access_token"
        params = {
            "client_id": META_APP_ID,
            "client_secret": META_APP_SECRET,
            "redirect_uri": META_REDIRECT_URL,
            "code": code
        }
        
        token_response = requests.get(token_url, params=params)
        if token_response.status_code != 200:
            raise HTTPException(400, f"Meta token exchange failed: {token_response.text}")
        
        token_data = token_response.json()
        access_token = token_data.get("access_token")
        
        # Get user info from Meta
        me_response = requests.get(
            "https://graph.facebook.com/v20.0/me",
            params={"access_token": access_token, "fields": "id,name,email"}
        )
        user_data = me_response.json()
        
        # Get WhatsApp Business Account details
        whatsapp_service = WhatsAppAPIService(access_token)
        waba_details = whatsapp_service.get_waba_details()
        
        # Update bot with WhatsApp details
        with Session(engine) as session:
            db_bot = session.get(WhatsAppBotMeta, bot_id)
            if not db_bot:
                raise HTTPException(404, "Bot not found")
            
            # Verify bot belongs to user
            if db_bot.owner != user_id:
                raise HTTPException(403, "You don't own this bot")
            
            if waba_details:
                db_bot.mark_connected(
                    waba_id=waba_details["waba_id"],
                    phone_number_id=waba_details["phone_number_id"],
                    phone_number=waba_details["phone_number"],
                    business_id=waba_details["business_id"]
                )
                db_bot.access_token = access_token
                # IMPORTANT: Keep is_active as False by default after connection
                db_bot.is_active = False
                db_bot.whatsapp_status = "connected"  # Not "active" yet
                session.add(db_bot)
                session.commit()
                session.refresh(db_bot)
                
                # Setup webhook for this phone number
                webhook_setup = whatsapp_service.setup_webhook(waba_details["phone_number_id"])
                if webhook_setup:
                    db_bot.webhook_configured = True
                    session.add(db_bot)
                    session.commit()
        
        return OAuthCallbackResponse(
            message="WhatsApp API connected successfully! Remember to activate the bot when ready.", 
            meta_user=user_data, 
            access_token=access_token,
            waba_details=waba_details
        )
        
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}")
        raise HTTPException(500, f"OAuth callback failed: {str(e)}")

@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None),
    hub_challenge: str = Query(None),
    hub_verify_token: str = Query(None),
):
    """Verify webhook with Meta - REQUIRED by Meta"""
    if hub_mode == "subscribe" and hub_verify_token == META_WEBHOOK_VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(403, "Webhook verification failed")

@router.post("/webhook")
async def handle_whatsapp_webhook(
    request: Request,
    x_hub_signature_256: str = Header(None)
):
    """Handle incoming WhatsApp messages from Meta"""
    
    try:
        # Get request body
        body = await request.body()
        payload = json.loads(body.decode('utf-8'))
        
        logger.info(f"Received webhook: {json.dumps(payload, indent=2)}")
        
        # Process webhook
        if payload.get("object") == "whatsapp_business_account":
            for entry in payload.get("entry", []):
                for change in entry.get("changes", []):
                    if change.get("field") == "messages":
                        value = change.get("value", {})
                        messages = value.get("messages", [])
                        metadata = value.get("metadata", {})
                        phone_number_id = metadata.get("phone_number_id")
                        
                        # Find bot by phone_number_id - CRITICAL: Only respond if is_active == True
                        with Session(engine) as session:
                            db_bot = session.exec(select(WhatsAppBotMeta).where(
                                WhatsAppBotMeta.phone_number_id == phone_number_id,
                                WhatsAppBotMeta.is_active == True  # MUST BE ACTIVE
                            )).first()
                            
                            if not db_bot:
                                logger.info(f"No active bot found for phone number: {phone_number_id}")
                                # Bot exists but is inactive - silently ignore
                                return {"status": "ok"}
                            
                            # Get bot instance
                            bot = whatsapp_bot_manager.get(db_bot.id)
                            if not bot:
                                logger.warning(f"Bot instance not found for bot_id: {db_bot.id}")
                                return {"status": "ok"}
                            
                            # Process each message
                            for message in messages:
                                if message.get("type") == "text":
                                    from_number = message.get("from")
                                    text_body = message.get("text", {}).get("body")
                                    message_id = message.get("id")
                                    
                                    logger.info(f"Message from {from_number} to active bot {db_bot.name}: {text_body}")
                                    
                                    # Get bot response
                                    bot_response = bot.chat(text_body)
                                    
                                    # Send response via WhatsApp API
                                    whatsapp_service = WhatsAppAPIService(db_bot.access_token)
                                    send_success = whatsapp_service.send_message(
                                        phone_number_id=phone_number_id,
                                        to_number=from_number,
                                        message=bot_response
                                    )
                                    
                                    if not send_success:
                                        logger.error(f"Failed to send response to {from_number}")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return {"status": "error", "message": str(e)}

@router.get("/{bot_id}/status", response_model=WhatsAppStatusResponse)
async def get_whatsapp_status(
    bot_id: int,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Get WhatsApp connection status for a bot"""
    
    # Validate WhatsApp API key
    api_key_info = await validate_whatsapp_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    with Session(engine) as session:
        db_bot = session.get(WhatsAppBotMeta, bot_id)
        if not db_bot:
            raise HTTPException(404, "Bot not found")
        
        # Verify ownership
        if db_bot.owner != user_id:
            raise HTTPException(403, "You don't have permission to access this bot")
        
        details = None
        if db_bot.access_token and db_bot.phone_number_id:
            # Get current status from Meta
            whatsapp_service = WhatsAppAPIService(db_bot.access_token)
            business_profile = whatsapp_service.get_business_profile(db_bot.phone_number_id)
            if business_profile:
                details = business_profile
        
        return WhatsAppStatusResponse(
            bot_id=bot_id,
            whatsapp_status=db_bot.whatsapp_status,
            phone_number=db_bot.phone_number,
            is_active=db_bot.is_active,
            webhook_configured=db_bot.webhook_configured,
            last_active_toggle=db_bot.last_active_toggle,
            details=details
        )

@router.post("/{bot_id}/toggle-active", response_model=ToggleActiveResponse)
async def toggle_whatsapp_bot_active(
    bot_id: int,
    req: ToggleActiveRequest,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Toggle WhatsApp bot active/inactive status"""
    
    # Validate WhatsApp API key
    api_key_info = await validate_whatsapp_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    with Session(engine) as session:
        db_bot = session.get(WhatsAppBotMeta, bot_id)
        if not db_bot:
            raise HTTPException(404, "Bot not found")
        
        # Verify ownership
        if db_bot.owner != user_id:
            raise HTTPException(403, "You don't own this bot")
        
        # Check prerequisites before allowing activation
        if req.active:  # Only check when trying to activate
            if db_bot.whatsapp_status != "connected":
                raise HTTPException(400, "WhatsApp must be connected before activation")
            
            if not db_bot.access_token:
                raise HTTPException(400, "Access token missing. Please reconnect to Meta.")
            
            if not db_bot.phone_number_id:
                raise HTTPException(400, "Phone number not configured. Please reconnect to Meta.")
        
        # Toggle active status
        db_bot.is_active = req.active
        db_bot.whatsapp_status = "active" if req.active else "connected"
        db_bot.last_active_toggle = datetime.utcnow()
        db_bot.updated_at = datetime.utcnow()
        
        session.add(db_bot)
        session.commit()
        session.refresh(db_bot)
        
        # Update webhook subscription when toggling
        if db_bot.access_token and db_bot.phone_number_id:
            whatsapp_service = WhatsAppAPIService(db_bot.access_token)
            if req.active:
                # Ensure webhook is set up when activating
                webhook_setup = whatsapp_service.setup_webhook(db_bot.phone_number_id)
                if webhook_setup:
                    db_bot.webhook_configured = True
                    session.add(db_bot)
                    session.commit()
                else:
                    logger.warning(f"Webhook setup failed for bot {bot_id}")
            else:
                # When deactivating, we could unsubscribe from webhook
                # But typically we keep webhook active and just ignore messages
                logger.info(f"Bot {bot_id} deactivated. Webhook remains active but messages will be ignored.")
        
        status_message = "activated" if req.active else "deactivated"
        status_emoji = "✅" if req.active else "⏸️"
        
        return ToggleActiveResponse(
            message=f"{status_emoji} WhatsApp bot {status_message} successfully!",
            bot_id=bot_id,
            is_active=db_bot.is_active,
            whatsapp_status=db_bot.whatsapp_status,
            phone_number=db_bot.phone_number,
            last_active_toggle=db_bot.last_active_toggle
        )

# REMOVED: Old /activate endpoint - replaced by /toggle-active
# @router.post("/{bot_id}/activate", response_model=ActivateBotResponse)

@router.get("/my-bots")
async def get_my_whatsapp_bots(
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Get all WhatsApp bots for the current user (requires WhatsApp API key)"""
    
    # Validate WhatsApp API key and get user info
    api_key_info = await validate_whatsapp_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    with Session(engine) as session:
        bots = session.exec(
            select(WhatsAppBotMeta).where(
                WhatsAppBotMeta.owner == user_id
            ).order_by(WhatsAppBotMeta.created_at.desc())
        ).all()
        
        return {
            "user_id": user_id,
            "bot_type": "whatsapp",
            "bots": [
                {
                    "id": bot.id,
                    "name": bot.name,
                    "access_token": "***" if bot.access_token else None,
                    "phone_number": bot.phone_number,
                    "whatsapp_status": bot.whatsapp_status,
                    "is_active": bot.is_active,
                    "last_active_toggle": bot.last_active_toggle,
                    "fallback_response": bot.fallback_response,
                    "created_at": bot.created_at,
                    "updated_at": bot.updated_at
                }
                for bot in bots
            ]
        }

@router.post("/{bot_id}/test-chat", response_model=BotResponse)
async def test_whatsapp_bot(
    bot_id: int,
    req: ChatRequest,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Test the WhatsApp bot without sending actual WhatsApp messages"""
    
    # Validate WhatsApp API key and get user info
    api_key_info = await validate_whatsapp_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    bot = whatsapp_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")
    
    # Verify the bot belongs to the user
    with Session(engine) as session:
        db_bot = session.exec(select(WhatsAppBotMeta).where(
            WhatsAppBotMeta.id == bot_id,
            WhatsAppBotMeta.owner == user_id
        )).first()
        if not db_bot:
            raise HTTPException(403, "You don't have permission to access this bot")
    
    # Get bot response (works regardless of active/inactive status)
    answer = bot.chat(req.message)
    return BotResponse(bot_response=answer)