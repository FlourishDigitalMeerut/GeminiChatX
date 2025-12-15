from sqlmodel import SQLModel, create_engine, Session # pyright: ignore[reportMissingImports]
from config.settings import DATABASE_URL

engine = create_engine(DATABASE_URL)

def create_db_and_tables():
    # Import all models here to ensure they're registered
    from models.website_bot import WebsiteBotMeta
    from models.whatsapp_bot import WhatsAppBotMeta
    from models.voice_bot import VoiceBotMeta
    from models.api_keys import BotAPIKey
    
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session