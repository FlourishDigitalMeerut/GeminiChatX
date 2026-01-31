import aiosmtplib # pyright: ignore[reportMissingImports]
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

async def send_contact_form_email(form_data: dict):
    """
    Send contact form submission to company via email
    """
    try:
        # Load email configuration
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT1", 587))  # Fixed: SMTP_PORT not SMTP_PORT1
        email_username = os.getenv("EMAIL_USERNAME")
        email_password = os.getenv("EMAIL_PASSWORD")
        company_email = os.getenv("COMPANY_EMAIL", "admin@company.com")
        
        if not all([email_username, email_password]):
            logger.warning("Email credentials not configured")
            return False
        
        # Create email message
        message = MIMEMultipart()
        message["From"] = email_username
        message["To"] = company_email
        message["Subject"] = f"New Contact Form - {form_data.get('business_name', 'No Business Name')}"
        
        # Create email body
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        alt_numbers = form_data.get('alternative_numbers')
        if alt_numbers and isinstance(alt_numbers, list) and alt_numbers:
            alt_text = ', '.join(alt_numbers)
        else:
            alt_text = 'Not provided'
        
        body = f"""
        NEW CONTACT FORM SUBMISSION
        
        Timestamp: {timestamp}
        
        BUSINESS DETAILS:
        ├── Business Name: {form_data.get('business_name', 'N/A')}
        ├── First Name: {form_data.get('first_name', 'N/A')}
        ├── Last Name: {form_data.get('last_name', 'N/A')}
        ├── Mobile: {form_data.get('mobile_number', 'N/A')}
        └── Email: {form_data.get('email', 'N/A')}
        
        ALTERNATIVE CONTACTS:
        └── {alt_text}
        
        APPOINTMENT DETAILS:
        └── Selected Slot: {form_data.get('selected_slot', 'Not selected')}
        
        MESSAGE:
        {form_data.get('message', 'No message provided')}
        
        ---
        This message was automatically generated from your website's contact form.
        """
        
        message.attach(MIMEText(body, "plain"))
        
        # Send email - CORRECTED VERSION
        # For port 465 (SSL) or port 587 (TLS)
        if smtp_port == 465:
            # SSL connection
            smtp = aiosmtplib.SMTP(
                hostname=smtp_server,
                port=smtp_port,
                start_tls=False,  # Don't use STARTTLS for SSL
                use_tls=True     # Use TLS for SSL connection
            )
        else:
            # TLS connection (default for port 587)
            smtp = aiosmtplib.SMTP(
                hostname=smtp_server,
                port=smtp_port,
                start_tls=True,  # Use STARTTLS
                use_tls=False    # TLS will be negotiated via STARTTLS
            )
        
        await smtp.connect()
        await smtp.login(email_username, email_password)
        await smtp.send_message(message)
        await smtp.quit()
        
        logger.info(f"Contact form email sent successfully at {timestamp}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send contact form email: {str(e)}")
        return False