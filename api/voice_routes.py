from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request, Depends, Body, Header
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import secrets
import json
import io
from sqlmodel import Session, select # pyright: ignore[reportMissingImports]
from models.database import engine
from models.voice_bot import VoiceBotMeta
from models.plivo_numbers import AccountPhoneNumber, NumberStatus
from managers.voice_bot_manager import voice_bot_manager
from utils.file_handlers import process_uploaded_files, process_website_content
from core.text_processing import split_documents
from api.dependencies import validate_voice_api_key, get_current_user_from_api_key
from config.settings import BATCH_SIZE, DEFAULT_FALLBACK, SUPPORTED_LANGUAGES, VOICE_TYPES
from fastapi.responses import Response
import xml.etree.ElementTree as ET
from config.settings import LANGUAGE_VOICE_AVAILABILITY
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bots/voice", tags=["voice-bots"])

# ========== PYDANTIC MODELS ==========

class CreateVoiceBotReq(BaseModel):
    name: str
    company_name: str
    owner: Optional[str] = None

class UpdateVoiceConfigReq(BaseModel):
    language: str
    voice_type: str
    fallback_response: str
    outbound_welcome_message: str

class TestCallRequest(BaseModel):
    test_phone_number: str  
    from_number: str  
    test_message: Optional[str] = None

class BulkCallRequest(BaseModel):
    phone_numbers: List[str]
    message: Optional[str] = None
    from_number: str 

class ChatRequest(BaseModel):
    message: str

class BotResponse(BaseModel):
    bot_response: str

class VoicePreviewRequest(BaseModel):
    voice_type: str
    language: str
    preview_text: str

class RecipientEntry(BaseModel):
    name: str
    number: str 

class BulkCallManualRequest(BaseModel):
    recipients: List[RecipientEntry]
    message: Optional[str] = None
    from_number: str  

class BulkCallExcelRequest(BaseModel):
    message: Optional[str] = None
    from_number: str

class ToggleActiveRequest(BaseModel):
    is_active: bool

class BotStatusResponse(BaseModel):
    bot_id: int
    is_active: bool
    message: str

# ========== BOT MANAGEMENT ROUTES ==========

@router.post("/create-bot", response_model=dict)
async def create_voice_bot(
    req: CreateVoiceBotReq,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Create a new voice bot - STEP 1: Basic info only (requires voice API key)"""
    
    # Validate voice API key and get user info
    api_key_info = await validate_voice_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    # Set owner to user ID if not provided
    owner = user_id
    
    bot_meta = voice_bot_manager.create_basic_bot(
        name=req.name,
        company_name=req.company_name,
        owner=owner
    )
    
    return {
        "bot_id": bot_meta.id,
        "api_key": bot_meta.api_key,  
        "message": "Voice bot created successfully",
        "next_step": "upload_knowledge_base"
    }

@router.post("/{bot_id}/upload_docs", response_model=dict)
async def upload_voice_docs(
    bot_id: int,
    website_url: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Upload knowledge base for voice bot - replaces old knowledge (requires voice API key)"""
    
    # Validate voice API key and get user info
    api_key_info = await validate_voice_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    bot = voice_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Voice bot not found")
    
    # Verify the bot belongs to the user
    with Session(engine) as session:
        db_bot = session.exec(select(VoiceBotMeta).where(
            VoiceBotMeta.id == bot_id,
            VoiceBotMeta.owner == user_id
        )).first()
        if not db_bot:
            raise HTTPException(403, "You don't have permission to modify this bot")

    # Clear existing knowledge base (automatic replacement)
    bot.clear_knowledge_base()
    
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
    
    # Add to vector store
    if chunks:
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i:i+BATCH_SIZE]
            bot.vector_store.add_documents(batch)
        # bot.vector_store.persist()

    sources = [f.filename for f in files] if files else [website_url] if website_url else []
    return {
        "message": f"Uploaded {len(chunks)} chunks to voice bot knowledge base. Old knowledge base was cleared.",
        "sources": sources,
        "next_step": "Configure voice settings for a voice bot"
    }

@router.post("/{bot_id}/configure-voice", response_model=dict)
async def configure_voice_settings(
    bot_id: int, 
    req: UpdateVoiceConfigReq,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """STEP 3: Configure voice settings after knowledge base upload (requires voice API key)"""
    
    # Validate voice API key and get user info
    api_key_info = await validate_voice_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    if req.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(400, f"Unsupported language. Supported: {SUPPORTED_LANGUAGES}")
    
    available_voices = LANGUAGE_VOICE_AVAILABILITY.get(req.language, [])
    if req.voice_type not in available_voices:
        raise HTTPException(400, f"Voice type '{req.voice_type}' not available for {req.language}. Available: {available_voices}")
    
    bot = voice_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Voice bot not found")
    
    # Verify the bot belongs to the user
    with Session(engine) as session:
        bot_meta = session.exec(select(VoiceBotMeta).where(
            VoiceBotMeta.id == bot_id,
            VoiceBotMeta.owner == user_id
        )).first()
        if not bot_meta:
            raise HTTPException(403, "You don't have permission to modify this bot")
        
        # Update bot configuration
        bot_meta.language = req.language
        bot_meta.voice_type = req.voice_type
        bot_meta.fallback_response = req.fallback_response
        bot_meta.outbound_welcome_message = req.outbound_welcome_message
        session.add(bot_meta)
        session.commit()
        
        # Update the bot instance
        bot.meta.language = req.language
        bot.meta.voice_type = req.voice_type
        bot.meta.fallback_response = req.fallback_response
        bot.meta.outbound_welcome_message = req.outbound_welcome_message
    
    return {
        "message": "Voice configuration updated successfully",
        "next_step": "test_voice_bot"
    }

@router.get("/{bot_id}/available-numbers")
async def get_bot_available_numbers(
    bot_id: int,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """
    Get all phone numbers available for this bot to use (for dropdown)
    This endpoint is called by the frontend to populate the number selection dropdown
    (requires voice API key)
    """
    
    # Validate voice API key and get user info
    api_key_info = await validate_voice_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    # Verify bot belongs to user
    with Session(engine) as session:
        bot = session.exec(
            select(VoiceBotMeta).where(
                VoiceBotMeta.id == bot_id,
                VoiceBotMeta.owner == user_id
            )
        ).first()
        
        if not bot:
            raise HTTPException(404, "Voice bot not found or not owned by you")
    
    # Get user's numbers formatted for dropdown
    dropdown_options = voice_bot_manager.get_user_numbers_for_dropdown(
        user_id=user_id,
        bot_id=bot_id
    )
    
    if not dropdown_options:
        return {
            "bot_id": bot_id,
            "user_id": user_id,
            "available_numbers": [],
            "message": "You don't have any phone numbers.",
            "action_required": True,
            "steps": [
                "1. Search for available numbers at /api/v1/plivo/numbers/search",
                "2. Purchase a number that fits your needs",
                "3. The number will be available here for selection"
            ],
            "quick_links": {
                "search_numbers": "/api/v1/plivo/numbers/search?country_iso=US",
                "buy_numbers_docs": "https://docs.plivo.com/api/number/buy-a-number/"
            }
        }
    
    # Get default number
    default_number = voice_bot_manager.get_default_user_number(user_id)
    default_option = None
    if default_number:
        default_option = {
            "value": default_number.phone_number,
            "label": f"{default_number.alias or default_number.phone_number} ({default_number.city or default_number.country_iso}) [Default]",
            "is_default": True
        }
    
    return {
        "bot_id": bot_id,
        "user_id": user_id,
        "available_numbers": dropdown_options,
        "default_number": default_option,
        "total_numbers": len(dropdown_options),
        "note": "Select a phone number to use for calls. Numbers with higher success rates are recommended."
    }

@router.get("/{bot_id}/number-status")
async def check_number_status(
    bot_id: int,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """
    Check if user has phone numbers available for calling
    Returns status and guidance (requires voice API key)
    """
    
    # Validate voice API key and get user info
    api_key_info = await validate_voice_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    # Verify bot belongs to user
    with Session(engine) as session:
        bot = session.exec(
            select(VoiceBotMeta).where(
                VoiceBotMeta.id == bot_id,
                VoiceBotMeta.owner == user_id
            )
        ).first()
        
        if not bot:
            raise HTTPException(404, "Voice bot not found or not owned by you")
    
    user_numbers = voice_bot_manager.get_user_numbers(user_id=user_id, active_only=True)
    
    if not user_numbers:
        return {
            "has_numbers": False,
            "message": "You need to purchase a phone number to make calls",
            "bot_id": bot_id,
            "bot_name": bot.meta.name,
            "next_steps": [
                {
                    "step": 1,
                    "action": "search_numbers",
                    "description": "Search for available phone numbers",
                    "endpoint": "/api/v1/plivo/numbers/search?country_iso=US&number_type=local"
                },
                {
                    "step": 2,
                    "action": "buy_number",
                    "description": "Purchase a number",
                    "endpoint": "/api/v1/plivo/numbers/buy"
                },
                {
                    "step": 3,
                    "action": "make_calls",
                    "description": "Start making calls with your new number",
                    "endpoint": f"/api/v1/bots/voice/{bot_id}/test-call"
                }
            ],
            "recommended_countries": ["US", "CA", "GB", "IN"],
            "estimated_cost": ""
        }
    
    return {
        "has_numbers": True,
        "total_numbers": len(user_numbers),
        "numbers": [
            {
                "phone_number": n.phone_number,
                "alias": n.alias,
                "is_default": n.is_default,
                "country": n.country_iso,
                "voice_enabled": n.voice_enabled
            }
            for n in user_numbers
        ],
        "message": "You have phone numbers available for calling",
        "ready_for_calls": True
    }

@router.post("/{bot_id}/test-call")
async def test_voice_bot(
    bot_id: int, 
    req: TestCallRequest,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """
    Initiate test call - user MUST select which number to use (requires voice API key)
    """
    
    # Validate voice API key and get user info
    api_key_info = await validate_voice_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    bot = voice_bot_manager.get(bot_id)
    
    if not bot:
        raise HTTPException(404, "Voice bot not found")
    
    # Verify bot belongs to user
    if bot.meta.owner != user_id:
        raise HTTPException(403, "You don't own this bot")
    
    if not bot.meta.is_active:
        raise HTTPException(423, {
            "error": "bot_inactive",
            "message": "This bot is currently inactive and cannot make test calls.Kindly activate the bot to enable test calling.",
            "bot_id": bot_id,
            "bot_name": bot.meta.name,
            "status": "inactive",
            "action_required": "Activate the bot to enable calling"
        })
    
    # Check if user has any phone numbers
    user_numbers = voice_bot_manager.get_user_numbers(user_id=user_id, active_only=True)
    
    if not user_numbers:
        raise HTTPException(400, {
            "error": "no_phone_numbers",
            "message": "You don't have any phone numbers. Please purchase a phone number first.",
            "action_required": "buy_phone_number",
            "help_url": "/api/v1/plivo/numbers/search",
            "steps": [
                "1. Search for available numbers",
                "2. Purchase a number (GeminiChatX will pay)",
                "3. Try making calls again"
            ]
        })
    
    # Validate the from_number belongs to user
    with Session(engine) as session:
        number_owned = session.exec(
            select(AccountPhoneNumber).where(
                AccountPhoneNumber.user_id == user_id,
                AccountPhoneNumber.phone_number == req.from_number,
                AccountPhoneNumber.status == NumberStatus.ACTIVE,
                AccountPhoneNumber.voice_enabled == True
            )
        ).first()
        
        if not number_owned:
            raise HTTPException(400, {
                "error": "invalid_phone_number",
                "message": f"You don't own this phone number ({req.from_number}) or it's not active for voice calls",
                "available_numbers": [n.phone_number for n in user_numbers]
            })
    
    # Make the test call
    call_result = bot.make_test_call(
        to_number=req.test_phone_number,
        from_number=req.from_number,
        test_message=req.test_message
    )
    
    return {
        "message": f"Test call initiated from {req.from_number} to {req.test_phone_number}",
        "call_id": call_result.get("call_id"),
        "status": "initiated"
    }
    
@router.post("/{bot_id}/bulk-call")
async def bulk_call(
    bot_id: int,
    request: Request,
    # Accept both JSON body and form-data
    data: Optional[dict] = Body(None),
    recipients_json: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    from_number: str = Form(None),
    x_api_key: str = Header(None, alias="X-API-Key")  # ADDED: API key validation
):
    """
    Robust bulk_call with REQUIRED from_number selection
    User MUST select which phone number to use for the calls
    (requires voice API key)
    """
    
    # Validate voice API key and get user info
    api_key_info = await validate_voice_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    bot = voice_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Voice bot not found")
    
    # Verify bot belongs to user
    if bot.meta.owner != user_id:
        raise HTTPException(403, "You don't own this bot")
    
    if not bot.meta.is_active:
        raise HTTPException(423, {
            "error": "bot_inactive",
            "message": "This bot is currently inactive and cannot make calls.Kindly activate the bot to enable calling.",
            "bot_id": bot_id,
            "bot_name": bot.meta.name,
            "status": "inactive",
            "action_required": "Activate the bot to enable calling"
        })
    
    # --- Try to detect & parse body robustly ---
    manual_recipients = None
    from_number_final = None
    debug = {"content_type": request.headers.get("content-type"), "parsed_from": None}
    
    # 1) Prefer body parsed by FastAPI (data)
    if data:
        manual_recipients = data.get("recipients") if isinstance(data, dict) else None
        from_number_final = data.get("from_number")
        debug["parsed_from"] = "fastapi_body_data"
    
    # 2) If no data, attempt to read request.json() directly
    if manual_recipients is None:
        try:
            body_json = await request.json()
            if isinstance(body_json, dict):
                manual_recipients = body_json.get("recipients")
                from_number_final = body_json.get("from_number")
                debug["parsed_from"] = "request.json()"
            elif isinstance(body_json, list):
                manual_recipients = body_json
                debug["parsed_from"] = "request.json()_top_level_list"
        except Exception:
            pass
    
    # 3) Check form-data
    if manual_recipients is None or file is None:
        try:
            form = await request.form()
            if "file" in form and not file:
                file = form["file"]
                debug["parsed_from"] = "form_file"
            if "recipients" in form and not manual_recipients:
                try:
                    manual_recipients = json.loads(form["recipients"])
                    debug["parsed_from"] = "form_recipients_field"
                except:
                    pass
            if recipients_json and not manual_recipients:
                try:
                    manual_recipients = json.loads(recipients_json)
                    debug["parsed_from"] = "recipients_json_form_param"
                except:
                    pass
            # Get from_number from form if not already set
            if not from_number_final and "from_number" in form:
                from_number_final = form["from_number"]
        except Exception:
            pass
    
    # Check if user has any phone numbers
    user_numbers = voice_bot_manager.get_user_numbers(user_id=user_id, active_only=True)
    
    if not user_numbers:
        raise HTTPException(400, {
            "error": "no_phone_numbers",
            "message": "You don't have any phone numbers. Please purchase a phone number first.",
            "action_required": "buy_phone_number",
            "help_url": "/api/v1/plivo/numbers/search"
        })
    
    # 4) Use the from_number parameter if provided
    if not from_number_final and from_number:
        from_number_final = from_number
    
    # --- VALIDATION: from_number is REQUIRED ---
    if not from_number_final:
        raise HTTPException(400, {
            "error": "Your virtual number is required for calling",
            "message": "Please select which phone number to use for calls."
        })
    
    # Verify the from_number belongs to user
    with Session(engine) as session:
        number_owned = session.exec(
            select(AccountPhoneNumber).where(
                AccountPhoneNumber.user_id == user_id,
                AccountPhoneNumber.phone_number == from_number_final,
                AccountPhoneNumber.status == NumberStatus.ACTIVE,
                AccountPhoneNumber.voice_enabled == True
            )
        ).first()
        
        if not number_owned:
            raise HTTPException(400, {
                "error": "Invalid from_number",
                "message": f"You don't own this phone number ({from_number_final}) or it's not active for voice calls"
            })
    
    # --- Rest of recipient processing ---
    if (not manual_recipients or len(manual_recipients) == 0) and file is None:
        raise HTTPException(400, "Either provide recipients manually OR upload an Excel file.")
    
    if file is not None and manual_recipients and len(manual_recipients) > 0:
        raise HTTPException(400, "Provide ONLY one: manual recipients OR file. Not both.")
    
    recipient_data = []
    
    # --- Manual mode ---
    if file is None:
        for entry in manual_recipients:
            if isinstance(entry, dict):
                name = entry.get("name", "").strip()
                number = str(entry.get("number", "")).strip()
            else:
                name = ""
                number = str(entry).strip()
            
            if not number:
                continue
            
            if not number.startswith("+"):
                number = "+" + number.lstrip("0")
            
            recipient_data.append({"name": name, "number": number})
        
        if not recipient_data:
            raise HTTPException(400, "At least one valid recipient required")
    
    # --- Excel mode ---
    else:
        if not file.filename.endswith((".xlsx", ".xls")):
            raise HTTPException(400, "Excel file must be .xlsx or .xls")
        try:
            import pandas as pd
            content = await file.read()
            df = pd.read_excel(io.BytesIO(content))
            if "name" not in df.columns or "number" not in df.columns:
                raise HTTPException(400, "Excel must contain 'name' and 'number' columns")
            for _, row in df.iterrows():
                name = str(row["name"]).strip()
                number = str(row["number"]).strip()
                if not number.startswith("+"):
                    number = "+" + number.lstrip("0")
                recipient_data.append({"name": name, "number": number})
        except Exception as e:
            raise HTTPException(400, f"Error reading Excel file: {str(e)}")
    
    # --- Make call with selected from_number ---
    numbers_string = "<".join([r["number"] for r in recipient_data])
    message_to_send = bot.meta.outbound_welcome_message
    
    call_result = bot.make_bulk_call(
        to_numbers=numbers_string,
        message=message_to_send,
        recipient_data=recipient_data,
        from_number=from_number_final,  # Use selected number
    ) or {}
    
    return {
        "message": f"Initiated {len(recipient_data)} bulk calls from {from_number_final}",
        "caller_id": from_number_final,
        "spoken_message": message_to_send,
        "recipients_processed": len(recipient_data),
        "call_ids": call_result.get("call_ids", []),
        "status": call_result.get("status"),
        "error": call_result.get("error"),
        "source": "excel" if file else "manual",
        "recipient_data_count": len(recipient_data),
    }

# ========== OTHER ROUTES (unchanged but add API key validation) ==========

@router.post("/{bot_id}/preview-voice")
async def preview_voice(
    bot_id: int, 
    req: VoicePreviewRequest,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Preview voice using Plivo TTS - RETURNS ACTUAL AUDIO (requires voice API key)"""
    
    # Validate voice API key and get user info
    api_key_info = await validate_voice_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    if req.voice_type not in VOICE_TYPES:
        raise HTTPException(400, "Invalid voice type")
    
    bot = voice_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Voice bot not found")
    
    # Verify bot belongs to user
    if bot.meta.owner != user_id:
        raise HTTPException(403, "You don't own this bot")
    
    try:
        # Use Plivo's Speak API to generate actual audio
        response = bot.plivo_client.calls.speak(
            call_uuid="preview_" + str(bot_id),  # Dummy call ID for preview
            text=req.preview_text,
            voice=req.voice_type,
            language=req.language
        )
        
        # Return the generated audio file
        return Response(
            content=response.audio_content,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=voice_preview.mp3"}
        )
        
    except Exception as e:
        raise HTTPException(500, f"Voice preview failed: {str(e)}")
    
@router.get("/{bot_id}/call-answer")
def handle_call_answer(bot_id: int):
    """Handle incoming call - generate Plivo XML (public endpoint, no API key needed)"""
    bot = voice_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Voice bot not found")
    
    response_xml = f"""
    <Response>
        <Speak voice="{bot.meta.voice_type}" language="{bot.meta.language}">
            Hello! I am {bot.meta.name} from {bot.meta.company_name} company. How can I help you today?
        </Speak>
        <Record action="/api/v1/bots/voice/{bot_id}/process-audio" 
                method="POST" 
                maxLength="30" 
                playBeep="true"
                transcriptionType="auto"
                transcriptionUrl="/api/v1/bots/voice/{bot_id}/process-transcript"/>
    </Response>
    """
    
    return Response(content=response_xml, media_type="application/xml")

@router.post("/{bot_id}/process-transcript")
async def process_transcript(bot_id: int, request: Request):
    """Process speech-to-text transcript - STORE ONLY, NO ANALYSIS (public endpoint for Plivo)"""
    form_data = await request.form()
    transcript = form_data.get('transcription', '')
    call_uuid = form_data.get('call_uuid', '')
    user_phone_number = form_data.get('From', '')  # Get caller's number
    
    bot = voice_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Voice bot not found")
    
    # Store transcript segment for later analysis
    if transcript:
        bot.store_call_transcript(call_uuid, transcript)
    
    # Generate bot response based on current segment only
    bot_response = bot.chat(transcript) if transcript else bot.meta.fallback_response
    
    response_xml = f"""
    <Response>
        <Speak voice="{bot.meta.voice_type}" language="{bot.meta.language}">
            {bot_response}
        </Speak>
        <Record action="/api/v1/bots/voice/{bot_id}/process-audio" 
                method="POST" 
                maxLength="30" 
                playBeep="true"
                transcriptionType="auto"
                transcriptionUrl="/api/v1/bots/voice/{bot_id}/process-transcript"/>
    </Response>
    """
    
    return Response(content=response_xml, media_type="application/xml")

@router.post("/{bot_id}/call-ended")
async def handle_call_end(
    bot_id: int, 
    request: Request,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Handle call completion - PERFORM SENTIMENT ANALYSIS & STORE RESULTS (requires voice API key)"""
    
    # Validate voice API key and get user info
    api_key_info = await validate_voice_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    form_data = await request.form()
    call_uuid = form_data.get('CallUUID', '')
    user_phone_number = form_data.get('To', '')  # The number we called
    call_duration = form_data.get('CallDuration', 0)
    
    bot = voice_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Voice bot not found")
    
    # Verify bot belongs to user
    if bot.meta.owner != user_id:
        raise HTTPException(403, "You don't own this bot")
    
    # Get complete transcript
    full_transcript = bot.get_full_transcript(call_uuid)
    
    # Perform sentiment analysis on complete transcript
    sentiment_analysis = bot.analyze_call_sentiment(full_transcript)
    
    # Store ONLY the analysis results (not transcript) in database
    voice_bot_manager.store_call_analytics(
        bot_id=bot_id,
        user_phone_number=user_phone_number,
        call_uuid=call_uuid,
        sentiment_data=sentiment_analysis,
        call_duration=int(call_duration) if call_duration else None
    )
    
    # Clear transcript from memory
    bot.clear_transcript(call_uuid)
    
    return {
        "status": "analysis_completed",
        "call_uuid": call_uuid,
        "user_number": user_phone_number,
        "sentiment_category": sentiment_analysis.get("category"),
        "confidence": sentiment_analysis.get("confidence")
    }

@router.get("/{bot_id}/call-analytics")
async def get_call_analytics(
    bot_id: int, 
    user_number: str = None,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Get stored sentiment analysis results (requires voice API key)"""
    
    # Validate voice API key and get user info
    api_key_info = await validate_voice_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    bot = voice_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Voice bot not found")
    
    # Verify bot belongs to user
    if bot.meta.owner != user_id:
        raise HTTPException(403, "You don't own this bot")
    
    analytics = voice_bot_manager.get_call_analytics(bot_id, user_number)
    
    return {
        "bot_id": bot_id,
        "user_number": user_number,
        "analytics": [
            {
                "recipient_name": item.recipient_name,
                "recipient_number": item.user_phone_number,
                "call_uuid": item.call_uuid,
                "sentiment_category": item.sentiment_category,
                "confidence_score": item.confidence_score,
                "analysis_reason": item.analysis_reason,
                "follow_up_action": item.follow_up_action,
                "call_duration": item.call_duration,
                "created_at": item.created_at
            }
            for item in analytics
        ]
    }

@router.post("/{bot_id}/chat", response_model=BotResponse)
async def chat_with_voice_bot(
    bot_id: int, 
    payload: ChatRequest,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Text-based chat for testing voice bot logic (requires voice API key)"""
    
    # Validate voice API key and get user info
    api_key_info = await validate_voice_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    bot = voice_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Voice bot not found")
    
    # Verify bot belongs to user
    if bot.meta.owner != user_id:
        raise HTTPException(403, "You don't own this bot")
    
    if not bot.meta.is_active:
        raise HTTPException(423, {
            "error": "bot_inactive",
            "message": "This bot is currently inactive and cannot respond.Kindly activate the bot to respond.",
            "bot_id": bot_id,
            "bot_name": bot.meta.name,
            "status": "inactive",
            "action_required": "Activate the bot to enable responses."
        })
    
    message = payload.message
    if not message:
        raise HTTPException(422, "Message is required")
    
    # Test sentiment analysis
    analysis = bot.analyze_call_sentiment(message)
    answer = bot.chat(message)
    
    return BotResponse(
        bot_response=f"{answer}\n\n[Analysis: {analysis['category']} - {analysis['reason']}]"
    )

@router.get("/supported-languages")
async def get_supported_languages(
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Get supported languages (requires voice API key)"""
    
    # Validate voice API key
    await validate_voice_api_key(x_api_key)
    
    return {
        "languages": SUPPORTED_LANGUAGES,
        "voice_availability": LANGUAGE_VOICE_AVAILABILITY
    }

@router.get("/voice-types")
async def get_voice_types(
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Get available voice types (requires voice API key)"""
    
    # Validate voice API key
    await validate_voice_api_key(x_api_key)
    
    return {"voice_types": VOICE_TYPES}

@router.post("/{bot_id}/regenerate_api_key", response_model=dict)
async def regenerate_api_key(
    bot_id: int,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Regenerate API key for a voice bot (requires voice API key)"""
    
    # Validate voice API key and get user info
    api_key_info = await validate_voice_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    with Session(engine) as session:
        bot_meta = session.exec(select(VoiceBotMeta).where(
            VoiceBotMeta.id == bot_id,
            VoiceBotMeta.owner == user_id
        )).first()
        
        if not bot_meta:
            raise HTTPException(404, "Voice bot not found or you don't have permission")
        
        # Generate new API key
        new_api_key = "aIVoice_" + secrets.token_hex(32)
        
        # Update the bot
        bot_meta.api_key = new_api_key
        bot_meta.updated_at = datetime.utcnow()
        session.add(bot_meta)
        session.commit()
        
        # Update the bot instance if loaded
        if bot_id in voice_bot_manager.bots:
            voice_bot_manager.bots[bot_id].meta.api_key = new_api_key
    
    return {
        "message": "API key regenerated successfully",
        "new_api_key": new_api_key,
        "bot_id": bot_id
    }

@router.get("/my-bots")
async def get_my_voice_bots(
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Get all voice bots for the current user (requires voice API key)"""
    
    # Validate voice API key and get user info
    api_key_info = await validate_voice_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    with Session(engine) as session:
        bots = session.exec(
            select(VoiceBotMeta).where(
                VoiceBotMeta.owner == user_id
            ).order_by(VoiceBotMeta.created_at.desc())
        ).all()
        
        return {
            "user_id": user_id,
            "bot_type": "voice",
            "total_bots": len(bots),
            "bots": [
                {
                    "id": bot.id,
                    "name": bot.name,
                    "company_name": bot.company_name,
                    "api_key": bot.api_key,
                    "language": bot.language,
                    "voice_type": bot.voice_type,
                    "fallback_response": bot.fallback_response,
                    "outbound_welcome_message": bot.outbound_welcome_message,
                    "is_active": bot.is_active,  
                    "status": "active" if bot.is_active else "inactive",
                    "created_at": bot.created_at,
                    "updated_at": bot.updated_at
                }
                for bot in bots
            ]
        }
    
@router.patch("/{bot_id}/toggle-active", response_model=BotStatusResponse)
async def toggle_voice_bot_active(
    bot_id: int, 
    req: ToggleActiveRequest,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Toggle voice bot active/inactive status (requires voice API key)"""
    
    # Validate voice API key and get user info
    api_key_info = await validate_voice_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    bot = voice_bot_manager.get(bot_id)
    if not bot:
        raise HTTPException(404, "Voice bot not found")
    
    # Verify the bot belongs to the user
    with Session(engine) as session:
        db_bot = session.exec(select(VoiceBotMeta).where(
            VoiceBotMeta.id == bot_id,
            VoiceBotMeta.owner == user_id
        )).first()
        if not db_bot:
            raise HTTPException(403, "You don't have permission to modify this bot")
        
        # Update bot active status
        db_bot.is_active = req.is_active
        session.add(db_bot)
        session.commit()
        session.refresh(db_bot)
        
    bot.meta.is_active = req.is_active
    
    status_text = "active and ready to make/receive calls" if req.is_active else "paused and will not make/receive calls"
    return BotStatusResponse(
        bot_id=bot_id, 
        is_active=req.is_active, 
        message=f"Voice bot '{bot.meta.name}' is now {status_text}"
    )

@router.get("/{bot_id}/status")
async def get_voice_bot_status(
    bot_id: int,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Get voice bot status (requires voice API key)"""
    
    # Validate voice API key and get user info
    api_key_info = await validate_voice_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    with Session(engine) as session:
        db_bot = session.exec(select(VoiceBotMeta).where(
            VoiceBotMeta.id == bot_id,
            VoiceBotMeta.owner == user_id
        )).first()
        if not db_bot:
            raise HTTPException(404, "Voice bot not found or not owned by you")
        
        return {
            "bot_id": bot_id,
            "name": db_bot.name,
            "company_name": db_bot.company_name,
            "is_active": db_bot.is_active,
            "status": "active" if db_bot.is_active else "inactive",
            "description": "Bot can make and receive calls" if db_bot.is_active else "Bot is paused and cannot make/receive calls",
            "language": db_bot.language,
            "voice_type": db_bot.voice_type,
            "last_updated": db_bot.updated_at
        }