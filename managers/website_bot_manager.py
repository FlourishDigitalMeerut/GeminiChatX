import secrets
from models.website_bot import WebsiteBotMeta
from bots.website_bot import WebsiteBotInstance
from managers.base_manager import BaseManager
from config.settings import BASE_PERSIST_DIR, DEFAULT_FALLBACK

class WebsiteBotManager(BaseManager):
    def __init__(self):
        super().__init__(WebsiteBotMeta, WebsiteBotInstance)

    def create(self, name, owner=None, fallback_response=DEFAULT_FALLBACK):
        persist_dir = str(BASE_PERSIST_DIR / f"website_{name}_{secrets.token_hex(8)}")
        return super().create(
            name=name, 
            owner=owner, 
            persist_dir=persist_dir, 
            fallback_response=fallback_response,
            is_active=False
        )
    
    def get(self, bot_id: int):
        return self._instances.get(bot_id)

website_bot_manager = WebsiteBotManager()