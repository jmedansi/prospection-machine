import time
from typing import Tuple, Optional
from envoi.email_tracking_service import EmailTrackingService

class ResendSenderWithRetry:
    def __init__(self, api_key: str, db_path: str, max_retries: int = 3):
        import resend
        self.client = resend.Client(api_key=api_key)
        self.tracking_service = EmailTrackingService(db_path)
        self.max_retries = max_retries
    
    def send_with_retry(
        self,
        email_record_id: int,
        email: str,
        subject: str,
        html_body: str,
        reply_to: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Envoyer un email avec retry automatique.
        Retourne: (success: bool, message_id_or_error: str)
        """
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.emails.send({
                    'from': 'noreply@example.com',
                    'to': email,
                    'subject': subject,
                    'html': html_body,
                    'reply_to': reply_to or 'noreply@example.com'
                })
                # Succès
                if hasattr(response, 'id'):
                    message_id = response.id
                    success = self.tracking_service.update_message_id(
                        email_record_id=email_record_id,
                        message_id_resend=message_id
                    )
                    if success:
                        return (True, message_id)
                    else:
                        return (False, "Envoi OK mais mise à jour BD échouée")
                # Erreur Resend
                elif hasattr(response, 'message'):
                    last_error = response.message
            except Exception as e:
                last_error = str(e)
            # Retry avec délai exponentiel
            if attempt < self.max_retries:
                wait_time = 2 ** attempt  # 2s, 4s, 8s
                print(f"Retry {attempt}/{self.max_retries} dans {wait_time}s...")
                time.sleep(wait_time)
        # Tous les retries ont échoué
        self.tracking_service.mark_send_error(
            email_record_id=email_record_id,
            error_message=last_error,
            retry_count=self.max_retries
        )
        return (False, last_error)
