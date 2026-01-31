import requests
import logging
from typing import Dict, Optional
from config.settings import WHATSAPP_API_VERSION

logger = logging.getLogger(__name__)

class WhatsAppAPIService:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}"
    
    def get_waba_details(self) -> Optional[Dict]:
        """Get WhatsApp Business Account details"""
        try:
            # First get business accounts
            biz_url = f"{self.base_url}/me/businesses"
            response = requests.get(
                biz_url,
                params={"access_token": self.access_token}
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to get businesses: {response.text}")
                return None
            
            businesses = response.json().get('data', [])
            if not businesses:
                logger.error("No businesses found")
                return None
            
            # Get first business account
            business_id = businesses[0]['id']
            
            # Get WABA for this business
            waba_url = f"{self.base_url}/{business_id}/whatsapp_business_accounts"
            waba_response = requests.get(
                waba_url,
                params={"access_token": self.access_token}
            )
            
            if waba_response.status_code != 200:
                logger.error(f"Failed to get WABA: {waba_response.text}")
                return None
            
            waba_data = waba_response.json().get('data', [])
            if not waba_data:
                logger.error("No WABA found")
                return None
            
            waba_id = waba_data[0]['id']
            
            # Get phone numbers
            phone_url = f"{self.base_url}/{waba_id}/phone_numbers"
            phone_response = requests.get(
                phone_url,
                params={"access_token": self.access_token}
            )
            
            if phone_response.status_code != 200:
                logger.error(f"Failed to get phone numbers: {phone_response.text}")
                return None
            
            phone_data = phone_response.json().get('data', [])
            if not phone_data:
                logger.error("No phone numbers found")
                return None
            
            phone_number_id = phone_data[0]['id']
            phone_number = phone_data[0].get('display_phone_number')
            phone_verified = phone_data[0].get('verified_name', 'Not Verified')
            
            return {
                "business_id": business_id,
                "waba_id": waba_id,
                "phone_number_id": phone_number_id,
                "phone_number": phone_number,
                "verified_name": phone_verified,
                "status": "connected"
            }
            
        except Exception as e:
            logger.error(f"Error getting WABA details: {str(e)}")
            return None
    
    def setup_webhook(self, phone_number_id: str) -> bool:
        """Subscribe phone number to webhook"""
        try:
            url = f"{self.base_url}/{phone_number_id}/subscribed_apps"
            response = requests.post(
                url,
                params={"access_token": self.access_token}
            )
            
            if response.status_code == 200:
                logger.info(f"Webhook setup successful for {phone_number_id}")
                return True
            else:
                logger.error(f"Webhook setup failed: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error setting up webhook: {str(e)}")
            return False
    
    def send_message(self, phone_number_id: str, to_number: str, message: str) -> bool:
        """Send WhatsApp message"""
        try:
            url = f"{self.base_url}/{phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            data = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to_number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": message
                }
            }
            
            response = requests.post(url, json=data, headers=headers)
            
            if response.status_code == 200:
                logger.info(f"Message sent to {to_number}")
                return True
            else:
                logger.error(f"Failed to send message: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            return False
    
    def get_business_profile(self, phone_number_id: str) -> Optional[Dict]:
        """Get WhatsApp Business profile"""
        try:
            url = f"{self.base_url}/{phone_number_id}/whatsapp_business_profile"
            response = requests.get(
                url,
                params={"access_token": self.access_token,
                       "fields": "about,address,description,email,profile_picture_url,websites,vertical"}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get business profile: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting business profile: {str(e)}")
            return None