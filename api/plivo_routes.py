from fastapi import APIRouter, HTTPException, Depends, Query, Body, UploadFile, File, Form, Header
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
import re
from sqlmodel import Session, select # pyright: ignore[reportMissingImports]
from models.database import engine
from models.plivo_numbers import AccountPhoneNumber, IncomingCarrier, NumberStatus
from managers.voice_bot_manager import voice_bot_manager
from api.dependencies import get_current_user_from_api_key, validate_virtual_numbers_api_key
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/plivo", tags=["number-management"])

class SearchNumbersRequest(BaseModel):
    country_iso: str
    number_type: str = "local"
    pattern: Optional[str] = None
    region: Optional[str] = None
    services: List[str] = ["voice"]

class BuyNumberRequest(BaseModel):
    phone_number: str
    alias: Optional[str] = None

class AssignNumberToBotRequest(BaseModel):
    number_id: int
    bot_id: int

class SetDefaultNumberRequest(BaseModel):
    number_id: int

class UpdateNumberRequest(BaseModel):
    alias: Optional[str] = None
    # assignment_type: Optional[str] = None
    # campaign_tag: Optional[str] = None

# class CreateCarrierRequest(BaseModel):
#     carrier_name: str = Field(..., description="Name of the carrier")
#     ip_set: List[str] = Field(..., description="Comma-separated list of IP addresses")
    
#     @validator('carrier_name')
#     def validate_carrier_name(cls, v):
#         # Only allow alphanumeric, hyphen, and underscore characters
#         if not re.match(r'^[a-zA-Z0-9_-]+$', v):
#             raise ValueError('Carrier name can only contain alphanumeric characters, hyphens, and underscores')
#         return v

# class UpdateCarrierRequest(BaseModel):
#     name: Optional[str] = Field(None, description="Name of the carrier")
#     ip_set: Optional[List[str]] = Field(None, description="Comma-separated list of IP addresses (replaces entire set)")
    
#     @validator('name')
#     def validate_carrier_name(cls, v):
#         if v is not None:
#             # Only allow alphanumeric, hyphen, and underscore characters
#             if not re.match(r'^[a-zA-Z0-9_-]+$', v):
#                 raise ValueError('Carrier name can only contain alphanumeric characters, hyphens, and underscores')
#         return v

# class AddNumberFromCarrierRequest(BaseModel):
#     phone_numbers: List[str] = Field(..., description="Comma-separated list of numbers to add")
#     carrier: str = Field(..., description="ID of the IncomingCarrier")
#     region: str = Field(..., description="Free-text field to describe region")
#     number_type: str = Field("local", description="Type: local, tollfree, mobile, national, or fixed")
#     alias: Optional[str] = None

@router.get("/numbers/search")
async def search_available_numbers(
    country_iso: str = Query(..., description="ISO country code (e.g., US, IN)"),
    number_type: str = Query("local", description="local, tollfree, mobile, national, fixed"),
    pattern: Optional[str] = Query(None, description="Pattern to match in number"),
    region: Optional[str] = Query(None, description="Region/state code"),
    services: List[str] = Query(["voice"], description="Services needed"),
    x_api_key: str = Header(None, alias="X-API-Key")  
):
    """Search for available phone numbers"""
    
    await validate_virtual_numbers_api_key(x_api_key)
    
    try:
        numbers = voice_bot_manager.search_available_numbers(
            country_iso=country_iso,
            number_type=number_type,
            pattern=pattern,
            region=region,
            services=services
        )
        
        return {
            "count": len(numbers),
            "numbers": numbers,
            "note": "Numbers purchased will be billed to GeminiChatX and assigned to your account"
        }
        
    except Exception as e:
        logger.error(f"Error searching numbers: {e}")
        raise HTTPException(500, f"Error searching numbers: {str(e)}")

@router.post("/numbers/buy")
async def buy_phone_number(
    req: BuyNumberRequest,
    x_api_key: str = Header(None, alias="X-API-Key") 
):
    """Buy a phone number and assign to current user"""
    
    api_key_info = await validate_virtual_numbers_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    if not req.phone_number.startswith("+"):
        raise HTTPException(400, "Phone number must be in E.164 format (e.g., +14151234567)")
    
    result = voice_bot_manager.buy_phone_number_for_user(
        user_id=user_id,
        number=req.phone_number,
        alias=req.alias
    )
    
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to buy number"))
    
    # Check if number requires verification/compliance documents
    number_status = result.get("status", "Success")
    
    response_data = {
        "message": "Phone number purchased successfully and assigned to your account",
        "data": result
    }
    
    # Handle pending verification status
    if number_status == "pending":
        response_data["message"] = "Phone number purchased but requires verification documents before activation"
        response_data["verification_required"] = True
        response_data["compliance_status"] = "pending"
        response_data["next_steps"] = (
    "Contact GeminichatX support with your verification documents. "
    "We will submit them on your behalf."
)
    
    return response_data

@router.get("/numbers/my-numbers")
async def get_my_numbers(
    active_only: bool = Query(True),
    number_type: Optional[str] = Query(None),
    x_api_key: str = Header(None, alias="X-API-Key")  
):
    """Get all phone numbers assigned to current user"""
    
    api_key_info = await validate_virtual_numbers_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    numbers = voice_bot_manager.get_user_numbers(
        user_id=user_id,
        active_only=active_only,
        number_type=number_type
    )
    
    return {
        "user_id": user_id,
        "count": len(numbers),
        "numbers": [
            {
                "id": n.id,
                "phone_number": n.phone_number,
                "alias": n.alias,
                "number_type": n.number_type.value,
                "country": n.country_iso,
                "city": n.city,
                "monthly_cost": n.monthly_rental_rate,
                "status": n.status.value,
                "assignment_type": n.assignment_type.value,
                "assigned_bot": n.assigned_bot_id,
                "is_default": n.is_default,
                "usage_stats": n.usage_stats_dict,
                "created_at": n.created_at
            }
            for n in numbers
        ]
    }

@router.post("/numbers/assign-to-bot")
async def assign_number_to_bot(
    req: AssignNumberToBotRequest,
    x_api_key: str = Header(None, alias="X-API-Key")  
):
    """Assign one of your numbers to a specific bot (dedicated use)"""
    
    api_key_info = await validate_virtual_numbers_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    success = voice_bot_manager.assign_number_to_bot(
        user_id=user_id,
        number_id=req.number_id,
        bot_id=req.bot_id
    )
    
    if not success:
        raise HTTPException(400, "Failed to assign number to bot. Check ownership.")
    
    return {
        "message": "Number assigned to bot successfully",
        "bot_id": req.bot_id,
        "number_id": req.number_id
    }

@router.post("/numbers/release-from-bot")
async def release_number_from_bot(
    number_id: int = Body(..., embed=True),
    x_api_key: str = Header(None, alias="X-API-Key")  
):
    """Release a number from bot assignment (back to your pool)"""
    
    api_key_info = await validate_virtual_numbers_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    success = voice_bot_manager.release_number_from_bot(
        user_id=user_id,
        number_id=number_id
    )
    
    if not success:
        raise HTTPException(400, "Failed to release number")
    
    return {"message": "Number released and available in your pool"}

@router.post("/numbers/set-default")
async def set_default_number(
    req: SetDefaultNumberRequest,
    x_api_key: str = Header(None, alias="X-API-Key")  
):
    """Set your default phone number for calls"""
    
    api_key_info = await validate_virtual_numbers_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    success = voice_bot_manager.set_default_number(
        user_id=user_id,
        number_id=req.number_id
    )
    
    if not success:
        raise HTTPException(400, "Failed to set default number")
    
    return {"message": "Default number updated successfully"}

@router.put("/numbers/{number_id}")
async def update_phone_number(
    number_id: int,
    req: UpdateNumberRequest,
    x_api_key: str = Header(None, alias="X-API-Key")  
):
    """Update phone number settings"""
    
    api_key_info = await validate_virtual_numbers_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    with Session(engine) as session:
        number = session.exec(
            select(AccountPhoneNumber).where(
                AccountPhoneNumber.id == number_id,
                AccountPhoneNumber.user_id == user_id
            )
        ).first()
        
        if not number:
            raise HTTPException(404, "Number not found or not owned by you")
        
        if req.alias is not None:
            number.alias = req.alias
        
        # if req.assignment_type is not None:
        #     number.assignment_type = req.assignment_type
        
        # if req.campaign_tag is not None:
        #     number.campaign_tag = req.campaign_tag
        
        session.add(number)
        session.commit()
        
        return {
            "message": "Number updated successfully",
            "number_id": number_id,
            "alias": number.alias
            # "assignment_type": number.assignment_type
        }

@router.delete("/numbers/{number_id}")
async def unrent_phone_number(
    number_id: int,
    x_api_key: str = Header(None, alias="X-API-Key")  
):
    """Release/unrent a phone number"""
    
    api_key_info = await validate_virtual_numbers_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    success = voice_bot_manager.unrent_number(
        user_id=user_id,
        number_id=number_id
    )
    
    if not success:
        raise HTTPException(400, "Failed to release number")
    
    return {"message": "Phone number released successfully"}

# # ========== CARRIER ROUTES ==========

# @router.post("/carriers")
# async def create_incoming_carrier(
#     req: CreateCarrierRequest,
#     x_api_key: str = Header(None, alias="X-API-Key")  
# ):
#     """Create an incoming carrier (BYOC - Bring Your Own Carrier)"""
    
#     api_key_info = await validate_virtual_numbers_api_key(x_api_key)
#     user_id = api_key_info["user_id"]
    
#     result = voice_bot_manager.create_incoming_carrier(
#         user_id=user_id,
#         carrier_name=req.carrier_name,
#         ip_set=req.ip_set,
#         prefix_set=[],  # Removed as per Plivo API
#         failover_carrier=None  # Removed as per Plivo API
#     )
    
#     if not result.get("success"):
#         raise HTTPException(400, result.get("error", "Failed to create carrier"))
    
#     return {
#         "message": "Incoming carrier created successfully",
#         "carrier_id": result["carrier_id"]
#     }

# @router.get("/carriers")
# async def list_all_carriers(
#     name: Optional[str] = Query(None, description="Filter by carrier name"),
#     limit: int = Query(20, description="Max 20 results per page", ge=1, le=20),
#     offset: int = Query(0, description="Offset for pagination", ge=0),
#     x_api_key: str = Header(None, alias="X-API-Key")  
# ):
#     """List all incoming carriers"""
    
#     api_key_info = await validate_virtual_numbers_api_key(x_api_key)
#     user_id = api_key_info["user_id"]
    
#     carriers = voice_bot_manager.list_incoming_carriers(
#         user_id=user_id,
#         name_filter=name,
#         limit=limit,
#         offset=offset
#     )
    
#     return {
#         "user_id": user_id,
#         "count": len(carriers),
#         "limit": limit,
#         "offset": offset,
#         "carriers": [
#             {
#                 "id": c.id,
#                 "carrier_id": c.carrier_id,
#                 "name": c.carrier_name,
#                 "ip_set": c.ip_set.split(",") if c.ip_set else [],
#                 "prefix_set": c.prefix_set.split(",") if c.prefix_set else [],
#                 "failover_carrier": c.failover_carrier,
#                 "is_active": c.is_active,
#                 "created_at": c.created_at,
#                 "updated_at": c.updated_at
#             }
#             for c in carriers
#         ],
#         "pagination": {
#             "next_offset": offset + limit if len(carriers) == limit else None,
#             "has_more": len(carriers) == limit
#         }
#     }

# @router.get("/carriers/{carrier_id}")
# async def retrieve_incoming_carrier(
#     carrier_id: str,
#     x_api_key: str = Header(None, alias="X-API-Key")  
# ):
#     """Retrieve details of a specific incoming carrier"""
    
#     api_key_info = await validate_virtual_numbers_api_key(x_api_key)
#     user_id = api_key_info["user_id"]
    
#     carrier = voice_bot_manager.get_incoming_carrier(
#         user_id=user_id,
#         carrier_id=carrier_id
#     )
    
#     if not carrier:
#         raise HTTPException(404, f"Carrier {carrier_id} not found")
    
#     return {
#         "carrier": {
#             "id": carrier.id,
#             "carrier_id": carrier.carrier_id,
#             "name": carrier.carrier_name,
#             "ip_set": carrier.ip_set.split(",") if carrier.ip_set else [],
#             "prefix_set": carrier.prefix_set.split(",") if carrier.prefix_set else [],
#             "failover_carrier": carrier.failover_carrier,
#             "is_active": carrier.is_active,
#             "created_at": carrier.created_at,
#             "updated_at": carrier.updated_at
#         }
#     }

# @router.put("/carriers/{carrier_id}")
# async def update_incoming_carrier(
#     carrier_id: str,
#     req: UpdateCarrierRequest,
#     x_api_key: str = Header(None, alias="X-API-Key")  
# ):
#     """Update an existing incoming carrier"""
    
#     api_key_info = await validate_virtual_numbers_api_key(x_api_key)
#     user_id = api_key_info["user_id"]
    
#     ip_set_str = ",".join(req.ip_set) if req.ip_set else None
    
#     result = voice_bot_manager.update_incoming_carrier(
#         user_id=user_id,
#         carrier_id=carrier_id,
#         name=req.name,
#         ip_set=ip_set_str
#     )
    
#     if not result.get("success"):
#         raise HTTPException(400, result.get("error", "Failed to update carrier"))
    
#     return {
#         "message": "Incoming carrier updated successfully",
#         "carrier_id": carrier_id
#     }

# @router.delete("/carriers/{carrier_id}")
# async def delete_incoming_carrier(
#     carrier_id: str,
#     x_api_key: str = Header(None, alias="X-API-Key")  
# ):
#     """Delete an incoming carrier"""
    
#     api_key_info = await validate_virtual_numbers_api_key(x_api_key)
#     user_id = api_key_info["user_id"]
    
#     result = voice_bot_manager.delete_incoming_carrier(
#         user_id=user_id,
#         carrier_id=carrier_id
#     )
    
#     if not result.get("success"):
#         raise HTTPException(400, result.get("error", "Failed to delete carrier"))
    
#     return {
#         "message": "Incoming carrier deleted successfully",
#         "warning": "All numbers associated with this carrier have been removed",
#         "carrier_id": carrier_id
#     }

# @router.post("/carriers/{carrier_id}/numbers")
# async def add_numbers_from_carrier(
#     carrier_id: str,
#     req: AddNumberFromCarrierRequest,
#     x_api_key: str = Header(None, alias="X-API-Key")  
# ):
#     """Add phone numbers from your own carrier to your account"""
    
#     api_key_info = await validate_virtual_numbers_api_key(x_api_key)
#     user_id = api_key_info["user_id"]
    
#     carrier = voice_bot_manager.get_incoming_carrier(user_id, carrier_id)
#     if not carrier:
#         raise HTTPException(404, f"Carrier {carrier_id} not found")
    
#     results = []
#     for phone_number in req.phone_numbers:
#         result = voice_bot_manager.add_number_from_carrier(
#             user_id=user_id,
#             phone_number=phone_number,
#             carrier_id=carrier_id,
#             region=req.region,
#             number_type=req.number_type,
#             alias=req.alias
#         )
#         results.append({
#             "phone_number": phone_number,
#             "success": result.get("success", False),
#             "error": result.get("error")
#         })
    
#     success_count = sum(1 for r in results if r["success"])
    
#     return {
#         "message": f"Added {success_count}/{len(req.phone_numbers)} numbers from carrier",
#         "carrier_id": carrier_id,
#         "region": req.region,
#         "number_type": req.number_type,
#         "results": results
#     }

# ========== UTILITY ROUTES ==========

@router.get("/numbers/verify-requirements/{country_iso}")
async def get_verification_requirements(
    country_iso: str,
    x_api_key: str = Header(None, alias="X-API-Key"),
    number_type: str = Query("local", description="Type of number: local, tollfree, mobile, national, fixed"),
    services: str = Query("voice,sms", description="Services needed (voice,sms,mms)")
):
    """Check verification requirements for a specific country"""
    
    await validate_virtual_numbers_api_key(x_api_key)
    
    try:
        search_result = voice_bot_manager.search_available_numbers(
            country_iso=country_iso.upper(),
            number_type=number_type,
            pattern=None,
            region=None,
            services=[services]
        )
        
        if not search_result:
            return {
                "country": country_iso,
                "verification_required": "unknown",
                "available_numbers": 0,
                "note": f"No {number_type} numbers available for {country_iso}."
            }
        
        verification_required = "unknown"
        restriction_details = []
        compliance_requirements = []
        
        for num in search_result[:5]:
            restriction = num.get('restriction', '') if isinstance(num, dict) else ''
            restriction_text = num.get('restriction_text', '') if isinstance(num, dict) else ''
            compliance_req = num.get('compliance_requirement', '') if isinstance(num, dict) else ''
            
            if restriction:
                verification_required = "yes"
                if restriction_text and restriction_text not in restriction_details:
                    restriction_details.append(restriction_text)
            
            if compliance_req and compliance_req not in compliance_requirements:
                compliance_requirements.append(compliance_req)
        
        if verification_required == "unknown":
            high_restriction_countries = ["US", "CA", "GB", "AU", "IN", "DE", "FR", "IT", "ES", "JP", "KR"]
            if country_iso.upper() in high_restriction_countries:
                verification_required = "likely"
                restriction_details.append(f"{country_iso} typically requires business verification")
            else:
                verification_required = "no"
                restriction_details.append("No specific verification required")
        
        return {
            "country": country_iso,
            "country_name": _get_country_name(country_iso),
            "verification_required": verification_required,
            "number_type": number_type,
            "available_numbers": len(search_result),
            "restriction_details": restriction_details,
            "compliance_requirements": compliance_requirements
        }
        
    except Exception as e:
        logger.error(f"Error checking verification requirements: {e}")
        return {
            "country": country_iso,
            "verification_required": "unknown",
            "error": str(e)
        }
    
@router.get("/numbers/usage/{number_id}")
async def get_number_usage(
    number_id: int,
    x_api_key: str = Header(None, alias="X-API-Key")  
):
    """Get usage statistics for a specific number"""
    
    api_key_info = await validate_virtual_numbers_api_key(x_api_key)
    user_id = api_key_info["user_id"]
    
    with Session(engine) as session:
        number = session.exec(
            select(AccountPhoneNumber).where(
                AccountPhoneNumber.id == number_id,
                AccountPhoneNumber.user_id == user_id
            )
        ).first()
        
        if not number:
            raise HTTPException(404, "Number not found or not owned by you")
        
        return {
            "number_id": number_id,
            "phone_number": number.phone_number,
            "alias": number.alias,
            "usage_stats": number.usage_stats_dict,
            "last_used": number.usage_stats_dict.get("last_used"),
            "success_rate": number.usage_stats_dict.get("success_rate", 100),
            "total_calls": number.usage_stats_dict.get("total_calls", 0)
        }
    
def _get_country_name(country_code: str) -> str:
    """Get country name from ISO code"""
    country_names = {
        "US": "United States",
        "CA": "Canada", 
        "GB": "United Kingdom",
        "IN": "India",
        "AU": "Australia",
        "DE": "Germany",
        "FR": "France",
        "IT": "Italy",
        "ES": "Spain",
        "JP": "Japan",
        "KR": "South Korea",
        "CN": "China",
        "BR": "Brazil",
        "MX": "Mexico",
    }
    return country_names.get(country_code.upper(), country_code)