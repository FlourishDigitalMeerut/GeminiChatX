import os
from typing import Optional, List, Dict, Any
from langchain_chroma import Chroma # pyright: ignore[reportMissingImports]
from core.embeddings import E5Embeddings
import plivo # pyright: ignore[reportMissingImports]
from groq import Groq
from sqlmodel import Session, select # pyright: ignore[reportMissingImports]
from models.database import engine
from models.plivo_numbers import AccountPhoneNumber, NumberStatus
from config.settings import GROQ_API_KEY, PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN, PLIVO_PHONE_NUMBER

class VoiceBot:            
    def __init__(self, meta):
        self.meta = meta
        self.embedding_model = E5Embeddings()
        self.vector_store = None
        # self.plivo_client = plivo.RestClient(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN)
        self.groq_client = Groq(api_key=GROQ_API_KEY)
        self.call_transcripts = {}  # Stores transcripts and recipient info
        self.ensure_vector_store()
    
    def ensure_vector_store(self):
        if self.vector_store is None:
            self.vector_store = Chroma(
                persist_directory=self.meta.persist_dir,
                embedding_function=self.embedding_model
            )
    
    def clear_knowledge_base(self):
        if self.vector_store:
            self.vector_store.delete_collection()
            self.vector_store = None
            self.ensure_vector_store()
    
    def chat(self, message: str) -> str:
        """Generate response using knowledge base and LLM"""
        try:
            # Search knowledge base
            if self.vector_store:
                docs = self.vector_store.similarity_search(message, k=3)
                context = "\n".join([doc.page_content for doc in docs])
            else:
                context = ""
            
            # Use Groq LLM for response generation
            prompt = f"""
            Your name is {self.meta.name},a voice assistant from {self.meta.company_name}.
            Based on the following context and user query, provide a helpful response.
            
            Context: {context}
            
            User Query: {message}
            
            If the context doesn't contain relevant information, then use {self.meta.fallback_response} as the response.
            Keep the response conversational and natural and friendly and professional and clean for voice delivery.
            Note: Keep the response concise and to the point and short accordingly as the response is being spoken in the call and avoid unnecessary elaboration and also avoid using phrases like "As an AI language model" or do not tell any one that i am AI assistant or AI bot.
            Also instead of introducing yourself as an AI assistant you should provide your name ({self.meta.name}) where ever required(mostly in the first message of greetings)with the company name and wherever is needed and note that you should not mention your name in every response only mention wherever is required.
            """
            
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.7,
                max_tokens=150
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"Error in voice bot chat: {e}")
            return self.meta.fallback_response
    
    # ========== CALLER ID MANAGEMENT ==========
    
    def validate_caller_id(self, from_number: str) -> str:
        """
        Validate that the user owns and can use the specified phone number
        """
        if not from_number:
            raise ValueError("from_number is required")
        
        # Verify this number belongs to the user
        with Session(engine) as session:
            number_owned = session.exec(
                select(AccountPhoneNumber).where(
                    AccountPhoneNumber.user_id == self.meta.owner,
                    AccountPhoneNumber.phone_number == from_number,
                    AccountPhoneNumber.status == NumberStatus.ACTIVE,
                    AccountPhoneNumber.voice_enabled == True
                )
            ).first()
            
            if not number_owned:
                raise ValueError(f"User does not own or cannot use phone number: {from_number}")
            
            return from_number
    
    def get_caller_id(self, from_number: str = None) -> str:
        """
        Get caller ID for outbound call with validation
        """
        # If specific number provided, validate it
        if from_number:
            return self.validate_caller_id(from_number)
        
        # If no number specified, get user's default number
        from managers.voice_bot_manager import voice_bot_manager
        default_number = voice_bot_manager.get_default_user_number(self.meta.owner)
        
        if default_number:
            return default_number.phone_number
        
        # Fallback to company default
        return PLIVO_PHONE_NUMBER
    
    # ========== CALL MANAGEMENT ==========
    
    def make_call(self, to_number: str, message: str = None, 
                 recipient_name: str = "Unknown", 
                 from_number: str = None) -> Dict[str, Any]:
        """
        Initiate outbound call using Plivo with caller ID validation
        """
        try:
            welcome_message = message or self.meta.outbound_welcome_message
            
            # Get and validate caller ID
            caller_id = self.get_caller_id(from_number)
            
            # Create Plivo XML for call flow
            response_xml = f"""
            <Response>
                <Speak voice="{self.meta.voice_type}" language="{self.meta.language}">
                    {welcome_message}
                </Speak>
                <Record action="/api/v1/bots/voice/{self.meta.id}/process-audio" 
                        method="POST" 
                        maxLength="30" 
                        playBeep="true"
                        transcriptionType="auto"
                        transcriptionUrl="/api/v1/bots/voice/{self.meta.id}/process-transcript"/>
                <Speak voice="{self.meta.voice_type}" language="{self.meta.language}">
                    Thank you for your time. Goodbye!
                </Speak>
            </Response>
            """
            
            # Make the call
            call_response = self.plivo_client.calls.create(
                from_=caller_id,
                to=to_number,
                answer_url=f"http://your-domain.com/api/v1/bots/voice/{self.meta.id}/call-answer",
                answer_method="GET"
            )
            
            # Store recipient info for analytics
            call_uuid = call_response.call_uuid
            self.call_transcripts[call_uuid] = {
                'segments': [],
                'recipient': {
                    'name': recipient_name,
                    'number': to_number
                },
                'caller_id': caller_id
            }
            
            # Update number usage stats
            from managers.voice_bot_manager import voice_bot_manager
            voice_bot_manager.update_number_usage(caller_id, call_success=True)
            
            return {
                "call_id": call_uuid,
                "caller_id": caller_id,
                "status": "initiated",
                "message": "Call initiated successfully"
            }
            
        except Exception as e:
            print(f"Error making call: {e}")
            # Update number usage stats as failed
            if 'caller_id' in locals():
                from managers.voice_bot_manager import voice_bot_manager
                voice_bot_manager.update_number_usage(caller_id, call_success=False)
            
            return {
                "call_id": None,
                "status": "failed",
                "error": str(e)
            }

    def make_bulk_call(self, to_numbers: str, message: str = None, 
                      recipient_data: List[Dict] = None,
                      from_number: str = None) -> Dict[str, Any]:
        """
        Initiate bulk outbound calls using Plivo with multiple destinations
        """
        try:
            welcome_message = message or self.meta.outbound_welcome_message
            
            # Get and validate caller ID
            caller_id = self.get_caller_id(from_number)
            
            # Create Plivo XML for call flow
            response_xml = f"""
            <Response>
                <Speak voice="{self.meta.voice_type}" language="{self.meta.language}">
                    {welcome_message}
                </Speak>
                <Record action="/api/v1/bots/voice/{self.meta.id}/process-audio" 
                        method="POST" 
                        maxLength="30" 
                        playBeep="true"
                        transcriptionType="auto"
                        transcriptionUrl="/api/v1/bots/voice/{self.meta.id}/process-transcript"/>
                <Speak voice="{self.meta.voice_type}" language="{self.meta.language}">
                    Thank you for your time. Goodbye!
                </Speak>
            </Response>
            """
            
            # Make the bulk call with multiple destinations
            call_response = self.plivo_client.calls.create(
                from_=caller_id,
                to=to_numbers,
                answer_url=f"http://your-domain.com/api/v1/bots/voice/{self.meta.id}/call-answer",
                answer_method="GET"
            )
            
            # Store recipient data for analytics
            call_ids = []
            if isinstance(call_response, list):
                for i, call in enumerate(call_response):
                    call_ids.append(call.call_uuid)
                    if recipient_data and i < len(recipient_data):
                        self.call_transcripts[call.call_uuid] = {
                            'segments': [],
                            'recipient': recipient_data[i],
                            'caller_id': caller_id
                        }
            else:
                call_ids.append(call_response.call_uuid)
                if recipient_data and len(recipient_data) > 0:
                    self.call_transcripts[call_response.call_uuid] = {
                        'segments': [],
                        'recipient': recipient_data[0],
                        'caller_id': caller_id
                    }
            
            # Update number usage stats
            from managers.voice_bot_manager import voice_bot_manager
            voice_bot_manager.update_number_usage(caller_id, call_success=True)
            
            return {
                "call_ids": call_ids,
                "caller_id": caller_id,
                "status": "initiated",
                "message": "Bulk calls initiated successfully"
            }
            
        except Exception as e:
            print(f"Error making bulk call: {e}")
            # Update number usage stats as failed
            if 'caller_id' in locals():
                from managers.voice_bot_manager import voice_bot_manager
                voice_bot_manager.update_number_usage(caller_id, call_success=False)
            
            return {
                "call_ids": [],
                "status": "failed",
                "error": str(e)
            }
    
    # ========== TRANSCRIPT MANAGEMENT ==========
    
    def store_call_transcript(self, call_uuid: str, transcript_segment: str):
        """Store transcript segments during call with recipient info"""
        if call_uuid not in self.call_transcripts:
            self.call_transcripts[call_uuid] = {'segments': [], 'recipient': None}
        self.call_transcripts[call_uuid]['segments'].append(transcript_segment)
    
    def get_full_transcript(self, call_uuid: str) -> str:
        """Get complete transcript for a call"""
        if call_uuid in self.call_transcripts:
            return " ".join(self.call_transcripts[call_uuid]['segments'])
        return ""
    
    def get_recipient_info(self, call_uuid: str) -> Dict:
        """Get recipient information for a call"""
        if call_uuid in self.call_transcripts:
            return self.call_transcripts[call_uuid].get('recipient', {})
        return {}
    
    def clear_transcript(self, call_uuid: str):
        """Clear transcript after analysis"""
        if call_uuid in self.call_transcripts:
            del self.call_transcripts[call_uuid]
    
    def analyze_call_sentiment(self, transcript: str) -> Dict[str, Any]:
        """Analyze COMPLETE call transcript after call ends"""
        if not transcript.strip():
            return {
                "category": "no_speech",
                "confidence": 1.0,
                "reason": "Empty transcript - no speech detected",
                "follow_up_action": "No action needed"
            }
        
        try:
            analysis_prompt = f"""
            Analyze this COMPLETE customer call transcript and categorize it into ONE of these categories:
            1. interested_in_product - Customer shows interest in product/service, asks for details
            2. not_interested - Customer clearly states they are not interested or refuses
            3. angry_customer - Customer is angry, frustrated, or dissatisfied
            4. satisfied_customer - Customer is happy, satisfied, or thankful
            5. request_callback - Customer requests callback or more information
            6. neutral_inquiry - General inquiry without clear sentiment
            
            Complete Transcript: "{transcript}"
            
            Respond in JSON format only:
            {{
                "category": "category_name",
                "confidence": 0.95,
                "reason": "brief explanation based on key phrases from transcript",
                "follow_up_action": "specific suggested action"
            }}
            """
            
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": analysis_prompt}],
                model="llama-3.1-8b-instant",
                temperature=0.1,
                max_tokens=200
            )
            
            import json
            result = json.loads(response.choices[0].message.content.strip())
            return result
            
        except Exception as e:
            print(f"Error in call analysis: {e}")
            return {
                "category": "analysis_failed",
                "confidence": 0.0,
                "reason": "Analysis failed due to technical error",
                "follow_up_action": "Manual review required"
            }
def get_caller_id(self, from_number: str = None) -> str:
    """
    Get caller ID for outbound call with validation
    """
    from managers.voice_bot_manager import voice_bot_manager
    
    # Check if user has any numbers first
    user_numbers = voice_bot_manager.get_user_numbers(user_id=self.meta.owner, active_only=True)
    
    if not user_numbers:
        raise ValueError(
            "User has no phone numbers. Please purchase a phone number first. "
            "Visit /api/v1/plivo/numbers/search to find available numbers."
        )
    
    # If specific number provided, validate it
    if from_number:
        return self.validate_caller_id(from_number)
    
    # If no number specified, get user's default number
    default_number = voice_bot_manager.get_default_user_number(self.meta.owner)
    
    if default_number:
        return default_number.phone_number
    
    # Fallback to any available number
    return user_numbers[0].phone_number