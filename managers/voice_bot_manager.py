import os
import secrets
import json
from typing import Optional, Dict, List, Any
from sqlmodel import Session, select # pyright: ignore[reportMissingImports]
from models.database import engine
from models.voice_bot import VoiceBotMeta
from bots.voice_bot import VoiceBot
from models.voice_bot import VoiceCallAnalytics
from models.plivo_numbers import AccountPhoneNumber, IncomingCarrier, NumberStatus, NumberType, NumberAssignment
from config.settings import PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN, DEFAULT_FALLBACK
import plivo # pyright: ignore[reportMissingImports]
from datetime import datetime

class VoiceBotManager:
    def __init__(self):
        self.bots: Dict[int, VoiceBot] = {}
        # self.plivo_client = plivo.RestClient(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN)
    
    # ========== BASIC BOT METHODS ==========
    def create_basic_bot(self, name: str, company_name: str, owner: Optional[str] = None) -> VoiceBotMeta:
        """Create bot with basic info only"""
        
        with Session(engine) as session:
            # Create persist directory
            persist_dir = f"data/voice_bots/{secrets.token_hex(8)}"
            os.makedirs(persist_dir, exist_ok=True)
            
            # Generate API key
            api_key = "aIVoice_" + secrets.token_hex(32)
            
            bot_meta = VoiceBotMeta(
                name=name,
                owner=owner,
                company_name=company_name,
                api_key=api_key,
                fallback_response=DEFAULT_FALLBACK, #By Default
                language="en-IN",  # By Default
                voice_type="WOMAN",  # By Default
                persist_dir=persist_dir,
                is_active=False # By Default
            )
            
            session.add(bot_meta)
            session.commit()
            session.refresh(bot_meta)
            
            # Create Plivo application
            try:
                app_response = self.plivo_client.applications.create(
                    app_name=f"voice-bot-{bot_meta.id}",
                    answer_url=f"http://your-domain.com/api/v1/bots/voice/{bot_meta.id}/call-answer",
                    answer_method="GET",
                    hangup_url=f"http://your-domain.com/api/v1/bots/voice/{bot_meta.id}/call-hangup",
                    hangup_method="POST"
                )
                
                bot_meta.plivo_app_id = app_response.app_id
                session.add(bot_meta)
                session.commit()
                
            except Exception as e:
                print(f"Plivo app creation failed: {e}")
            
            # Create bot instance with default values
            bot = VoiceBot(bot_meta)
            self.bots[bot_meta.id] = bot
            
            return bot_meta
    
    def create(self, name: str, owner: Optional[str] = None, 
               fallback_response: str = DEFAULT_FALLBACK,
               language: str = "en-IN", voice_type: str = "WOMAN") -> VoiceBotMeta:
        """Legacy method for backward compatibility"""
        return self.create_basic_bot(name, owner)
    
    def get(self, bot_id: int) -> Optional[VoiceBot]:
        if bot_id in self.bots:
            return self.bots[bot_id]
        
        with Session(engine) as session:
            bot_meta = session.exec(select(VoiceBotMeta).where(VoiceBotMeta.id == bot_id)).first()
            if bot_meta:
                bot = VoiceBot(bot_meta)
                self.bots[bot_id] = bot
                return bot
        return None
    
    def get_by_api_key(self, api_key: str) -> Optional[VoiceBot]:
        with Session(engine) as session:
            bot_meta = session.exec(select(VoiceBotMeta).where(VoiceBotMeta.api_key == api_key)).first()
            if bot_meta:
                return self.get(bot_meta.id)
        return None
    
    def store_call_analytics(self, bot_id: int, call_uuid: str, sentiment_data: Dict, call_duration: int = None):
        """Store sentiment analysis results in database with recipient info"""
        bot = self.get(bot_id)
        if not bot:
            return
        
        # Get recipient information from the bot
        recipient_info = bot.get_recipient_info(call_uuid) or {}
        
        with Session(engine) as session:
            analytics = VoiceCallAnalytics(
                bot_id=bot_id,
                user_phone_number=recipient_info.get('number', 'Unknown'),
                recipient_name=recipient_info.get('name', 'Unknown'),  # NEW: Store recipient name
                call_uuid=call_uuid,
                sentiment_category=sentiment_data.get("category", "neutral"),
                confidence_score=sentiment_data.get("confidence", 0.5),
                analysis_reason=sentiment_data.get("reason", ""),
                follow_up_action=sentiment_data.get("follow_up_action", ""),
                call_duration=call_duration
            )
            session.add(analytics)
            session.commit()
            
    def get_call_analytics(self, bot_id: int, user_phone_number: str = None):
        """Retrieve call analytics for a bot"""
        with Session(engine) as session:
            query = select(VoiceCallAnalytics).where(VoiceCallAnalytics.bot_id == bot_id)
            if user_phone_number:
                query = query.where(VoiceCallAnalytics.user_phone_number == user_phone_number)
            results = session.exec(query).all()
            return results
    
    # ========== PHONE NUMBER MANAGEMENT METHODS ==========
    
    def search_available_numbers(self, country_iso: str, 
                                 number_type: str = "local",
                                 pattern: str = None,
                                 region: str = None,
                                 services: List[str] = ["voice", "sms"]) -> List[Dict]:
        """
        Search for available phone numbers on Plivo
        """
        try:
            params = {
                "country_iso": country_iso.upper(),
                "type": number_type,
                "services": ",".join(services)
            }
            
            if pattern:
                params["pattern"] = pattern
            if region:
                params["region"] = region
            
            response = self.plivo_client.numbers.search(**params)
            return response.numbers if hasattr(response, 'numbers') else []
            
        except Exception as e:
            print(f"Error searching numbers: {e}")
            return []
    
    def buy_phone_number_for_user(self, user_id: str, number: str, 
                                  app_id: str = None, 
                                  alias: str = None,
                                  assignment_type: str = "pooled",
                                  campaign_tag: str = None) -> Dict:
        """
        Buy a phone number and assign it to a USER (GeminiChatX pays)
        """
        try:
            # Buy the number from Plivo
            response = self.plivo_client.numbers.buy(
                number=number,
                app_id=app_id
            )
            
            # Get number details from Plivo
            number_info = self.plivo_client.numbers.get(number)
            
            # Store in database as user-owned
            with Session(engine) as session:
                # Check if this is user's first number (set as default)
                existing_numbers = session.exec(
                    select(AccountPhoneNumber).where(
                        AccountPhoneNumber.user_id == user_id,
                        AccountPhoneNumber.status == NumberStatus.ACTIVE
                    )
                ).all()
                
                is_default = len(existing_numbers) == 0
                
                phone_record = AccountPhoneNumber(
                    user_id=user_id,
                    plivo_number_id=number_info.number_id,
                    phone_number=number,
                    alias=alias or f"My Number {len(existing_numbers)+1}",
                    number_type=NumberType(number_info.type.lower()),
                    country_iso=number_info.country_iso,
                    city=number_info.city,
                    region=number_info.region,
                    monthly_rental_rate=float(number_info.monthly_rental_rate),
                    setup_rate=float(number_info.setup_rate),
                    voice_enabled=number_info.voice_enabled,
                    sms_enabled=number_info.sms_enabled,
                    status=NumberStatus.ACTIVE,
                    assignment_type=NumberAssignment(assignment_type),
                    campaign_tag=campaign_tag,
                    is_default=is_default,
                    plivo_app_id=app_id,
                    usage_stats_dict={"total_calls": 0, "last_used": None, "successful_calls": 0, "success_rate": 100}
                )
                
                session.add(phone_record)
                session.commit()
                session.refresh(phone_record)
                
                return {
                    "success": True,
                    "user_id": user_id,
                    "number": number,
                    "alias": phone_record.alias,
                    "plivo_number_id": phone_record.plivo_number_id,
                    "record_id": phone_record.id,
                    "monthly_cost": phone_record.monthly_rental_rate,
                    "is_default": is_default,
                    "message": "Number purchased and assigned to your account"
                }
                
        except plivo.exceptions.ValidationError as ve:
            return {"success": False, "error": f"Validation error: {ve}"}
        except plivo.exceptions.PlivoRestError as pe:
            return {"success": False, "error": f"Plivo error: {pe}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_user_numbers(self, user_id: str, 
                         active_only: bool = True,
                         number_type: Optional[str] = None) -> List[AccountPhoneNumber]:
        """Get all phone numbers assigned to a user"""
        with Session(engine) as session:
            query = select(AccountPhoneNumber).where(
                AccountPhoneNumber.user_id == user_id
            )
            
            if active_only:
                query = query.where(AccountPhoneNumber.status == NumberStatus.ACTIVE)
            
            if number_type:
                query = query.where(AccountPhoneNumber.number_type == number_type)
            
            return session.exec(query.order_by(AccountPhoneNumber.is_default.desc(),
                                              AccountPhoneNumber.created_at.desc())).all()
    
    def get_default_user_number(self, user_id: str) -> Optional[AccountPhoneNumber]:
        """Get user's default phone number"""
        with Session(engine) as session:
            return session.exec(
                select(AccountPhoneNumber).where(
                    AccountPhoneNumber.user_id == user_id,
                    AccountPhoneNumber.status == NumberStatus.ACTIVE,
                    AccountPhoneNumber.is_default == True
                )
            ).first()
    
    def get_user_numbers_for_dropdown(self, user_id: str, bot_id: Optional[int] = None) -> List[Dict]:
        """
        Get user's phone numbers formatted for frontend dropdown
        """
        numbers = self.get_user_numbers(user_id=user_id, active_only=True)
        
        dropdown_data = []
        for num in numbers:
            # Only include voice-enabled numbers
            if num.voice_enabled:
                # Create display label
                display_parts = []
                if num.alias:
                    display_parts.append(num.alias)
                
                display_parts.append(num.phone_number)
                
                if num.city:
                    display_parts.append(f"({num.city})")
                elif num.country_iso:
                    display_parts.append(f"({num.country_iso})")
                
                if num.is_default:
                    display_parts.append("[Default]")
                
                if bot_id and num.assigned_bot_id == bot_id:
                    display_parts.append("[Dedicated]")
                
                if num.assignment_type == "campaign" and num.campaign_tag:
                    display_parts.append(f"[Campaign: {num.campaign_tag}]")
                
                label = " ".join(display_parts)
                
                # Get success rate from usage stats
                stats = num.usage_stats_dict
                success_rate = stats.get("success_rate", 100) if stats else 100
                
                dropdown_data.append({
                    "value": num.phone_number,
                    "label": label,
                    "alias": num.alias,
                    "type": num.number_type.value,
                    "country": num.country_iso,
                    "city": num.city,
                    "is_default": num.is_default,
                    "assigned_to_bot": num.assigned_bot_id,
                    "campaign": num.campaign_tag,
                    "monthly_cost": num.monthly_rental_rate,
                    "success_rate": success_rate,
                    "total_calls": stats.get("total_calls", 0) if stats else 0
                })
        
        # Sort: default first, then dedicated to bot, then by creation date
        dropdown_data.sort(key=lambda x: (
            not x["is_default"],
            not (x["assigned_to_bot"] == bot_id if bot_id else False),
            x["value"]
        ))
        
        return dropdown_data
    
    def assign_number_to_bot(self, user_id: str, number_id: int, bot_id: int) -> bool:
        """Assign a user's number to a specific bot (dedicated assignment)"""
        with Session(engine) as session:
            # Verify user owns the number
            number = session.exec(
                select(AccountPhoneNumber).where(
                    AccountPhoneNumber.id == number_id,
                    AccountPhoneNumber.user_id == user_id
                )
            ).first()
            
            if not number:
                return False
            
            # Verify user owns the bot
            bot = session.exec(
                select(VoiceBotMeta).where(
                    VoiceBotMeta.id == bot_id,
                    VoiceBotMeta.owner == user_id
                )
            ).first()
            
            if not bot:
                return False
            
            # Update number assignment
            number.assigned_bot_id = bot_id
            number.assignment_type = NumberAssignment.DEDICATED
            session.add(number)
            session.commit()
            
            return True
    
    def release_number_from_bot(self, user_id: str, number_id: int) -> bool:
        """Release a number from bot assignment (back to pooled)"""
        with Session(engine) as session:
            number = session.exec(
                select(AccountPhoneNumber).where(
                    AccountPhoneNumber.id == number_id,
                    AccountPhoneNumber.user_id == user_id
                )
            ).first()
            
            if number:
                number.assigned_bot_id = None
                number.assignment_type = NumberAssignment.POOLED
                session.add(number)
                session.commit()
                return True
            return False
    
    def get_available_number_for_bot(self, bot_id: int, user_id: str) -> Optional[str]:
        """
        Get an available phone number for a bot to use
        Priority: Dedicated > Default > Any pooled number
        """
        with Session(engine) as session:
            # 1. Check for dedicated number assigned to this bot
            dedicated = session.exec(
                select(AccountPhoneNumber).where(
                    AccountPhoneNumber.user_id == user_id,
                    AccountPhoneNumber.assigned_bot_id == bot_id,
                    AccountPhoneNumber.status == NumberStatus.ACTIVE
                )
            ).first()
            
            if dedicated:
                return dedicated.phone_number
            
            # 2. Check user's default number
            default = self.get_default_user_number(user_id)
            if default:
                return default.phone_number
            
            # 3. Get any active pooled number
            pooled = session.exec(
                select(AccountPhoneNumber).where(
                    AccountPhoneNumber.user_id == user_id,
                    AccountPhoneNumber.status == NumberStatus.ACTIVE,
                    AccountPhoneNumber.assignment_type == NumberAssignment.POOLED
                ).order_by(AccountPhoneNumber.created_at)
            ).first()
            
            return pooled.phone_number if pooled else None
    
    def validate_user_owns_number(self, user_id: str, phone_number: str) -> bool:
        """
        Validate that a user owns and can use a phone number
        """
        with Session(engine) as session:
            number = session.exec(
                select(AccountPhoneNumber).where(
                    AccountPhoneNumber.user_id == user_id,
                    AccountPhoneNumber.phone_number == phone_number,
                    AccountPhoneNumber.status == NumberStatus.ACTIVE,
                    AccountPhoneNumber.voice_enabled == True
                )
            ).first()
            return number is not None
    
    def update_number_usage(self, phone_number: str, call_success: bool = True):
        """Update usage statistics for a number"""
        with Session(engine) as session:
            number_record = session.exec(
                select(AccountPhoneNumber).where(
                    AccountPhoneNumber.phone_number == phone_number
                )
            ).first()
            
            if number_record:
                stats = number_record.usage_stats_dict
                stats["total_calls"] = stats.get("total_calls", 0) + 1
                stats["last_used"] = datetime.utcnow().isoformat()
                
                # Calculate success rate
                if "successful_calls" not in stats:
                    stats["successful_calls"] = 0
                
                if call_success:
                    stats["successful_calls"] += 1
                
                total_calls = stats["total_calls"]
                if total_calls > 0:
                    stats["success_rate"] = (stats["successful_calls"] / total_calls) * 100
                
                number_record.usage_stats_dict = stats
                session.add(number_record)
                session.commit()
    
    def set_default_number(self, user_id: str, number_id: int) -> bool:
        """Set a number as user's default"""
        with Session(engine) as session:
            # First, unset any existing default
            existing_defaults = session.exec(
                select(AccountPhoneNumber).where(
                    AccountPhoneNumber.user_id == user_id,
                    AccountPhoneNumber.is_default == True
                )
            ).all()
            
            for num in existing_defaults:
                num.is_default = False
                session.add(num)
            
            # Set new default
            number = session.exec(
                select(AccountPhoneNumber).where(
                    AccountPhoneNumber.id == number_id,
                    AccountPhoneNumber.user_id == user_id
                )
            ).first()
            
            if number:
                number.is_default = True
                session.add(number)
                session.commit()
                return True
            
            return False
    
    def update_number_application(self, number_id: str, app_id: str) -> bool:
        """
        Update which Plivo application is associated with a number
        """
        try:
            response = self.plivo_client.numbers.update(
                number_id=number_id,
                app_id=app_id
            )
            return True
        except Exception as e:
            print(f"Error updating number: {e}")
            return False
    
    def unrent_number(self, user_id: str, number_id: int) -> bool:
        """
        Release/unrent a phone number
        """
        try:
            with Session(engine) as session:
                # Get the record
                number_record = session.exec(
                    select(AccountPhoneNumber).where(
                        AccountPhoneNumber.id == number_id,
                        AccountPhoneNumber.user_id == user_id
                    )
                ).first()
                
                if number_record:
                    # Unrent from Plivo
                    self.plivo_client.numbers.unrent(number_id=number_record.plivo_number_id)
                    
                    # Update status in database
                    number_record.status = NumberStatus.RELEASED
                    session.add(number_record)
                    session.commit()
                    
                    return True
            return False
            
        except Exception as e:
            print(f"Error unrenting number: {e}")
            return False
    
    # ========== INCOMING CARRIER METHODS ==========
    
    def create_incoming_carrier(self, user_id: str, carrier_name: str, ip_set: List[str], 
                               prefix_set: List[str], failover_carrier: str = None) -> Dict:
        """
        Create an incoming carrier for BYOC (Bring Your Own Carrier)
        """
        try:
            response = self.plivo_client.carriers.create(
                name=carrier_name,
                ips=",".join(ip_set),
                prefixes=",".join(prefix_set),
                failover_carrier=failover_carrier
            )
            
            # Store in database
            with Session(engine) as session:
                carrier = IncomingCarrier(
                    user_id=user_id,
                    carrier_name=carrier_name,
                    carrier_id=response.carrier_id,
                    ip_set=",".join(ip_set),
                    prefix_set=",".join(prefix_set),
                    failover_carrier=failover_carrier
                )
                
                session.add(carrier)
                session.commit()
                
                return {
                    "success": True,
                    "carrier_id": response.carrier_id,
                    "carrier_name": carrier_name
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def list_incoming_carriers(self, user_id: str) -> List[IncomingCarrier]:
        """
        List all incoming carriers for a user
        """
        with Session(engine) as session:
            return session.exec(select(IncomingCarrier).where(
                IncomingCarrier.user_id == user_id
            )).all()
    
    def add_number_from_carrier(self, user_id: str, phone_number: str, 
                               carrier_id: str, monthly_cost: float = 0.0) -> Dict:
        """
        Add a number from your own carrier to the account
        """
        try:
            # This is a simplified version - actual implementation depends on carrier setup
            with Session(engine) as session:
                phone_record = AccountPhoneNumber(
                    user_id=user_id,
                    plivo_number_id=f"carrier_{carrier_id}_{phone_number}",
                    phone_number=phone_number,
                    alias=f"BYOC - {phone_number}",
                    number_type=NumberType.LOCAL,
                    country_iso="US",  # Get from number
                    monthly_rental_rate=monthly_cost,
                    setup_rate=0.0,
                    voice_enabled=True,
                    sms_enabled=True,
                    status=NumberStatus.ACTIVE
                )
                
                session.add(phone_record)
                session.commit()
                
                return {
                    "success": True,
                    "message": f"Number {phone_number} added from carrier",
                    "record_id": phone_record.id
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}

# Global instance
voice_bot_manager = VoiceBotManager()