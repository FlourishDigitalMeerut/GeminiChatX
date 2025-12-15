import secrets
from datetime import datetime
from models.whatsapp_bot import WhatsAppBotMeta
from bots.whatsapp_bot import WhatsAppBotInstance
from managers.base_manager import BaseManager
from config.settings import BASE_PERSIST_DIR, DEFAULT_FALLBACK
from sqlmodel import Session, select # pyright: ignore[reportMissingImports]
from models.database import engine

class WhatsAppBotManager(BaseManager):
    def __init__(self):
        super().__init__(WhatsAppBotMeta, WhatsAppBotInstance)

    def create(self, name, owner=None, access_token=None, fallback_response=DEFAULT_FALLBACK):
        persist_dir = str(BASE_PERSIST_DIR / f"whatsapp_{name}_{secrets.token_hex(8)}")
        
        # Create bot with initial pending status
        return super().create(
            name=name, 
            owner=owner, 
            persist_dir=persist_dir, 
            access_token=access_token,
            fallback_response=fallback_response,
            whatsapp_status="pending",
            is_active=False,
            webhook_configured=False
        )
    
    def get(self, bot_id: int):
        return self._instances.get(bot_id)
    
    def get_by_phone_number(self, phone_number: str):
        """Get bot by WhatsApp phone number"""
        with Session(engine) as session:
            bot_meta = session.exec(
                select(WhatsAppBotMeta).where(
                    WhatsAppBotMeta.phone_number == phone_number,
                    WhatsAppBotMeta.is_active == True
                )
            ).first()
            
            if bot_meta:
                return self.get(bot_meta.id)
            return None
    
    def update_whatsapp_status(self, bot_id: int, status: str, details: dict = None):
        """Update WhatsApp connection status"""
        with Session(engine) as session:
            bot = session.get(WhatsAppBotMeta, bot_id)
            if not bot:
                return False
            
            bot.whatsapp_status = status
            bot.updated_at = datetime.utcnow()
            
            if status == "connected" and details:
                bot.waba_id = details.get("waba_id")
                bot.phone_number_id = details.get("phone_number_id")
                bot.phone_number = details.get("phone_number")
                bot.business_id = details.get("business_id")
            
            session.add(bot)
            session.commit()
            session.refresh(bot)
            
            # Update instance if exists
            if bot_id in self._instances:
                self._instances[bot_id].meta = bot
            
            return True

whatsapp_bot_manager = WhatsAppBotManager()