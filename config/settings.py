import os
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict

load_dotenv()

# Base directories
BASE_DIR = Path(__file__).parent.parent
BASE_PERSIST_DIR = BASE_DIR / "bots_vectorstores"
BASE_PERSIST_DIR.mkdir(exist_ok=True)

DATABASE_URL = "sqlite:///bots.db"

# API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# GROQ_API_KEY_WEBSITE = os.getenv("GROQ_API_KEY_FOR_WEBSITE_BOT")
# GROQ_API_KEY_WHATSAPP = os.getenv("GROQ_API_KEY_FOR_WHATSAPP_BOT")
# GROQ_API_KEY_VOICE = os.getenv("GROQ_API_KEY_FOR_VOICE_BOT")
META_APP_ID = os.getenv("META_APP_ID")
META_APP_SECRET = os.getenv("META_APP_SECRET")
META_REDIRECT_URL = os.getenv("META_REDIRECT_URL")

# Constants
DEFAULT_FALLBACK = "Sorry, I don't know the answer to that."
BATCH_SIZE = 16
DATABASE_URL = "sqlite:///bots.db"

if not GROQ_API_KEY:
    raise RuntimeError("Set GROQ_API_KEY in environment")

# Add these to your existing settings
PLIVO_AUTH_ID: str = os.getenv("PLIVO_AUTH_ID", "MADUMMYAUTH12345")
PLIVO_AUTH_TOKEN: str = os.getenv("PLIVO_AUTH_TOKEN", "dummy_token_abc123xyz789")
PLIVO_APP_ID: str = os.getenv("PLIVO_APP_ID", "APP_DUMMY_123456789")
PLIVO_PHONE_NUMBER: str = os.getenv("PLIVO_PHONE_NUMBER", "+14151234567")

# Voice Settings
SUPPORTED_LANGUAGES = {
    "en-US": "English (US)",
    "en-GB": "English (UK)", 
    "en-AU": "English (Australia)",
    "en-IN": "English (India)",  # ✅ Indian English
    "hi-IN": "Hindi (India)",    # ✅ Hindi - CONFIRMED SUPPORTED
    "es-ES": "Spanish (Spain)",
    "es-US": "Spanish (US)",
    "es-MX": "Spanish (Mexico)",
    "fr-FR": "French (France)",
    "fr-CA": "French (Canada)", 
    "de-DE": "German (Germany)",
    "pt-BR": "Portuguese (Brazil)",
    "pt-PT": "Portuguese (Portugal)",
    "it-IT": "Italian (Italy)",
    "ja-JP": "Japanese (Japan)",
    "ko-KR": "Korean (South Korea)",
    "cmn-CN": "Chinese Mandarin",
    "nl-NL": "Dutch (Netherlands)",
    "da-DK": "Danish (Denmark)",
    "nb-NO": "Norwegian (Norway)", 
    "sv-SE": "Swedish (Sweden)",
    "pl-PL": "Polish (Poland)",
    "ru-RU": "Russian (Russia)",
    "tr-TR": "Turkish (Turkey)",
    "ro-RO": "Romanian (Romania)",
    "is-IS": "Icelandic (Iceland)",
    "cy-GB": "Welsh (Wales)",
    "arb": "Arabic"
}

VOICE_TYPES = {
    "WOMAN": "Female Voice",
    "MAN": "Male Voice"
}

DEFAULT_VOICE: str = "WOMAN"

LANGUAGE_VOICE_AVAILABILITY = {
    "en-US": ["WOMAN", "MAN"],
    "en-GB": ["WOMAN", "MAN"],
    "en-AU": ["WOMAN", "MAN"],
    "en-IN": ["WOMAN"],  # Only WOMAN for Indian English
    "hi-IN": ["WOMAN"],  # Only WOMAN for Hindi
    "es-ES": ["WOMAN", "MAN"],
    "es-US": ["WOMAN", "MAN"],
    "es-MX": ["WOMAN"],
    "fr-FR": ["WOMAN", "MAN"],
    "fr-CA": ["WOMAN"],
    "de-DE": ["WOMAN", "MAN"],
    "pt-BR": ["WOMAN", "MAN"],
    "pt-PT": ["WOMAN", "MAN"],
    "it-IT": ["WOMAN", "MAN"],
    "ja-JP": ["WOMAN", "MAN"],
    "ko-KR": ["WOMAN"],
    "cmn-CN": ["WOMAN"],
    "nl-NL": ["WOMAN", "MAN"],
    "da-DK": ["WOMAN", "MAN"],
    "nb-NO": ["WOMAN"],
    "sv-SE": ["WOMAN"],
    "pl-PL": ["WOMAN", "MAN"],
    "ru-RU": ["WOMAN", "MAN"],
    "tr-TR": ["WOMAN"],
    "ro-RO": ["WOMAN"],
    "is-IS": ["WOMAN", "MAN"],
    "cy-GB": ["WOMAN"],
    "arb": ["WOMAN"]
}

# MongoDB Configuration
MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "chatbot_db")

# JWT Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your_very_secret_key_here_change_in_production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 180
REFRESH_TOKEN_EXPIRE_DAYS = 10

# Application Configuration
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

# Collections
USERS_COLLECTION = "users"
API_KEYS_COLLECTION = "api_keys"
REFRESH_TOKENS_COLLECTION = "refresh_tokens"
PASSWORD_RESET_SESSIONS_COLLECTION = "password_reset_sessions"

# Meta WhatsApp Settings
META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_REDIRECT_URL = os.getenv("META_REDIRECT_URL", "http://localhost:8000/bots/whatsapp/oauth/callback")
META_SYSTEM_USER_TOKEN = os.getenv("META_SYSTEM_USER_TOKEN", "")
META_WEBHOOK_VERIFY_TOKEN = os.getenv("META_WEBHOOK_VERIFY_TOKEN", "gemini_whatsapp_verify")

# WhatsApp API Version
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v20.0")

# Server URLs
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "http://localhost:8000/bots/whatsapp")