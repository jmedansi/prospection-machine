# 🔴 FIX COMPLET: Pourquoi Resend n'enregistre pas les opens

## 🎯 DIAGNOSTIC

Tu as 500 mails avec **0 ouverture = IMPOSSIBLE** naturellement.

Causes:
1. ✗ **Webhook URL morte (ngrok)** → Resend a arrêté d'envoyer les événements
2. ✗ **Domaine par défaut resend.dev** → Taux de livraison mauvais, tracking unreliable
3. ✗ **Pas d'endpoint Flask fonctionnel** → Les opens ne sont pas persistées

**Plan de correction:**
1. ✅ Setup domaine custom dans Resend (avec ton domaine Cloudflare)
2. ✅ Setup Cloudflare Tunnel pour webhook permanent
3. ✅ Créer un service de webhook robuste avec logging
4. ✅ Dashboard de debug pour voir les événements en temps réel

---

## ⚡ ÉTAPE 1: CONFIGURER DOMAINE CUSTOM DANS RESEND

### Pourquoi c'est important?
- Opens/clicks tracking: **Requiert un domaine custom** (ou du moins c'est beaucoup plus fiable)
- Délivrabilité: +20% avec domaine custom
- Réputation: Ne pas dépendre du domaine Resend partagé

### Tu as un domaine Cloudflare. Processus:

1. **Aller à Resend Dashboard**
   - https://resend.com/domains
   - Cliquer "Add Domain"
   - Entrer: `mail.tudomaine.com` (ou `noreply.tudomaine.com`)

2. **Copier les records DNS** que Resend te propose

3. **Aller à Cloudflare Dashboard**
   - https://dash.cloudflare.com
   - Sélectionner ton domaine
   - DNS → Ajouter un record
   - Coller chaque record que Resend a donné (généralement 2-3 records CNAME/MX)

4. **Attendre validation (5-15 minutes)**
   - Resend va vérifier les DNS
   - Quand c'est vert = domaine activé

5. **Mettre à jour ton code Python**
   ```python
   # AVANT (domaine par défaut)
   from_email = "noreply@onboarding.resend.dev"
   
   # APRÈS (domaine custom)
   from_email = "noreply@tudomaine.com"
   ```

---

## ⚡ ÉTAPE 2: SETUP CLOUDFLARE TUNNEL (Permanent)

### Installation Windows (5 minutes)

**Via Chocolatey (le plus simple):**
```bash
# Ouvrir PowerShell en admin
choco install cloudflare-warp-cli

# Vérifier l'installation
cloudflared --version
```

**Via installer manuel:**
- Télécharger: https://github.com/cloudflare/cloudflared/releases
- Chercher: `cloudflared-windows-amd64.msi`
- Double-cliquer et installer

### Configuration (une seule fois)

**Étape 1: Se connecter à Cloudflare**
```bash
cloudflared tunnel login
# Ouvre un navigateur → tu cliques "Authorize"
# Retourne: Success! Certificate saved to ...
```

**Étape 2: Créer le tunnel**
```bash
cloudflared tunnel create prospection-webhook

# Retourne:
# Tunnel UUID: 12345678-xxxx
# Credentials file: C:\Users\jmeda\.cloudflared\12345678.json
```

**Étape 3: Créer fichier config**

Créer: `C:\Users\jmeda\.cloudflared\config.yml`

```yaml
tunnel: prospection-webhook
credentials-file: C:\Users\jmeda\.cloudflared\<YOUR_UUID>.json

ingress:
  - hostname: webhook.tudomaine.com
    service: http://localhost:5000
  - service: http_status:404
```

*(Remplacer `<YOUR_UUID>` par l'UUID de l'étape 2)*
*(Remplacer `tudomaine.com` par TON domaine)*

**Étape 4: Enregistrer le DNS (une seule fois)**
```bash
cloudflared tunnel route dns prospection-webhook webhook.tudomaine.com

# Retourne: Successfully created DNS record
```

**Étape 5: LANCER LE TUNNEL**
```bash
cloudflared tunnel run prospection-webhook

# Devrait afficher:
# Listening on https://webhook.tudomaine.com
```

✅ **Ton serveur est maintenant exposé en HTTPS permanent!**

---

## ⚡ ÉTAPE 3: CRÉER LE SERVICE WEBHOOK ROBUSTE

### Fichier: `dashboard/webhooks.py`

```python
"""
Service de gestion des webhooks Resend.
Enregistre TOUS les événements pour debugging + tracking.
"""

import sqlite3
import json
import os
from datetime import datetime
from flask import request, jsonify
from typing import Dict, Any

class WebhookService:
    """Service robuste pour gérer les webhooks Resend"""
    
    def __init__(self, db_path: str, telegram_token: str = None, telegram_chat: str = None):
        self.db_path = db_path
        self.telegram_token = telegram_token
        self.telegram_chat = telegram_chat
        self._ensure_webhook_log_table()
    
    def _ensure_webhook_log_table(self):
        """Créer la table webhook_logs si elle n'existe pas"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS webhook_logs (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                email_record_id INTEGER,
                lead_id INTEGER,
                raw_payload TEXT NOT NULL,
                processed BOOLEAN DEFAULT 0,
                error_message TEXT,
                created_at TEXT
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_webhook_timestamp 
            ON webhook_logs(timestamp)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_webhook_type 
            ON webhook_logs(event_type)
        """)
        
        conn.commit()
        conn.close()
    
    def log_webhook_raw(self, payload: Dict[str, Any]) -> int:
        """
        Enregistrer le webhook RAW dans la DB pour debugging.
        Retourne l'ID du log.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        event_type = payload.get('type', 'unknown')
        email_record_id = payload.get('email_record_id') or payload.get('message_id')
        lead_id = payload.get('lead_id')
        
        cursor.execute("""
            INSERT INTO webhook_logs 
            (timestamp, event_type, email_record_id, lead_id, raw_payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            payload.get('timestamp', datetime.now().isoformat()),
            event_type,
            email_record_id,
            lead_id,
            json.dumps(payload),
            datetime.now().isoformat()
        ))
        
        conn.commit()
        log_id = cursor.lastrowid
        conn.close()
        
        return log_id
    
    def process_webhook(self, payload: Dict[str, Any]) -> tuple:
        """
        Traiter un webhook Resend.
        Retourne: (success: bool, message: str)
        """
        event_type = payload.get('type', '')
        event_type_clean = event_type.split('.')[-1]  # 'sent', 'opened', etc
        
        # Enregistrer le webhook raw
        log_id = self.log_webhook_raw(payload)
        
        print(f"📨 Webhook reçu: {event_type_clean} (log_id={log_id})")
        print(f"   Payload: {json.dumps(payload, indent=2)}")
        
        try:
            if event_type_clean == 'sent':
                self._handle_sent(payload)
            elif event_type_clean == 'opened':
                self._handle_opened(payload)
            elif event_type_clean == 'clicked':
                self._handle_clicked(payload)
            elif event_type_clean == 'bounced':
                self._handle_bounced(payload)
            elif event_type_clean == 'complained':
                self._handle_complained(payload)
            elif event_type_clean == 'unsubscribed':
                self._handle_unsubscribed(payload)
            else:
                print(f"⚠️ Event type inconnu: {event_type}")
            
            # Marquer comme traité
            self._mark_webhook_processed(log_id, True)
            return (True, f"Event {event_type_clean} processed")
        
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Erreur traitement webhook: {error_msg}")
            self._mark_webhook_processed(log_id, False, error_msg)
            return (False, error_msg)
    
    def _handle_sent(self, payload: Dict):
        """Email envoyé avec succès"""
        email_record_id = payload.get('message_id')
        email_addr = payload.get('email')
        
        print(f"✉️ EMAIL ENVOYÉ à {email_addr}")
        
        # Mettre à jour la DB
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE emails_envoyes
            SET 
                message_id_resend = ?,
                date_envoi = ?,
                statut_envoi = 'sent'
            WHERE id = ?
        """, (email_record_id, datetime.now().isoformat(), email_record_id))
        
        conn.commit()
        conn.close()
    
    def _handle_opened(self, payload: Dict):
        """Email ouvert - C'EST CELUI-LÀ QUI NE MARCHE PAS!"""
        email_record_id = payload.get('message_id')
        user_agent = payload.get('user_agent', '')
        ip = payload.get('ip', '')
        
        print(f"👁️ EMAIL OUVERT! ID={email_record_id}")
        print(f"   IP: {ip}, User-Agent: {user_agent[:50]}...")
        
        # Mettre à jour la DB
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Vérifier si c'est la première ouverture
        cursor.execute("""
            SELECT date_premiere_ouverture, nb_ouvertures 
            FROM emails_envoyes 
            WHERE id = ?
        """, (email_record_id,))
        
        row = cursor.fetchone()
        
        if row:
            date_premiere, nb_opens = row
            is_first_open = date_premiere is None
            
            cursor.execute("""
                UPDATE emails_envoyes
                SET 
                    date_premiere_ouverture = COALESCE(date_premiere_ouverture, ?),
                    date_derniere_ouverture = ?,
                    nb_ouvertures = COALESCE(nb_ouvertures, 0) + 1,
                    ip_ouverture = ?,
                    user_agent_ouverture = ?,
                    derniere_interaction = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                ip,
                user_agent[:200],
                datetime.now().isoformat(),
                email_record_id
            ))
            
            conn.commit()
            
            # Alerte si première ouverture
            if is_first_open:
                self._send_telegram_alert(f"🎉 PREMIER OPEN! Email ID={email_record_id}")
        
        conn.close()
    
    def _handle_clicked(self, payload: Dict):
        """Lien cliqué"""
        email_record_id = payload.get('message_id')
        url = payload.get('url', '')
        ip = payload.get('ip', '')
        
        print(f"🔗 LIEN CLIQUÉ! ID={email_record_id} → {url}")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE emails_envoyes
            SET 
                clique = 1,
                nb_clics = COALESCE(nb_clics, 0) + 1,
                date_dernier_clic = ?,
                derniere_interaction = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), datetime.now().isoformat(), email_record_id))
        
        conn.commit()
        conn.close()
        
        # Alerte
        self._send_telegram_alert(f"🔥 CLIC DÉTECTÉ! Email ID={email_record_id}")
    
    def _handle_bounced(self, payload: Dict):
        """Email bounced"""
        email_record_id = payload.get('message_id')
        bounce_type = payload.get('bounce_type', 'unknown')
        reason = payload.get('reason', '')
        
        print(f"🚫 EMAIL BOUNCED! ID={email_record_id} ({bounce_type}): {reason}")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if bounce_type == 'hard':
            # Hard bounce = email n'existe pas
            cursor.execute("""
                UPDATE emails_envoyes
                SET statut_envoi = 'bounce_hard'
                WHERE id = ?
            """, (email_record_id,))
        elif bounce_type == 'soft':
            # Soft bounce = temporaire
            cursor.execute("""
                UPDATE emails_envoyes
                SET statut_envoi = 'bounce_soft'
                WHERE id = ?
            """, (email_record_id,))
        
        conn.commit()
        conn.close()
    
    def _handle_complained(self, payload: Dict):
        """Email signalé comme spam"""
        email_record_id = payload.get('message_id')
        print(f"⚠️ SPAM COMPLAINT! ID={email_record_id}")
    
    def _handle_unsubscribed(self, payload: Dict):
        """Lead a cliqué unsubscribe"""
        email_record_id = payload.get('message_id')
        print(f"🚪 UNSUBSCRIBED! ID={email_record_id}")
    
    def _mark_webhook_processed(self, log_id: int, success: bool, error: str = None):
        """Marquer le webhook comme traité"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE webhook_logs
            SET processed = ?, error_message = ?
            WHERE id = ?
        """, (1 if success else 0, error, log_id))
        
        conn.commit()
        conn.close()
    
    def _send_telegram_alert(self, message: str):
        """Envoyer une alerte Telegram"""
        if not self.telegram_token or not self.telegram_chat:
            return
        
        try:
            import requests
            requests.post(
                f'https://api.telegram.org/bot{self.telegram_token}/sendMessage',
                json={'chat_id': self.telegram_chat, 'text': message},
                timeout=5
            )
        except:
            pass
    
    def get_webhook_stats(self) -> Dict:
        """Statistiques des webhooks reçus"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Total par type
        cursor.execute("""
            SELECT event_type, COUNT(*) as count
            FROM webhook_logs
            GROUP BY event_type
            ORDER BY count DESC
        """)
        
        stats = dict(cursor.fetchall())
        
        # Derniers webhooks
        cursor.execute("""
            SELECT event_type, timestamp, created_at
            FROM webhook_logs
            ORDER BY created_at DESC
            LIMIT 20
        """)
        
        recent = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            'stats_by_type': stats,
            'recent_webhooks': recent,
            'total': sum(stats.values())
        }
```

### Intégrer dans Flask

**Modifier:** `dashboard/app.py`

```python
from webhooks import WebhookService

# Initialiser le service
webhook_service = WebhookService(
    db_path='data/prospection.db',
    telegram_token=os.getenv('TELEGRAM_BOT_TOKEN'),
    telegram_chat=os.getenv('TELEGRAM_CHAT_ID')
)

@app.route('/webhooks/resend', methods=['POST'])
def webhook_resend():
    """Endpoint pour recevoir les webhooks Resend"""
    data = request.json
    
    # Traiter le webhook
    success, message = webhook_service.process_webhook(data)
    
    # Répondre IMMÉDIATEMENT (important pour Resend)
    if success:
        return jsonify({'success': True, 'message': message}), 200
    else:
        return jsonify({'success': False, 'error': message}), 500
```

---

## ⚡ ÉTAPE 4: DASHBOARD DE DEBUG

### Fichier: `dashboard/templates/webhook_debug.html`

```html
<!DOCTYPE html>
<html>
<head>
    <title>🔍 Webhook Debug Dashboard</title>
    <style>
        body {
            font-family: monospace;
            background: #1e1e1e;
            color: #0f0;
            padding: 20px;
            margin: 0;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        h1 { color: #0f0; margin-bottom: 30px; }
        
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .stat-box {
            background: #2d2d2d;
            border: 2px solid #0f0;
            padding: 20px;
            border-radius: 5px;
        }
        
        .stat-box h3 {
            margin: 0 0 10px 0;
            color: #0f0;
        }
        
        .stat-box .number {
            font-size: 2em;
            font-weight: bold;
            color: #0f0;
        }
        
        .webhook-list {
            background: #2d2d2d;
            border: 2px solid #0f0;
            padding: 20px;
            border-radius: 5px;
        }
        
        .webhook-item {
            background: #1e1e1e;
            border-left: 4px solid #0f0;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 3px;
        }
        
        .webhook-item.sent { border-left-color: #00ff00; }
        .webhook-item.opened { border-left-color: #00ff88; }
        .webhook-item.clicked { border-left-color: #ffff00; }
        .webhook-item.bounced { border-left-color: #ff0000; }
        
        .timestamp {
            color: #888;
            font-size: 0.9em;
        }
        
        .event-type {
            font-weight: bold;
            color: #0f0;
        }
        
        .refresh-btn {
            background: #0f0;
            color: #000;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-weight: bold;
            margin-bottom: 20px;
        }
        
        .refresh-btn:hover {
            background: #00ff00;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Resend Webhook Debug Dashboard</h1>
        
        <button class="refresh-btn" onclick="location.reload()">🔄 Rafraîchir</button>
        
        <div class="stats" id="stats"></div>
        
        <div class="webhook-list">
            <h2>📨 Derniers Webhooks Reçus</h2>
            <div id="webhooks"></div>
        </div>
    </div>
    
    <script>
        async function loadStats() {
            const response = await fetch('/api/webhook-stats');
            const data = await response.json();
            
            const statsDiv = document.getElementById('stats');
            statsDiv.innerHTML = '';
            
            const total = data.total || 0;
            statsDiv.innerHTML += `
                <div class="stat-box">
                    <h3>Total Webhooks</h3>
                    <div class="number">${total}</div>
                </div>
            `;
            
            Object.entries(data.stats_by_type || {}).forEach(([type, count]) => {
                let emoji = '';
                if (type === 'sent') emoji = '✉️';
                if (type === 'opened') emoji = '👁️';
                if (type === 'clicked') emoji = '🔗';
                if (type === 'bounced') emoji = '🚫';
                
                statsDiv.innerHTML += `
                    <div class="stat-box">
                        <h3>${emoji} ${type.toUpperCase()}</h3>
                        <div class="number">${count}</div>
                    </div>
                `;
            });
            
            const webhooksDiv = document.getElementById('webhooks');
            webhooksDiv.innerHTML = '';
            
            (data.recent_webhooks || []).forEach(webhook => {
                const time = new Date(webhook.timestamp).toLocaleString();
                webhooksDiv.innerHTML += `
                    <div class="webhook-item ${webhook.event_type}">
                        <div class="event-type">${webhook.event_type.toUpperCase()}</div>
                        <div class="timestamp">${time}</div>
                    </div>
                `;
            });
        }
        
        // Charger les stats immédiatement et toutes les 5 secondes
        loadStats();
        setInterval(loadStats, 5000);
    </script>
</body>
</html>
```

### Route Flask pour le dashboard

```python
@app.route('/webhook-debug')
def webhook_debug():
    """Page de debug des webhooks"""
    return render_template('webhook_debug.html')

@app.route('/api/webhook-stats')
def webhook_stats():
    """API pour récupérer les stats de webhooks"""
    stats = webhook_service.get_webhook_stats()
    return jsonify(stats)
```

---

## ⚡ ÉTAPE 5: CONFIGURATION FINALE RESEND

### Dans le Dashboard Resend:

1. **Webhooks** → https://resend.com/webhooks

2. **Ajouter un webhook:**
   - URL: `https://webhook.tudomaine.com/webhooks/resend`
   - Events à sélectionner:
     - ✅ Email sent
     - ✅ Email opened
     - ✅ Email clicked
     - ✅ Email bounced
     - ✅ Spam complaint
     - ✅ Unsubscribe

3. **Tester:**
   - Cliquer "Send test event"
   - Vérifier le dashboard: https://webhook.tudomaine.com/webhook-debug

---

## 🚀 RÉSUMÉ DES COMMANDES

### Première fois (setup complet):

```bash
# 1. Installer cloudflared
choco install cloudflare-warp-cli

# 2. Se connecter
cloudflared tunnel login

# 3. Créer le tunnel
cloudflared tunnel create prospection-webhook

# 4. Enregistrer le DNS
cloudflared tunnel route dns prospection-webhook webhook.tudomaine.com

# 5. Lancer le tunnel (à faire à chaque fois)
cloudflared tunnel run prospection-webhook

# 6. Dans un autre terminal, lancer Flask
python dashboard/app.py
```

### Chaque jour (après setup):

```bash
# Terminal 1: Tunnel Cloudflare
cloudflared tunnel run prospection-webhook

# Terminal 2: Flask
python dashboard/app.py

# Visiter:
# - Dashboard: http://localhost:5000
# - Webhook Debug: http://localhost:5000/webhook-debug
```

---

## ✅ CHECKLIST COMPLÈTE

- [ ] Domaine custom configuré dans Resend (avec DNS Cloudflare)
- [ ] Code d'envoi mis à jour avec nouveau domaine
- [ ] Cloudflare Tunnel installé et configuré
- [ ] `dashboard/webhooks.py` créé
- [ ] `dashboard/app.py` modifié pour intégrer WebhookService
- [ ] `dashboard/templates/webhook_debug.html` créé
- [ ] Flask lancé avec tunnel Cloudflare ouvert
- [ ] Webhook URL dans Resend = `https://webhook.tudomaine.com/webhooks/resend`
- [ ] Envoyer un email test
- [ ] Vérifier le dashboard debug: http://localhost:5000/webhook-debug
- [ ] Voir "opened" quand tu ouvres l'email

---

## 🔥 PROBLÈMES ET SOLUTIONS

### "Domaine non trouvé"
```
❌ webhook.tudomaine.com ne résout pas
→ Vérifier que cloudflared tunnel route dns a été exécuté
→ Attendre 5 minutes pour la propagation DNS
→ Tester: nslookup webhook.tudomaine.com
```

### "Webhook pas reçu"
```
❌ Resend envoie mais Flask ne reçoit pas
→ Vérifier que tunnel est lancé: cloudflared tunnel list
→ Vérifier Flask écoute: http://localhost:5000
→ Tester l'endpoint: curl https://webhook.tudomaine.com/webhooks/resend
```

### "Toujours 0 ouverture"
```
❌ Les events arrivent mais pas traités
→ Aller à http://localhost:5000/webhook-debug
→ Envoyer un email, ouvrir-le, attendre 10s
→ Vérifier que tu vois "opened" dans le dashboard
→ Si pas présent = webhook n'arrive pas
→ Si présent = c'est un bug dans _handle_opened()
```

---

**Prêt? Commence par créer le domaine custom dans Resend! 🚀**

