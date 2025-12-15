from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Header
from typing import Optional, List
import secrets
from sqlmodel import Session, select # pyright: ignore[reportMissingImports]
from pydantic import BaseModel
from models.database import engine
from api.dependencies import get_current_user_from_api_key, validate_website_api_key
import logging
from models.website_bot import WebsiteBotMeta
# from managers import website_bot_manager  # Import the instance, not the class
from managers.website_bot_manager import website_bot_manager
from utils.file_handlers import process_uploaded_files, process_website_content
from utils.web_utils import valid_url
from core.text_processing import split_documents
from core.framework_detector import detect_framework, generate_snippet, default_integrations
from api.dependencies import get_website_bot, verify_api_key
from config.settings import BATCH_SIZE, DEFAULT_FALLBACK

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bots/website", tags=["website-bots"])
# website_bot_manager = WebsiteBotManager()

# Pydantic Models
class CreateBotReq(BaseModel):
    name: str
    owner: Optional[str] = None
    fallback_response: str = DEFAULT_FALLBACK

class UpdateFallbackReq(BaseModel):
    fallback_response: str

class URLRequest(BaseModel):
    website_url: str

class ChatRequest(BaseModel):
    message: str

class BotResponse(BaseModel):
    bot_response: str

class BotCreateResponse(BaseModel):
    bot_id: int
    persist_dir: str
    api_key: str
    fallback_response: str

class APIKeyResponse(BaseModel):
    bot_id: int
    api_key: str

class APIKeyRegenerateResponse(BaseModel):
    bot_id: int
    new_api_key: str
    message: str

class FallbackUpdateResponse(BaseModel):
    bot_id: int
    fallback_response: str
    message: str

class UploadDocsResponse(BaseModel):
    message: str
    sources: List[str]

class IntegrationResponse(BaseModel):
    framework: str
    language: str
    integration_type: str
    integration_code: str
    instructions: str

class ToggleActiveRequest(BaseModel):
    is_active: bool

class BotStatusResponse(BaseModel):
    bot_id: int
    is_active: bool
    message: str

async def get_user_id_from_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
    """Extract user ID from API key (supports both bot-type and bot-specific keys)"""
    api_key_info = await get_current_user_from_api_key(x_api_key)
    return api_key_info["user_id"]

@router.post("/create-bot", response_model=BotCreateResponse)
async def create_website_bot(
    req: CreateBotReq,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Create a new website bot (requires website API key)"""
    
    # Validate website API key and get user info
    api_key_info = await validate_website_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    logger.info(f"Creating website bot for user {user_id} with name: {req.name}")
    
    # Set owner to user ID if not provided
    owner = user_id
    
    bot_meta = website_bot_manager.create(
        name=req.name, 
        owner=owner, 
        fallback_response=req.fallback_response
    )
    
    return BotCreateResponse(
        bot_id=bot_meta.id,
        persist_dir=bot_meta.persist_dir,
        api_key=bot_meta.api_key,
        fallback_response=bot_meta.fallback_response
    )

@router.get("/{bot_id}/api_key", response_model=APIKeyResponse)
async def get_website_bot_api_key(
    bot_id: int,
    api_key_info: dict = Depends(validate_website_api_key)
):
    """Get API key for a specific website bot (requires website API key)"""
    user_id = api_key_info["user_id"]
    
    bot = website_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")
    
    # Verify the bot belongs to the user
    with Session(engine) as session:
        db_bot = session.exec(select(WebsiteBotMeta).where(
            WebsiteBotMeta.id == bot_id,
            WebsiteBotMeta.owner == user_id
        )).first()
        if not db_bot:
            raise HTTPException(403, "You don't have permission to access this bot")
    
    return APIKeyResponse(bot_id=bot_id, api_key=bot.meta.api_key)

@router.post("/{bot_id}/regenerate_api_key", response_model=APIKeyRegenerateResponse)
async def regenerate_website_bot_api_key(
    bot_id: int,
    api_key_info: dict = Depends(validate_website_api_key)
):
    """Regenerate API key for a website bot (requires website API key)"""
    user_id = api_key_info["user_id"]
    
    bot = website_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")
    
    # Verify the bot belongs to the user
    with Session(engine) as session:
        db_bot = session.exec(select(WebsiteBotMeta).where(
            WebsiteBotMeta.id == bot_id,
            WebsiteBotMeta.owner == user_id
        )).first()
        if not db_bot:
            raise HTTPException(403, "You don't have permission to modify this bot")
    
    new_key = "aIWeBCb_" + secrets.token_hex(32)
    with Session(engine) as session:
        db_bot = session.exec(select(WebsiteBotMeta).where(WebsiteBotMeta.id == bot_id)).first()
        if db_bot:
            db_bot.api_key = new_key
            session.add(db_bot)
            session.commit()
            session.refresh(db_bot)
    bot.meta.api_key = new_key
    return APIKeyRegenerateResponse(
        bot_id=bot_id, 
        new_api_key=new_key, 
        message="API key regenerated successfully"
    )

@router.patch("/{bot_id}/fallback", response_model=FallbackUpdateResponse)
async def update_website_bot_fallback(
    bot_id: int, 
    req: UpdateFallbackReq,
    api_key_info: dict = Depends(validate_website_api_key)
):
    """Update fallback response for a website bot (requires website API key)"""
    user_id = api_key_info["user_id"]
    
    bot = website_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Website Bot not found")
    
    # Verify the bot belongs to the user
    with Session(engine) as session:
        db_bot = session.exec(select(WebsiteBotMeta).where(
            WebsiteBotMeta.id == bot_id,
            WebsiteBotMeta.owner == user_id
        )).first()
        if not db_bot:
            raise HTTPException(403, "You don't have permission to modify this bot")
        
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
    api_key_info: dict = Depends(validate_website_api_key)
):
    """Upload documents to website bot knowledge base (requires website API key)"""
    user_id = api_key_info["user_id"]
    
    bot = website_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")
    
    # Verify the bot belongs to the user
    with Session(engine) as session:
        db_bot = session.exec(select(WebsiteBotMeta).where(
            WebsiteBotMeta.id == bot_id,
            WebsiteBotMeta.owner == user_id
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
        message=f"Uploaded {len(chunks)} chunks to website knowledge base for bot {bot_id}. Old knowledge base was cleared.",
        sources=sources
    )

@router.post("/{bot_id}/generate_integration", response_model=IntegrationResponse)
async def generate_integration(
    bot_id: int, 
    req: URLRequest,
    api_key_info: dict = Depends(validate_website_api_key)
):
    """Generate integration code for a website bot (requires website API key)"""
    user_id = api_key_info["user_id"]
    
    bot = website_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")
    
    # Verify the bot belongs to the user
    with Session(engine) as session:
        db_bot = session.exec(select(WebsiteBotMeta).where(
            WebsiteBotMeta.id == bot_id,
            WebsiteBotMeta.owner == user_id
        )).first()
        if not db_bot:
            raise HTTPException(403, "You don't have permission to access this bot")
    
    url = req.website_url.strip()
    if not valid_url(url):
        raise HTTPException(400, "Invalid URL")
    
    logger.info(f"Generating integration for URL: {url}")
    
    from utils.web_utils import fetch_website_html
    html = fetch_website_html(url)
    if not html:
        logger.error(f"Failed to fetch HTML from {url}")
        return default_integrations()
    
    logger.info(f"Successfully fetched HTML, length: {len(html)}")
    
    framework, language = detect_framework(html)
    logger.info(f"Detected framework: {framework}, language: {language}")
    
    snippet = generate_snippet(framework, bot_id=str(bot_id), api_key=bot.meta.api_key, bot_name=bot.meta.name)
    if not snippet:
        logger.error("Failed to generate snippet")
        return default_integrations()
    
    logger.info(f"Generated snippet for {framework}")
    
    return IntegrationResponse(
        framework=framework,
        language=language,
        integration_type="frontend",
        integration_code=snippet.integration_code,
        instructions=snippet.instructions
    )

@router.post("/{bot_id}/chat", response_model=BotResponse)
async def chat_with_website_bot(
    bot_id: int, 
    payload: ChatRequest,
    # Supports both bot-type API key and bot-specific API key
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Chat with website bot (supports both bot-type and bot-specific API keys)"""
    
    # Get API key info
    api_key_info = await get_current_user_from_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    bot_type = api_key_info.get("bot_type")
    
    # Check if it's a bot-specific key (direct bot access)
    if "bot_id" in api_key_info and api_key_info["bot_id"] == bot_id:
        # Direct bot access - no further validation needed
        pass
    else:
        # Bot-type API key - verify the bot belongs to the user
        with Session(engine) as session:
            db_bot = session.exec(select(WebsiteBotMeta).where(
                WebsiteBotMeta.id == bot_id,
                WebsiteBotMeta.owner == user_id
            )).first()
            if not db_bot:
                raise HTTPException(403, "You don't have permission to access this bot")
    
    bot = website_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")
    
    if not bot.meta.is_active:
        raise HTTPException(423, {
            "error": "bot_inactive",
            "message": "This bot is currently inactive and will not respond to queries.Kindly activate the bot to enable responses.",
            "bot_id": bot_id,
            "bot_name": bot.meta.name,
            "status": "inactive",
            "action_required": "Activate the bot to enable responses"
        })
    
    message = payload.message
    if not message:
        raise HTTPException(422, "Message is required")
    
    answer = bot.chat(message)
    return BotResponse(bot_response=answer)

@router.get("/my-bots")
async def get_my_website_bots(
    api_key_info: dict = Depends(validate_website_api_key)
):
    """Get all website bots for the current user (requires website API key)"""
    user_id = api_key_info["user_id"]
    
    with Session(engine) as session:
        bots = session.exec(
            select(WebsiteBotMeta).where(
                WebsiteBotMeta.owner == user_id
            ).order_by(WebsiteBotMeta.created_at.desc())
        ).all()
        
        return {
            "user_id": user_id,
            "bot_type": "website",
            "bots": [
                {
                    "id": bot.id,
                    "name": bot.name,
                    "api_key": bot.api_key,
                    "fallback_response": bot.fallback_response,
                    "is_active": bot.is_active, 
                    "status": "active" if bot.is_active else "inactive",
                    "created_at": bot.created_at,
                    "updated_at": bot.updated_at
                }
                for bot in bots
            ]
        }
    
@router.patch("/{bot_id}/toggle-active", response_model=BotStatusResponse)
async def toggle_website_bot_active(
    bot_id: int, 
    req: ToggleActiveRequest,
    api_key_info: dict = Depends(validate_website_api_key)
):
    """Toggle website bot active/inactive status (requires website API key)"""
    user_id = api_key_info["user_id"]
    
    bot = website_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Website Bot not found")
    
    # Verify the bot belongs to the user
    with Session(engine) as session:
        db_bot = session.exec(select(WebsiteBotMeta).where(
            WebsiteBotMeta.id == bot_id,
            WebsiteBotMeta.owner == user_id
        )).first()
        if not db_bot:
            raise HTTPException(403, "You don't have permission to modify this bot")
        
        # Update bot active status
        db_bot.is_active = req.is_active
        session.add(db_bot)
        session.commit()
        session.refresh(db_bot)
        
    bot.meta.is_active = req.is_active
    
    status_text = "active and ready to respond" if req.is_active else "paused and will not respond"
    return BotStatusResponse(
        bot_id=bot_id, 
        is_active=req.is_active, 
        message=f"Website bot '{bot.meta.name}' is now {status_text}"
    )

@router.get("/{bot_id}/status")
async def get_website_bot_status(
    bot_id: int,
    api_key_info: dict = Depends(validate_website_api_key)
):
    """Get website bot status (requires website API key)"""
    user_id = api_key_info["user_id"]
    
    with Session(engine) as session:
        db_bot = session.exec(select(WebsiteBotMeta).where(
            WebsiteBotMeta.id == bot_id,
            WebsiteBotMeta.owner == user_id
        )).first()
        if not db_bot:
            raise HTTPException(404, "Website bot not found or not owned by you")
        
        return {
            "bot_id": bot_id,
            "name": db_bot.name,
            "is_active": db_bot.is_active,
            "status": "active" if db_bot.is_active else "inactive",
            "description": "Bot is ready to respond to queries" if db_bot.is_active else "Bot is paused and will not respond",
            "last_updated": db_bot.updated_at
        }