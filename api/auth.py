from fastapi import APIRouter, HTTPException, status, Depends, Header
from models.users import UserCreate, UserResponse, UserLogin, Token
from services.mongodb import get_users_collection
from services.auth import get_current_user, authenticate_user
from services.token_service import TokenService
from utils.security import get_password_hash
from services.api_key_service import api_key_service
from models.database import engine
from models.users import TokenRefresh, ForgotPasswordRequest, VerifyOTPRequest, ResetPasswordRequest
from services.otp_service import OTPService
from datetime import datetime, timezone, timedelta
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])

@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(user: UserCreate):
    users_collection = await get_users_collection()
    
    # Check if user already exists
    existing_user = await users_collection.find_one({
        "$or": [
            {"email": user.email},
            {"username": user.username}
        ]
    })
    if existing_user:
        raise HTTPException(status_code=400, detail="Email or username already registered")
    
    # Create new user
    new_user = {
        "email": user.email,
        "username": user.username,
        "mobile_number": user.mobile_number,
        "hashed_password": get_password_hash(user.password),
        "chatbot_active": True,
        "created_at": datetime.utcnow()
    }
    
    result = await users_collection.insert_one(new_user)
    
    logger.info(f"New user created: {user.email} ({user.username})")
    
    return UserResponse(
        _id=str(result.inserted_id),
        username=user.username,
        mobile_number=user.mobile_number,
        email=user.email,
        chatbot_active=True,
        created_at=new_user["created_at"]
    )

@router.post("/login", response_model=dict)
async def login(user_credentials: UserLogin):
    # Authenticate user
    
    user = await authenticate_user(user_credentials.email, user_credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    tokens = await TokenService.create_tokens_for_user(user)
    
    user_id = str(user["_id"])
    
    logger.info(f"Generating API keys for user: {user_id}")
    try:
        api_keys = api_key_service.generate_all_bot_api_keys(user_id)
    except Exception as e:
        logger.error(f"Failed to generate API keys for user {user_id}: {e}")
        
        api_keys = {
            "website_key": "generation_failed",
            "whatsapp_key": "generation_failed", 
            "voice_key": "generation_failed",
            "virtual_numbers_key": "generation_failed",
            "expires_at": datetime.utcnow() + timedelta(hours=3)
        }
    
    return {
        "message": "Login successful, Welcome!",
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"], 
        "token_type": tokens["token_type"],
        "user_id": user_id,
        "email": user["email"],
        "expires_in": tokens["expires_in"],
        "api_keys": {
            "website_key": api_keys.website_key,
            "whatsapp_key": api_keys.whatsapp_key,
            "voice_key": api_keys.voice_key,
            "virtual_numbers_key": api_keys.virtual_numbers_key,
            "expires_at": api_keys.expires_at.isoformat()
        },
        "instructions": "Use these API keys for respective bot operations. Keys expire in 3 hours."
    }

@router.post("/refresh", response_model=dict)
async def refresh_token(token_data: TokenRefresh):  # Use the model
    """Refresh access token using refresh token"""
    try:
        tokens = await TokenService.refresh_access_token(token_data.refresh_token)
        
        return {
            "message": "Token refreshed successfully",
            "access_token": tokens["access_token"],
            "token_type": tokens["token_type"],
            "expires_in": tokens["expires_in"]
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    
@router.post("/logout")
async def logout(refresh_token: str = None, current_user: dict = Depends(get_current_user)):
    """Logout user and revoke tokens"""
    if refresh_token:
        await TokenService.revoke_refresh_token(refresh_token)
    else:
        # Revoke all user tokens
        await TokenService.revoke_all_user_tokens(str(current_user["_id"]))
    
    return {"message": "Successfully logged out"}

@router.get("/user-detail", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information"""
    return UserResponse(
        _id=str(current_user["_id"]),
        email=current_user["email"],
        username=current_user["username"],
        mobile_number=current_user["mobile_number"],
        chatbot_active=current_user.get("chatbot_active", True),
        created_at=current_user["created_at"]
    )

@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    """Step 1: Verify email exists + Send OTP"""
    try:
        session_token = str(uuid.uuid4())
        
        from services.mongodb import get_password_reset_sessions_collection
        sessions_collection = await get_password_reset_sessions_collection()
        
        await sessions_collection.insert_one({
            "session_token": session_token,
            "email": request.email,
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
            "used": False,
            "otp_verified": False
        })
        
        result = await OTPService.create_otp_for_user(request.email, session_token)
        
        return {
            "success": True, 
            "message": "OTP sent to your email successfully",
            "session_token": session_token
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in forgot password: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/resend-otp")
async def resend_otp(
    x_session_token: str = Header(..., alias="X-Session-Token")
):
    """Resend OTP using existing session token"""
    try:
        result = await OTPService.resend_otp(x_session_token)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resending OTP: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/verify-otp")
async def verify_otp(
    request: VerifyOTPRequest,
    x_session_token: str = Header(..., alias="X-Session-Token")
):
    """Step 2: Verify OTP using session token"""
    try:
        result = await OTPService.verify_otp(x_session_token, request.otp)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying OTP: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    x_session_token: str = Header(..., alias="X-Session-Token")
):
    """Step 3: Reset password using session token"""
    try:
        if len(request.new_password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")
        
        result = await OTPService.reset_password(x_session_token, request.new_password)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting password: {e}")
        raise HTTPException(status_code=500, detail="Error resetting password")