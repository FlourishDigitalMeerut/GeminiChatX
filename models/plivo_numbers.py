from sqlmodel import SQLModel, Field, Relationship # pyright: ignore[reportMissingImports]
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import json

class NumberType(str, Enum):
    LOCAL = "local"
    TOLLFREE = "tollfree"
    MOBILE = "mobile"
    FIXED = "fixed"

class NumberStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    RELEASED = "released"
    RESERVED = "reserved"
    DISABLED = "disabled"

class NumberAssignment(str, Enum):
    POOLED = "pooled"  # Any bot can use
    DEDICATED = "dedicated"  # Assigned to specific bot
    CAMPAIGN = "campaign"  # For specific campaign

class AccountPhoneNumber(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)  # Links to user/owner
    plivo_number_id: str  # Plivo's internal ID
    phone_number: str  # E.164 format: +14151234567
    alias: Optional[str] = None  # User-friendly name
    number_type: NumberType
    country_iso: str  # ISO country code
    city: Optional[str] = None
    region: Optional[str] = None
    monthly_rental_rate: float
    setup_rate: float
    voice_enabled: bool = True
    sms_enabled: bool = True
    status: NumberStatus = NumberStatus.PENDING
    assignment_type: NumberAssignment = NumberAssignment.POOLED
    assigned_bot_id: Optional[int] = None  # If dedicated to specific bot
    campaign_tag: Optional[str] = None  # For campaign-specific numbers
    is_default: bool = False  # Default number for user
    plivo_app_id: Optional[str] = None  # Associated Plivo application
    usage_stats: str = Field(default="{}")  # JSON stats
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    @property
    def usage_stats_dict(self) -> Dict[str, Any]:
        return json.loads(self.usage_stats) if self.usage_stats else {}
    
    @usage_stats_dict.setter
    def usage_stats_dict(self, value: Dict[str, Any]):
        self.usage_stats = json.dumps(value)

class IncomingCarrier(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)  # Carrier belongs to user
    carrier_name: str
    carrier_id: str  # Plivo carrier ID
    ip_set: str  # Comma-separated IP addresses
    prefix_set: str  # Comma-separated prefixes
    failover_carrier: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)