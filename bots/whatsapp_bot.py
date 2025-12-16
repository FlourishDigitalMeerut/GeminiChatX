from bots.base_bot import BaseBot

class WhatsAppBotInstance(BaseBot):
    def __init__(self, meta):
        super().__init__(meta, meta.persist_dir)