import requests
import json

def simulate_resend_event(event_type, message_id, extra=None):
    url = "http://localhost:5001/webhooks/resend"
    data = {
        "type": event_type,
        "message_id": message_id,
        "timestamp": "2026-04-02T12:00:00Z",
        "user_agent": "pytest-agent/1.0",
        "ip": "127.0.0.1"
    }
    if extra:
        data.update(extra)
    resp = requests.post(url, json=data)
    print(f"Event {event_type} → {resp.status_code} {resp.text}")

if __name__ == "__main__":
    # Remplacez par un message_id valide existant dans votre base
    test_message_id = "test-message-id-123"
    simulate_resend_event("email.opened", test_message_id)
    simulate_resend_event("email.clicked", test_message_id, {"details": {"url": "https://incidenx.com"}})
    simulate_resend_event("email.bounced", test_message_id, {"details": {"reason": "Mailbox full"}})
