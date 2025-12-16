from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field  # pyright: ignore[reportMissingImports]
from config.settings import DEFAULT_FALLBACK
import secrets

class WhatsAppBotMeta(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    owner: Optional[str] = None
    persist_dir: str
    access_token: Optional[str] = None
    fallback_response: str = Field(default=DEFAULT_FALLBACK)
    
    # WhatsApp Specific Fields
    waba_id: Optional[str] = None  # WhatsApp Business Account ID
    phone_number_id: Optional[str] = None  # Phone Number ID
    phone_number: Optional[str] = None  # Actual phone number
    business_id: Optional[str] = None  # Business ID from Meta
    whatsapp_status: str = Field(default="pending")  # pending, connected, failed, active
    
    # TOGGLE FIELD - Default is inactive
    is_active: bool = Field(default=False)
    
    webhook_configured: bool = Field(default=False)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_active_toggle: Optional[datetime] = None
    
    def mark_connected(self, waba_id: str, phone_number_id: str, phone_number: str, business_id: str):
        """Mark bot as connected to WhatsApp"""
        self.waba_id = waba_id
        self.phone_number_id = phone_number_id
        self.phone_number = phone_number
        self.business_id = business_id
        self.whatsapp_status = "connected"
        self.is_active = False  # Still inactive by default
        self.updated_at = datetime.utcnow()
    
    def toggle_active(self, active: bool):
        """Toggle bot active status"""
        self.is_active = active
        self.whatsapp_status = "active" if active else "connected"
        self.last_active_toggle = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def mark_failed(self):
        """Mark bot as failed"""
        self.whatsapp_status = "failed"
        self.is_active = False
        self.updated_at = datetime.utcnow()