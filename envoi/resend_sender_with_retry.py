import time
import requests
from typing import Tuple, Optional
from envoi.email_tracking_service import EmailTrackingService

class ResendSenderWithRetry:
    def __init__(self, api_key: str, db_path: str, max_retries: int = 3):
        self.api_key = api_key
        self.db_path = db_path
        self.tracking_service = EmailTrackingService(db_path)
        self.max_retries = max_retries
        self.api_url = "https://api.resend.com/emails"
    
    def _send_via_api(self, from_email: str, email: str, subject: str, html_body: str, reply_to: str = None) -> Tuple[bool, dict]:
        """Envoie via l'API Resend."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "from": from_email,
            "to": email,
            "subject": subject,
            "html": html_body
        }
        if reply_to:
            payload["reply_to"] = reply_to
        
        resp = requests.post(self.api_url, json=payload, headers=headers, timeout=15)
        if resp.status_code in (200, 201):
            return True, resp.json()
        else:
            return False, {"error": resp.text, "status": resp.status_code}
    
    def send_with_retry(
        self,
        email_record_id: int,
        email: str,
        subject: str,
        html_body: str,
        reply_to: Optional[str] = None,
        from_email: str = "noreply@resend.dev"
    ) -> Tuple[bool, Optional[str]]:
        """
        Envoyer un email avec retry automatique.
        Retourne: (success: bool, message_id_or_error: str)
        """
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                success, resp = self._send_via_api(from_email, email, subject, html_body, reply_to)
                if success and 'id' in resp:
                    message_id = resp['id']
                    self.tracking_service.update_message_id(
                        email_record_id=email_record_id,
                        message_id_resend=message_id
                    )
                    return (True, message_id)
                else:
                    last_error = resp.get('error', 'Unknown error')
            except Exception as e:
                last_error = str(e)
            
            if attempt < self.max_retries:
                wait_time = 2 ** attempt
                print(f"Retry {attempt}/{self.max_retries} dans {wait_time}s...")
                time.sleep(wait_time)
        
        self.tracking_service.mark_send_error(
            email_record_id=email_record_id,
            error_message=last_error,
            retry_count=self.max_retries
        )
        return (False, last_error)
