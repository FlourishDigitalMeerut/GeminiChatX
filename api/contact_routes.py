from fastapi import APIRouter, HTTPException, BackgroundTasks, Form
from typing import Optional
from datetime import datetime
import logging

from models.contact import ContactForm, ContactFormResponse
from services.email_service import send_contact_form_email
# from services.mongodb import save_contact_submission  # Optional: if you want to save to MongoDB

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/contact/submit", response_model=ContactFormResponse)
async def submit_contact_form(
    background_tasks: BackgroundTasks,
    business_name: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    mobile_number: str = Form(...),
    email: str = Form(...),
    selected_slot: str = Form(...),
    message: str = Form(...),
    alternative_numbers: Optional[str] = Form("")
):
    """
    Submit contact form. All fields are required except alternative_numbers.
    
    Form Fields:
    - business_name: Business Name
    - first_name: First Name
    - last_name: Last Name
    - mobile_number: Mobile Number (with country code)
    - email: Email ID
    - selected_slot: Selected date & time slot
    - message: Message content
    - alternative_numbers: Comma-separated alternative numbers (optional)
    """
    try:
        # Parse alternative numbers
        alt_numbers_list = []
        if alternative_numbers and alternative_numbers.strip():
            alt_numbers_list = [
                num.strip() for num in alternative_numbers.split(',') 
                if num.strip()
            ]
        
        # Create form data object
        form_data = ContactForm(
            business_name=business_name,
            first_name=first_name,
            last_name=last_name,
            mobile_number=mobile_number,
            email=email,
            selected_slot=selected_slot,
            message=message,
            alternative_numbers=alt_numbers_list if alt_numbers_list else None,
            submitted_at=datetime.now()
        )
        
        # Convert to dict for email and database
        form_dict = form_data.dict()
        
        # Send email in background
        background_tasks.add_task(send_contact_form_email, form_dict)
        
        # Optional: Save to MongoDB if configured
        try:
            # Uncomment if you have MongoDB service
            # background_tasks.add_task(save_contact_submission, form_dict)
            pass
        except Exception as db_error:
            logger.warning(f"Failed to save to database: {db_error}")
        
        return {
            "success": True,
            "message": "Thank you! Your message has been sent successfully.",
            "data": {
                "business_name": form_data.business_name,
                "name": f"{form_data.first_name} {form_data.last_name}",
                "email": form_data.email,
                "slot": form_data.selected_slot,
                "submitted_at": form_data.submitted_at.isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Contact form submission error: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Form submission failed: {str(e)}"
        )

@router.get("/contact/test")
async def test_contact_endpoint():
    """
    Test endpoint to verify contact form API is working
    """
    return {
        "status": "active",
        "service": "Contact Form API",
        "required_fields": [
            "business_name", 
            "first_name", 
            "last_name", 
            "mobile_number", 
            "email", 
            "selected_slot", 
            "message"
        ],
        "optional_fields": ["alternative_numbers"]
    }