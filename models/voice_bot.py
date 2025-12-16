from sqlmodel import SQLModel, Field # pyright: ignore[reportMissingImports]
from typing import Optional, List
from datetime import datetime
import json

class VoiceBotMeta(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    owner: Optional[str] = None
    company_name: str
    api_key: str = Field(default="")
    plivo_app_id: Optional[str] = None
    fallback_response: str = "I'm sorry, I didn't understand that. Could you please repeat?"
    language: str = "en-IN"
    voice_type: str = "WOMAN"
    persist_dir: str
    outbound_welcome_message: str = "Hello! This is your assistant calling. How can I help you today?"
    is_active: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class VoiceCallAnalytics(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    bot_id: int = Field(foreign_key="voicebotmeta.id")
    recipient_name: str
    user_phone_number: str
    call_uuid: str = Field(unique=True, index=True)
    sentiment_category: str  # interested_in_product, not_interested, angry_customer, etc.
    confidence_score: float
    analysis_reason: str
    follow_up_action: str
    call_duration: Optional[int] = None  # in seconds
    created_at: datetime = Field(default_factory=datetime.utcnow)