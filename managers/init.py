from .website_bot_manager import WebsiteBotManager
from .whatsapp_bot_manager import WhatsAppBotManager
from .voice_bot_manager import voice_bot_manager

# Create global instances
website_bot_manager = WebsiteBotManager()
whatsapp_bot_manager = WhatsAppBotManager()

__all__ = [
    "WebsiteBotManager",
    "WhatsAppBotManager",
    "website_bot_manager", 
    "whatsapp_bot_manager"
    # "voice_bot_manager"
]