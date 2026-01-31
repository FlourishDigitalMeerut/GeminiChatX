import secrets
import logging
import time
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from services.mongodb import get_users_collection, get_password_reset_sessions_collection
from services.email_sender import email_sender
from utils.security import get_password_hash, verify_password
from collections import defaultdict
import hashlib

logger = logging.getLogger(__name__)

class OTPRateLimiter:
    def __init__(self):
        # Store: email -> {last_request_time, request_count, failed_attempts, locked_until, current_otp, otp_expires}
        self.rate_limit_data = defaultdict(lambda: {
            'last_request_time': 0,
            'request_count': 0,
            'failed_attempts': 0,
            'locked_until': 0,
            'current_otp': None,
            'otp_expires': 0,
            'session_token': None,
            'otp_verified': False
        })
    
    def is_locked(self, email: str) -> bool:
        """Check if email is currently locked"""
        data = self.rate_limit_data[email]
        if data['locked_until'] > time.time():
            return True
        # Reset failed attempts if lock period expired
        if data['locked_until'] > 0 and data['locked_until'] <= time.time():
            data['failed_attempts'] = 0
            data['locked_until'] = 0
        return False
    
    def check_cooldown(self, email: str) -> bool:
        """Check if 1-minute cooldown has passed since last request"""
        data = self.rate_limit_data[email]
        current_time = time.time()
        return current_time - data['last_request_time'] >= 60
    
    def check_hourly_limit(self, email: str) -> bool:
        """Check if user has exceeded 3 requests per hour"""
        data = self.rate_limit_data[email]
        # Reset count if it's been more than 1 hour since first request
        if data['last_request_time'] > 0 and (time.time() - data['last_request_time']) >= 3600:
            data['request_count'] = 0
        return data['request_count'] < 3
    
    def set_otp(self, email: str, session_token: str, otp: str):
        """Store OTP in memory (not database)"""
        data = self.rate_limit_data[email]
        data['current_otp'] = otp
        data['otp_expires'] = time.time() + 600  # 10 minutes
        data['session_token'] = session_token
        data['otp_verified'] = False
        data['last_request_time'] = time.time()
        data['request_count'] += 1
    
    def verify_otp(self, email: str, session_token: str, otp: str) -> bool:
        """Verify OTP from memory"""
        data = self.rate_limit_data[email]
        
        # Check if session token matches
        if data['session_token'] != session_token:
            return False
        
        # Check if OTP exists and is not expired
        if not data['current_otp'] or time.time() > data['otp_expires']:
            return False
        
        # Verify OTP
        if data['current_otp'] != otp:
            data['failed_attempts'] += 1
            if data['failed_attempts'] >= 5:
                data['locked_until'] = time.time() + 900  # 15 minutes lock
            return False
        
        # OTP is valid
        data['otp_verified'] = True
        data['failed_attempts'] = 0
        data['locked_until'] = 0
        return True
    
    def mark_otp_verified(self, email: str):
        """Mark OTP as verified"""
        data = self.rate_limit_data[email]
        data['otp_verified'] = True
    
    def is_otp_verified(self, email: str, session_token: str) -> bool:
        """Check if OTP is verified for session"""
        data = self.rate_limit_data[email]
        return data['otp_verified'] and data['session_token'] == session_token
    
    def clear_otp_data(self, email: str):
        """Clear OTP data after successful password reset"""
        if email in self.rate_limit_data:
            del self.rate_limit_data[email]

# Global instance
otp_rate_limiter = OTPRateLimiter()

class OTPService:
    
    @staticmethod
    def generate_otp(length=6):
        """Generate a numeric OTP"""
        return ''.join([str(secrets.randbelow(10)) for _ in range(length)])
    
    @staticmethod
    async def create_otp_for_user(email: str, session_token: str):
        """Create and send OTP with rate limiting"""
        try:
            # Check rate limits
            if otp_rate_limiter.is_locked(email):
                remaining_time = otp_rate_limiter.rate_limit_data[email]['locked_until'] - time.time()
                raise HTTPException(
                    status_code=429, 
                    detail=f"Too many failed attempts. Try again in {int(remaining_time/60)} minutes"
                )
            
            if not otp_rate_limiter.check_cooldown(email):
                raise HTTPException(
                    status_code=429, 
                    detail="Please wait 1 minute before requesting another OTP"
                )
            
            if not otp_rate_limiter.check_hourly_limit(email):
                raise HTTPException(
                    status_code=429, 
                    detail="Maximum 3 OTP requests per hour exceeded"
                )
            
            users_collection = await get_users_collection()
            
            # Check if user exists (but don't reveal it)
            user = await users_collection.find_one({"email": email})
            if not user:
                # Security: don't reveal if email exists, but still apply rate limiting
                otp_rate_limiter.rate_limit_data[email]['request_count'] += 1
                otp_rate_limiter.rate_limit_data[email]['last_request_time'] = time.time()
                return {"success": True, "message": "If the email exists, OTP has been sent"}
            
            # Generate OTP
            otp = OTPService.generate_otp()
            
            # Store OTP in memory (not database)
            otp_rate_limiter.set_otp(email, session_token, otp)
            
            # Send OTP via email
            email_sent = await email_sender.send_otp_email(email, otp)
            
            if not email_sent:
                # Fallback: log OTP for development
                logger.info(f"OTP for {email}: {otp}")
                return {
                    "success": True,
                    "message": "OTP generated (check logs for development)",
                    "development_otp": otp  # Remove in production
                }
            
            return {
                "success": True,
                "message": "OTP sent to your email successfully"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating OTP: {e}")
            raise HTTPException(status_code=500, detail="Error generating OTP")
    
    @staticmethod
    async def resend_otp(session_token: str):
        """Resend OTP using existing session token"""
        try:
            sessions_collection = await get_password_reset_sessions_collection()
            
            # Verify session token is valid and not expired
            session = await sessions_collection.find_one({
                "session_token": session_token,
                "used": False,
                "expires_at": {"$gt": datetime.now(timezone.utc)}
            })
            
            if not session:
                raise HTTPException(status_code=400, detail="Invalid or expired session token")
            
            email = session["email"]
            
            # Check rate limits for resend
            if otp_rate_limiter.is_locked(email):
                remaining_time = otp_rate_limiter.rate_limit_data[email]['locked_until'] - time.time()
                raise HTTPException(
                    status_code=429, 
                    detail=f"Too many failed attempts. Try again in {int(remaining_time/60)} minutes"
                )
            
            if not otp_rate_limiter.check_cooldown(email):
                raise HTTPException(
                    status_code=429, 
                    detail="Please wait 1 minute before requesting another OTP"
                )
            
            if not otp_rate_limiter.check_hourly_limit(email):
                raise HTTPException(
                    status_code=429, 
                    detail="Maximum 3 OTP requests per hour exceeded"
                )
            
            # Generate new OTP
            otp = OTPService.generate_otp()
            
            # Store new OTP in memory
            otp_rate_limiter.set_otp(email, session_token, otp)
            
            # Send new OTP via email
            email_sent = await email_sender.send_otp_email(email, otp)
            
            if not email_sent:
                logger.info(f"Resent OTP for {email}: {otp}")
                return {
                    "success": True,
                    "message": "OTP regenerated (check logs for development)",
                    "development_otp": otp
                }
            
            return {
                "success": True,
                "message": "New OTP sent to your email successfully"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error resending OTP: {e}")
            raise HTTPException(status_code=500, detail="Error resending OTP")
    
    @staticmethod
    async def verify_otp(session_token: str, otp: str):
        """Verify OTP using session token"""
        try:
            sessions_collection = await get_password_reset_sessions_collection()
            
            # Verify session token is valid
            session = await sessions_collection.find_one({
                "session_token": session_token,
                "used": False,
                "expires_at": {"$gt": datetime.now(timezone.utc)}
            })
            
            if not session:
                raise HTTPException(status_code=400, detail="Invalid or expired session token")
            
            email = session["email"]
            
            # Check if locked due to too many failed attempts
            if otp_rate_limiter.is_locked(email):
                remaining_time = otp_rate_limiter.rate_limit_data[email]['locked_until'] - time.time()
                raise HTTPException(
                    status_code=429, 
                    detail=f"Too many failed attempts. Try again in {int(remaining_time/60)} minutes"
                )
            
            # Verify OTP from memory
            if not otp_rate_limiter.verify_otp(email, session_token, otp):
                data = otp_rate_limiter.rate_limit_data[email]
                remaining_attempts = 5 - data['failed_attempts']
                
                if data['failed_attempts'] >= 5:
                    raise HTTPException(
                        status_code=429, 
                        detail="Too many failed OTP attempts. Account locked for 15 minutes."
                    )
                else:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Invalid OTP. {remaining_attempts} attempts remaining"
                    )
            
            # Mark OTP as verified
            otp_rate_limiter.mark_otp_verified(email)
            
            return {"success": True, "message": "OTP verified successfully"}
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error verifying OTP: {e}")
            raise HTTPException(status_code=500, detail="Error verifying OTP")
    
    @staticmethod
    async def reset_password(session_token: str, new_password: str):
        """Reset password using session token after OTP verification"""
        try:
            users_collection = await get_users_collection()
            sessions_collection = await get_password_reset_sessions_collection()
            
            # Verify session token and check OTP verification
            session = await sessions_collection.find_one({
                "session_token": session_token,
                "used": False,
                "expires_at": {"$gt": datetime.now(timezone.utc)}
            })
            
            if not session:
                raise HTTPException(status_code=400, detail="Invalid or expired session token")
            
            email = session["email"]
            
            # Check if OTP was verified in memory
            if not otp_rate_limiter.is_otp_verified(email, session_token):
                raise HTTPException(status_code=400, detail="OTP not verified. Please verify OTP first.")
            
            # Get user from database
            user = await users_collection.find_one({"email": email})
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Validate password strength
            if len(new_password) < 6:
                raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
            
            # Check if new password is same as old password
            if verify_password(new_password, user.get("hashed_password", "")):
                raise HTTPException(status_code=400, detail="New password cannot be the same as the old password")
            
            # Hash new password and update ONLY the password in database
            hashed_password = get_password_hash(new_password)
            await users_collection.update_one(
                {"email": email},
                {"$set": {
                    "hashed_password": hashed_password,
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
            
            # Mark session as used
            await sessions_collection.update_one(
                {"session_token": session_token},
                {"$set": {"used": True}}
            )
            
            # Clear OTP data from memory
            otp_rate_limiter.clear_otp_data(email)
            
            return {"success": True, "message": "Password reset successfully"}
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error resetting password: {e}")
            raise HTTPException(status_code=500, detail="Error resetting password")