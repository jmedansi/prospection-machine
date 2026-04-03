# -*- coding: utf-8 -*-
"""
Validation SMTP des emails après scraping.
Vérifie que les MX records existent et que la boîte mail existe via SMTP.
"""
import smtplib
import dns.resolver
import logging
from typing import Optional
import socket

socket.setdefaulttimeout(5)

logger = logging.getLogger(__name__)


def verify_email_smtp(email: str, sender_domain: str = "incidenx.com") -> Optional[str]:
    """
    Vérifie si un email est valide via connexion SMTP.
    Version optimisée avec timeout court.
    
    Args:
        email: Adresse email à vérifier
        sender_domain: Domaine expéditeur pour la connexion SMTP
    
    Returns:
        'Valide' si l'email existe
        'Inconnu' si le domaine MX n'existe pas ou erreur de vérification
        'Erreur' si erreur technique (timeout, etc.)
    """
    if not email or '@' not in email:
        return 'Erreur'
    
    domain = email.split('@')[1]
    
    try:
        # Vérifier les MX records
        mx_records = dns.resolver.resolve(domain, 'MX')
        mx_host = str(mx_records[0].exchange).rstrip('.')
        
        # Connexion SMTP avec timeout court
        server = smtplib.SMTP(timeout=5)
        server.connect(mx_host)
        server.helo(sender_domain)
        server.mail(f'verify@{sender_domain}')
        code, _ = server.rcpt(email)
        server.quit()
        
        if code == 250:
            return 'Valide'
        else:
            return 'Inconnu'
            
    except dns.resolver.NXDOMAIN:
        return 'Inconnu'
    except smtplib.SMTPServerDisconnected:
        return 'Inconnu'
    except smtplib.SMTPConnectError:
        return 'Inconnu'
    except smtplib.SMTPSenderRefused:
        return 'Inconnu'
    except socket.timeout:
        return 'Erreur'
    except Exception as e:
        logger.warning(f"SMTP verify {email}: {e}")
        return 'Erreur'


def validate_email_quick(email: str) -> str:
    """
    Validation rapide d'un email via Mailcheck.ai (API gratuite, pas de clé requise).
    Retourne 'Valide', 'Invalide' ou 'Inconnu'.
    Beaucoup plus fiable que SMTP qui est souvent bloqué.
    """
    if not email or '@' not in email:
        return 'Invalide'
    
    import re
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return 'Invalide'
    
    domain = email.split('@')[1].lower()
    disposable_domains = {
        'yopmail.com', 'guerrillamail.com', 'tempmail.com', 'throwaway.email',
        'mailinator.com', 'sharklasers.com', 'guerrillamailblock.com',
        'grr.la', 'dispostable.com', 'temp-mail.org'
    }
    if domain in disposable_domains:
        return 'Invalide'
    
    try:
        import requests
        resp = requests.get(
            f'https://api.mailcheck.ai/email/{email}',
            timeout=5,
            headers={'Accept': 'application/json'}
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('disposable', False):
                return 'Invalide'
            if data.get('mx', False):
                return 'Valide'
            else:
                return 'Invalide'
    except Exception as e:
        logger.warning(f"Mailcheck API error for {email}: {e}")
    
    try:
        domain = email.split('@')[1]
        dns.resolver.resolve(domain, 'MX')
        return 'Valide'
    except Exception:
        return 'Inconnu'


def validate_pending_leads(limit: int = 50) -> dict:
    """
    Valide SMTP les leads avec email non vérifié (tous statuts).
    Traite par lot de 'limit' emails pour éviter les timeouts.
    
    Args:
        limit: Nombre max d'emails à valider par appel (défaut: 50)
    
    Returns:
        Dict avec compteurs: validated, invalid, errors, remaining
    """
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from database.db_manager import get_conn
    
    stats = {'validated': 0, 'invalid': 0, 'errors': 0, 'remaining': 0}
    
    with get_conn() as conn:
        # Récupérer les leads avec email non validés
        rows = conn.execute("""
            SELECT id, email, email_valide 
            FROM leads_bruts 
            WHERE email IS NOT NULL 
              AND email != ''
              AND (email_valide != 'Valide' OR email_valide IS NULL OR email_valide = '')
            LIMIT ?
        """, (limit,)).fetchall()
        
        print(f"  [OK] Validation de {len(rows)} emails...")
        
        for row in rows:
            lead_id = row['id']
            email = row['email']
            
            result = validate_email_quick(email)
            
            if result == 'Valide':
                conn.execute(
                    "UPDATE leads_bruts SET email_valide = 'Valide' WHERE id = ?",
                    (lead_id,)
                )
                stats['validated'] += 1
            elif result == 'Inconnu':
                conn.execute(
                    "UPDATE leads_bruts SET email_valide = 'Inconnu' WHERE id = ?",
                    (lead_id,)
                )
                stats['invalid'] += 1
            else:
                conn.execute(
                    "UPDATE leads_bruts SET email_valide = 'Erreur' WHERE id = ?",
                    (lead_id,)
                )
                stats['errors'] += 1
        
        conn.commit()
        
        # Compter les restants
        stats['remaining'] = conn.execute("""
            SELECT COUNT(*) FROM leads_bruts 
            WHERE email IS NOT NULL AND email != '' 
              AND (email_valide != 'Valide' OR email_valide IS NULL OR email_valide = '')
        """).fetchone()[0]
    
    return stats


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from config_manager import get_config
    
    # Test rapide
    test_emails = [
        "contact@clinadent.fr",
        "test@invalide-domaine-xyz123.com",
        "plomberiepatrac@hotmail.com"
    ]
    
    print("=== Test validation SMTP ===")
    for email in test_emails:
        result = verify_email_smtp(email)
        print(f"  {email}: {result}")
