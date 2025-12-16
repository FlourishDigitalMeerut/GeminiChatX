from typing import Optional
from sqlmodel import SQLModel, Field # pyright: ignore[reportMissingImports]
import secrets
from config.settings import DEFAULT_FALLBACK
from datetime import datetime

class WebsiteBotMeta(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    owner: Optional[str] = None
    persist_dir: str
    framework: Optional[str] = None
    api_key: str = Field(default_factory=lambda: "aIWeBCb_" + secrets.token_hex(32))
    fallback_response: str = Field(default=DEFAULT_FALLBACK)
    is_active: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)