# models/contact.py
from pydantic import BaseModel, EmailStr, validator
from typing import Optional, List
from datetime import datetime

class ContactForm(BaseModel):
    business_name: str
    first_name: str
    last_name: str
    mobile_number: str
    email: EmailStr
    selected_slot: str
    message: str
    alternative_numbers: Optional[List[str]] = None
    submitted_at: Optional[datetime] = None
    
    @validator('mobile_number')
    def validate_mobile_number(cls, v):
        if not v.replace('+', '').replace(' ', '').isdigit():
            raise ValueError('Mobile number must contain only digits and optional + sign')
        return v
    
    @validator('selected_slot')
    def validate_slot(cls, v):
        if not v or v == "Select date & time":
            raise ValueError('Please select a valid date and time slot')
        return v

class ContactFormResponse(BaseModel):
    success: bool
    message: str
    data: dict