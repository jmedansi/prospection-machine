# 📋 WALKTHROUGH: Plan d'implémentation complet pour agent d'exécution

**Objectif:** Corriger les problèmes critiques de synchronisation, améliorer le tracking client et automatiser les relances.

**Durée estimée:** 3-4 semaines  
**Ordre d'exécution:** Phases 1 → 2 → 3 (dépendances)

---

## 🔴 PHASE 1: CORRECTIONS CRITIQUES (Semaine 1)

### Objectif
Sécuriser les opérations critiques avec transactions atomiques et gestion d'erreurs robuste.

### État actuel du problème
- **pipeline.py** insère dans emails_envoyes avec approuve=0
- **app.py** /api/previews/push met à jour lien_rapport dans emails_envoyes ET leads_audites séparément
- **resend_sender.py** met à jour message_id_resend sans gestion d'erreur
- **Risque:** Incohérence entre leads_audites et emails_envoyes

---

## 📝 TASK 1.1: Créer la classe EmailTrackingService

### Fichiers à créer
`envoi/email_tracking_service.py`

### Code à implémenter
```python
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any

class EmailTrackingService:
    """Service centralisé pour toutes les opérations sur emails_envoyes"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def _get_conn(self):
        """Obtenir une connexion avec row_factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    # ========== OPÉRATIONS DE BASE ==========
    
    def create_email_record(
        self,
        lead_id: int,
        email: str,
        subject: str,
        body: str,
        lien_rapport: Optional[str] = None,
        approuve: int = 0
    ) -> int:
        """
        Créer un nouvel enregistrement dans emails_envoyes.
        Retourne l'ID de l'enregistrement créé.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO emails_envoyes 
                (lead_id, email, sujet, corps, lien_rapport, approuve, date_creation)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (lead_id, email, subject, body, lien_rapport, approuve, datetime.now().isoformat()))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
    
    def update_rapport_link(
        self,
        email_record_id: int,
        lead_id: int,
        lien_rapport: str
    ) -> bool:
        """
        TRANSACTION ATOMIQUE: Mettre à jour lien_rapport dans les DEUX tables.
        - leads_audites.lien_rapport
        - emails_envoyes.lien_rapport
        
        Retourne True si succès, False si erreur.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            # Commencer la transaction
            cursor.execute("BEGIN IMMEDIATE")
            
            # Vérifier que le lien est accessible avant de l'enregistrer
            if not self._validate_rapport_link(lien_rapport):
                conn.rollback()
                return False
            
            # Mise à jour atomique
            cursor.execute("""
                UPDATE leads_audites 
                SET lien_rapport = ? 
                WHERE id = ?
            """, (lien_rapport, lead_id))
            
            cursor.execute("""
                UPDATE emails_envoyes 
                SET lien_rapport = ? 
                WHERE id = ?
            """, (lien_rapport, email_record_id))
            
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            print(f"Erreur update_rapport_link: {e}")
            return False
        finally:
            conn.close()
    
    def update_message_id(
        self,
        email_record_id: int,
        message_id_resend: str
    ) -> bool:
        """
        Mettre à jour message_id_resend après envoi réussi.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE emails_envoyes 
                SET message_id_resend = ?, date_envoi = ?
                WHERE id = ?
            """, (message_id_resend, datetime.now().isoformat(), email_record_id))
            conn.commit()
            return True
        except Exception as e:
            print(f"Erreur update_message_id: {e}")
            return False
        finally:
            conn.close()
    
    def mark_send_error(
        self,
        email_record_id: int,
        error_message: str,
        retry_count: int = 0
    ) -> bool:
        """
        Marquer un email comme ayant échoué à l'envoi.
        Incrémenter le nombre de tentatives.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE emails_envoyes 
                SET 
                    statut_envoi = 'erreur',
                    message_erreur = ?,
                    nb_tentatives_envoi = ?,
                    date_dernier_essai = ?
                WHERE id = ?
            """, (error_message, retry_count, datetime.now().isoformat(), email_record_id))
            conn.commit()
            return True
        except Exception as e:
            print(f"Erreur mark_send_error: {e}")
            return False
        finally:
            conn.close()
    
    # ========== VALIDATION ==========
    
    def _validate_rapport_link(self, lien_rapport: str) -> bool:
        """
        Vérifier que le lien est valide avant l'enregistrer:
        - Commence par https://
        - N'est pas vide
        """
        if not lien_rapport:
            return False
        if not lien_rapport.startswith("https://"):
            print(f"Lien non HTTPS: {lien_rapport}")
            return False
        return True
    
    def get_email_record(self, email_record_id: int) -> Optional[Dict[str, Any]]:
        """Récupérer un enregistrement email"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM emails_envoyes WHERE id = ?", (email_record_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
```

### Intégration dans le code existant

**Mettre à jour:** `pipeline.py` (génération d'emails)

Remplacer:
```python
# ANCIEN CODE
cursor.execute("""
    INSERT INTO emails_envoyes (lead_id, email, sujet, corps, approuve)
    VALUES (?, ?, ?, ?, 0)
""", (...))
```

Par:
```python
# NOUVEAU CODE
from envoi.email_tracking_service import EmailTrackingService
tracking_service = EmailTrackingService(db_path)
email_record_id = tracking_service.create_email_record(
    lead_id=lead_id,
    email=email,
    subject=subject,
    body=body,
    approuve=0
)
```

---

## 📝 TASK 1.2: Sécuriser l'endpoint /api/previews/push

### Fichier à modifier
`dashboard/app.py` - fonction `push_preview` (route POST /api/previews/push)

### État actuel
```python
# ANCIEN: Deux mises à jour séparées = RISQUE
cursor.execute("UPDATE leads_audites SET lien_rapport = ? WHERE id = ?", (...))
cursor.execute("UPDATE emails_envoyes SET lien_rapport = ? WHERE id = ?", (...))
conn.commit()  # Si ça échoue à mi-chemin = incohérence
```

### Nouvelle implémentation
```python
from envoi.email_tracking_service import EmailTrackingService

@app.route('/api/previews/push', methods=['POST'])
def push_preview():
    data = request.json
    lead_id = data.get('lead_id')
    email_record_id = data.get('email_record_id')
    lien_rapport = data.get('lien_rapport')
    
    # Valider que lien_rapport est HTTPS
    if not lien_rapport.startswith('https://'):
        return jsonify({'error': 'Lien non HTTPS'}), 400
    
    # Utiliser le service pour une transaction atomique
    tracking_service = EmailTrackingService(db_path)
    success = tracking_service.update_rapport_link(
        email_record_id=email_record_id,
        lead_id=lead_id,
        lien_rapport=lien_rapport
    )
    
    if not success:
        return jsonify({'error': 'Échec mise à jour cohérente'}), 500
    
    return jsonify({'success': True, 'lien_rapport': lien_rapport})
```

---

## 📝 TASK 1.3: Ajouter gestion d'erreurs Resend avec retry

### Fichier à modifier
`envoi/resend_sender.py`

### Code actuel (problème)
```python
# ANCIEN: Si Resend retourne une erreur, pas de gestion
response = resend.emails.send({
    'from': 'sender@example.com',
    'to': email,
    'html': body
})
# Si ça échoue, c'est silencieux!
```

### Nouvelle implémentation
```python
import time
from typing import Tuple, Optional

class ResendSenderWithRetry:
    def __init__(self, api_key: str, db_path: str, max_retries: int = 3):
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
```

### Schéma BD: Ajouter colonnes si nécessaire

```sql
-- Exécuter si les colonnes n'existent pas
ALTER TABLE emails_envoyes ADD COLUMN statut_envoi TEXT DEFAULT 'en_attente';
ALTER TABLE emails_envoyes ADD COLUMN message_erreur TEXT;
ALTER TABLE emails_envoyes ADD COLUMN nb_tentatives_envoi INTEGER DEFAULT 0;
ALTER TABLE emails_envoyes ADD COLUMN date_dernier_essai TEXT;
```

---

## 🎯 PHASE 1 - RÉSUMÉ D'EXÉCUTION

✅ **Checklist Phase 1**

- [ ] Créer `envoi/email_tracking_service.py` avec classe EmailTrackingService
- [ ] Mettre à jour `pipeline.py` pour utiliser EmailTrackingService.create_email_record()
- [ ] Mettre à jour `dashboard/app.py` endpoint /api/previews/push avec transaction atomique
- [ ] Créer `envoi/resend_sender_with_retry.py` avec gestion erreurs
- [ ] Mettre à jour `database/db_manager.py` pour ajouter colonnes statut_envoi, message_erreur, etc.
- [ ] Tester end-to-end: génération → approuvation → envoi avec un lead test

---

## 🟡 PHASE 2: AMÉLIORATION DU TRACKING (Semaine 2)

### Objectif
Enrichir les données collectées pour avoir une vue complète du parcours de chaque lead.

---

## 📝 TASK 2.1: Créer la table email_events

### Fichier à modifier
`database/db_manager.py` - fonction `init_db()`

### SQL à ajouter
```sql
CREATE TABLE IF NOT EXISTS email_events (
    id INTEGER PRIMARY KEY,
    email_record_id INTEGER NOT NULL,
    lead_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,  -- 'sent', 'opened', 'clicked', 'bounced', 'unsubscribed'
    event_data TEXT,  -- JSON avec métadonnées (ip, user_agent, etc.)
    timestamp TEXT NOT NULL,
    FOREIGN KEY (email_record_id) REFERENCES emails_envoyes(id),
    FOREIGN KEY (lead_id) REFERENCES leads_audites(id)
);

CREATE INDEX IF NOT EXISTS idx_email_events_email_record ON email_events(email_record_id);
CREATE INDEX IF NOT EXISTS idx_email_events_lead ON email_events(lead_id);
CREATE INDEX IF NOT EXISTS idx_email_events_type ON email_events(event_type);
CREATE INDEX IF NOT EXISTS idx_email_events_timestamp ON email_events(timestamp);
```

### Modifier: dashboard/app.py webhook Resend

```python
import json
from datetime import datetime

@app.route('/webhooks/resend', methods=['POST'])
def webhook_resend():
    """
    Webhook Resend - Enregistrer TOUS les événements dans email_events
    """
    data = request.json
    event_type = data.get('type')  # 'email.sent', 'email.opened', 'email.clicked', etc.
    email_record_id = data.get('email_record_id') or data.get('message_id')
    
    # Nettoyer le type d'événement
    event_type_clean = event_type.split('.')[-1]  # 'sent', 'opened', etc.
    
    # Collecter les métadonnées
    event_data = {
        'user_agent': data.get('user_agent'),
        'ip': data.get('ip'),
        'timestamp_resend': data.get('timestamp')
    }
    
    if event_type_clean == 'bounced':
        event_data['bounce_type'] = data.get('bounce_type')  # 'soft' ou 'hard'
        event_data['reason'] = data.get('reason')
    
    # Enregistrer dans email_events
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO email_events 
            (email_record_id, lead_id, event_type, event_data, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (
            email_record_id,
            data.get('lead_id'),
            event_type_clean,
            json.dumps(event_data),
            datetime.now().isoformat()
        ))
        conn.commit()
    finally:
        conn.close()
    
    # Traiter les événements spécifiques
    if event_type_clean == 'opened':
        _handle_email_opened(email_record_id)
    elif event_type_clean == 'clicked':
        _handle_email_clicked(email_record_id, data.get('url'))
    elif event_type_clean == 'bounced':
        _handle_email_bounced(email_record_id, data.get('bounce_type'))
    
    return jsonify({'success': True}), 200

def _handle_email_opened(email_record_id: int):
    """Mettre à jour l'email quand il est ouvert"""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE emails_envoyes 
            SET 
                date_ouverture = ?,
                clique = COALESCE(clique, 0)
            WHERE id = ?
        """, (datetime.now().isoformat(), email_record_id))
        conn.commit()
    finally:
        conn.close()

def _handle_email_clicked(email_record_id: int, url: str):
    """Mettre à jour l'email quand le lien est cliqué"""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE emails_envoyes 
            SET 
                clique = 1,
                date_dernier_clic = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), email_record_id))
        conn.commit()
    finally:
        conn.close()

def _handle_email_bounced(email_record_id: int, bounce_type: str):
    """Gérer les bounces"""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        
        if bounce_type == 'hard':
            # Bounce dur = désactiver le lead
            cursor.execute("""
                UPDATE emails_envoyes 
                SET statut_envoi = 'bounce_dur'
                WHERE id = ?
            """, (email_record_id,))
        elif bounce_type == 'soft':
            # Bounce mou = marquer pour retry
            cursor.execute("""
                UPDATE emails_envoyes 
                SET statut_envoi = 'bounce_mou'
                WHERE id = ?
            """, (email_record_id,))
        
        conn.commit()
    finally:
        conn.close()
```

---

## 📝 TASK 2.2: Étendre le schéma emails_envoyes

### Colonnes à ajouter (si n'existent pas)

```sql
-- Tracking détaillé des ouvertures
ALTER TABLE emails_envoyes ADD COLUMN date_premiere_ouverture TEXT;
ALTER TABLE emails_envoyes ADD COLUMN date_derniere_ouverture TEXT;
ALTER TABLE emails_envoyes ADD COLUMN nb_ouvertures INTEGER DEFAULT 0;

-- Tracking détaillé des clics
ALTER TABLE emails_envoyes ADD COLUMN nb_clics INTEGER DEFAULT 0;
ALTER TABLE emails_envoyes ADD COLUMN date_dernier_clic TEXT;

-- Métadonnées de sécurité
ALTER TABLE emails_envoyes ADD COLUMN ip_ouverture TEXT;
ALTER TABLE emails_envoyes ADD COLUMN user_agent_ouverture TEXT;

-- Planification des relances
ALTER TABLE emails_envoyes ADD COLUMN date_relance_prevue TEXT;
ALTER TABLE emails_envoyes ADD COLUMN relance_type TEXT;  -- 'initial', 'relance_1', 'relance_2'

-- Qualité du lead
ALTER TABLE emails_envoyes ADD COLUMN lead_temperature TEXT;  -- 'chaud', 'tiede', 'froid'
ALTER TABLE emails_envoyes ADD COLUMN derniere_interaction TEXT;
ALTER TABLE emails_envoyes ADD COLUMN score_lead INTEGER DEFAULT 0;
```

### Migration helper: `database/migrations.py`

```python
import sqlite3

def get_missing_columns(db_path: str) -> dict:
    """Vérifier quelles colonnes manquent"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(emails_envoyes)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    required_columns = {
        'date_premiere_ouverture',
        'date_derniere_ouverture',
        'nb_ouvertures',
        'nb_clics',
        'date_dernier_clic',
        'ip_ouverture',
        'user_agent_ouverture',
        'date_relance_prevue',
        'relance_type',
        'lead_temperature',
        'derniere_interaction',
        'score_lead'
    }
    
    missing = required_columns - existing_columns
    conn.close()
    return missing

def add_missing_columns(db_path: str):
    """Ajouter les colonnes manquantes"""
    missing = get_missing_columns(db_path)
    
    if not missing:
        print("✅ Toutes les colonnes sont présentes")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    for col in missing:
        if col in ['nb_ouvertures', 'nb_clics', 'score_lead']:
            default = 'DEFAULT 0'
        else:
            default = ''
        
        try:
            cursor.execute(f"ALTER TABLE emails_envoyes ADD COLUMN {col} TEXT {default}")
            print(f"✅ Colonne ajoutée: {col}")
        except sqlite3.OperationalError as e:
            print(f"⚠️ Colonne déjà existante ou erreur: {col} - {e}")
    
    conn.commit()
    conn.close()
```

---

## 🎯 PHASE 2 - RÉSUMÉ D'EXÉCUTION

✅ **Checklist Phase 2**

- [ ] Créer table `email_events` dans `database/db_manager.py`
- [ ] Créer `database/migrations.py` pour ajouter colonnes manquantes
- [ ] Exécuter la migration: `python -m database.migrations` 
- [ ] Enrichir webhook `/webhooks/resend` pour enregistrer tous les événements
- [ ] Implémenter `_handle_email_opened()`, `_handle_email_clicked()`, `_handle_email_bounced()`
- [ ] Tester webhook avec événements Resend simulés

---

## 🟢 PHASE 3: AUTOMATION COMMERCIALE (Semaine 3-4)

### Objectif
Implémenter les relances automatiques, le scoring des leads et les alertes Telegram.

---

## 📝 TASK 3.1: Créer la table email_sequences

### SQL à ajouter

```sql
CREATE TABLE IF NOT EXISTS email_sequences (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL,
    email_record_id INTEGER,
    email_type TEXT NOT NULL,  -- 'initial', 'relance_1', 'relance_2', 'relance_special'
    statut TEXT DEFAULT 'planned',  -- 'planned', 'sent', 'cancelled', 'bounced'
    date_planifiee TEXT NOT NULL,
    date_envoi TEXT,
    condition_envoi TEXT,  -- JSON
    created_at TEXT NOT NULL,
    FOREIGN KEY (lead_id) REFERENCES leads_audites(id),
    FOREIGN KEY (email_record_id) REFERENCES emails_envoyes(id)
);

CREATE INDEX IF NOT EXISTS idx_sequences_lead ON email_sequences(lead_id);
CREATE INDEX IF NOT EXISTS idx_sequences_statut ON email_sequences(statut);
CREATE INDEX IF NOT EXISTS idx_sequences_date_planifiee ON email_sequences(date_planifiee);
```

---

## 📝 TASK 3.2: Créer le système de scoring

### Fichier à créer
`services/lead_scoring_service.py`

```python
import sqlite3
from datetime import datetime, timedelta
import json

class LeadScoringService:
    """Calculer et mettre à jour le score des leads"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.POINTS = {
            'email_sent': 1,
            'email_opened': 10,
            'link_clicked': 50,
            'response_received': 100,
            'daily_decay': -5  # Par jour depuis la dernière interaction
        }
    
    def calculate_lead_score(self, lead_id: int) -> int:
        """Calculer le score total d'un lead"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        score = 0
        
        # Points pour envois
        cursor.execute("""
            SELECT COUNT(*) FROM email_events 
            WHERE lead_id = ? AND event_type = 'sent'
        """, (lead_id,))
        sent_count = cursor.fetchone()[0]
        score += sent_count * self.POINTS['email_sent']
        
        # Points pour ouvertures
        cursor.execute("""
            SELECT COUNT(*) FROM email_events 
            WHERE lead_id = ? AND event_type = 'opened'
        """, (lead_id,))
        opened_count = cursor.fetchone()[0]
        score += opened_count * self.POINTS['email_opened']
        
        # Points pour clics
        cursor.execute("""
            SELECT COUNT(*) FROM email_events 
            WHERE lead_id = ? AND event_type = 'clicked'
        """, (lead_id,))
        clicked_count = cursor.fetchone()[0]
        score += clicked_count * self.POINTS['link_clicked']
        
        # Points pour réponses (si table existe)
        cursor.execute("""
            SELECT COUNT(*) FROM email_events 
            WHERE lead_id = ? AND event_type IN ('replied', 'responded')
        """, (lead_id,))
        response_count = cursor.fetchone()[0]
        score += response_count * self.POINTS['response_received']
        
        # Décroissance temporelle
        cursor.execute("""
            SELECT MAX(timestamp) FROM email_events 
            WHERE lead_id = ?
        """, (lead_id,))
        last_interaction = cursor.fetchone()[0]
        
        if last_interaction:
            last_date = datetime.fromisoformat(last_interaction)
            days_since = (datetime.now() - last_date).days
            score += days_since * self.POINTS['daily_decay']
        
        # Minimum 0
        score = max(0, score)
        
        conn.close()
        return score
    
    def classify_temperature(self, score: int) -> str:
        """Classer la température d'un lead"""
        if score >= 100:
            return 'chaud'
        elif score >= 30:
            return 'tiede'
        else:
            return 'froid'
    
    def update_lead_score(self, lead_id: int) -> tuple:
        """Calculer et persister le score + température"""
        score = self.calculate_lead_score(lead_id)
        temperature = self.classify_temperature(score)
        
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE emails_envoyes
                SET 
                    score_lead = ?,
                    lead_temperature = ?,
                    derniere_interaction = ?
                WHERE lead_id = ?
            """, (score, temperature, datetime.now().isoformat(), lead_id))
            conn.commit()
            return (score, temperature)
        finally:
            conn.close()
    
    def get_hot_leads(self, min_temperature: str = 'chaud', limit: int = 50) -> list:
        """Récupérer les leads chauds pour relance"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        temp_values = []
        if min_temperature == 'chaud':
            temp_values = ['chaud']
        elif min_temperature == 'tiede':
            temp_values = ['chaud', 'tiede']
        else:
            temp_values = ['froid', 'tiede', 'chaud']
        
        placeholders = ','.join('?' * len(temp_values))
        cursor.execute(f"""
            SELECT * FROM emails_envoyes
            WHERE lead_temperature IN ({placeholders})
            ORDER BY score_lead DESC
            LIMIT ?
        """, (*temp_values, limit))
        
        leads = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        conn.close()
        return leads
```

---

## 📝 TASK 3.3: Créer le service de relances automatisées

### Fichier à créer
`services/email_sequence_service.py`

```python
import sqlite3
from datetime import datetime, timedelta
import json

class EmailSequenceService:
    """Gérer les séquences de relances"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def plan_sequences_for_lead(self, lead_id: int, initial_email_record_id: int):
        """
        Planifier les relances pour un lead après l'email initial.
        
        Séquence par défaut:
        - Jour 3: Relance 1 (pour les non-clics)
        - Jour 7: Relance 2 (pour les ouvertures sans clic)
        - Jour 14: Relance spéciale haute-valeur (si lead tiède/chaud)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Récupérer la date d'envoi initial
        cursor.execute("""
            SELECT date_envoi FROM emails_envoyes WHERE id = ?
        """, (initial_email_record_id,))
        row = cursor.fetchone()
        if not row or not row[0]:
            conn.close()
            return
        
        initial_send_date = datetime.fromisoformat(row[0])
        
        # Planifier les relances
        sequences = [
            {
                'email_type': 'relance_1',
                'days_offset': 3,
                'condition': json.dumps({'nb_clics': 0})
            },
            {
                'email_type': 'relance_2',
                'days_offset': 7,
                'condition': json.dumps({'nb_clics': 0, 'date_ouverture': True})
            },
            {
                'email_type': 'relance_special',
                'days_offset': 14,
                'condition': json.dumps({'lead_temperature': ['chaud', 'tiede']})
            }
        ]
        
        now = datetime.now()
        
        for seq in sequences:
            date_planifiee = initial_send_date + timedelta(days=seq['days_offset'])
            
            cursor.execute("""
                INSERT INTO email_sequences
                (lead_id, email_record_id, email_type, statut, date_planifiee, condition_envoi, created_at)
                VALUES (?, ?, ?, 'planned', ?, ?, ?)
            """, (
                lead_id,
                initial_email_record_id,
                seq['email_type'],
                date_planifiee.isoformat(),
                seq['condition'],
                now.isoformat()
            ))
        
        conn.commit()
        conn.close()
    
    def get_sequences_to_send(self) -> list:
        """Récupérer les séquences prêtes à être envoyées"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute("""
            SELECT 
                seq.*,
                ee.lead_id,
                ee.email,
                ee.score_lead,
                ee.lead_temperature
            FROM email_sequences seq
            JOIN emails_envoyes ee ON seq.email_record_id = ee.id
            WHERE 
                seq.statut = 'planned'
                AND seq.date_planifiee <= ?
            ORDER BY seq.date_planifiee ASC
        """, (now,))
        
        sequences = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        conn.close()
        
        return sequences
    
    def should_send_sequence(self, sequence: dict) -> bool:
        """Vérifier si les conditions sont respectées pour envoyer"""
        condition_str = sequence.get('condition_envoi')
        if not condition_str:
            return True
        
        try:
            condition = json.loads(condition_str)
        except:
            return True
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        lead_id = sequence['lead_id']
        
        # Vérifier les conditions
        if 'nb_clics' in condition:
            cursor.execute("""
                SELECT nb_clics FROM emails_envoyes WHERE lead_id = ?
            """, (lead_id,))
            row = cursor.fetchone()
            if row and row[0] >= condition['nb_clics']:
                conn.close()
                return False
        
        conn.close()
        return True
    
    def mark_sequence_sent(self, sequence_id: int, email_record_id: int):
        """Marquer une séquence comme envoyée"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE email_sequences
            SET statut = 'sent', date_envoi = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), sequence_id))
        
        conn.commit()
        conn.close()
```

---

## 📝 TASK 3.4: Ajouter alertes Telegram pour leads chauds

### Fichier à modifier
`dashboard/app.py` - webhook Resend

```python
def _send_telegram_alert_if_hot(email_record_id: int, event_type: str):
    """Envoyer une alerte Telegram si un lead devient chaud"""
    import requests
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Récupérer le lead
    cursor.execute("""
        SELECT lead_id, score_lead, lead_temperature 
        FROM emails_envoyes 
        WHERE id = ?
    """, (email_record_id,))
    
    row = cursor.fetchone()
    if not row:
        conn.close()
        return
    
    lead_id, score, temperature = row
    
    # Conditions pour alerte
    if temperature == 'chaud' and score >= 100:
        cursor.execute("""
            SELECT nom, email FROM leads_audites WHERE id = ?
        """, (lead_id,))
        lead = cursor.fetchone()
        
        if lead:
            nom, email = lead
            message = f"""
🔥 LEAD CHAUD DÉTECTÉ!

Nom: {nom}
Email: {email}
Score: {score}
Température: {temperature}
Dernier événement: {event_type}

Action: Préparer une relance personnalisée!
            """
            
            # Envoyer via Telegram
            telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
            telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
            
            requests.post(
                f'https://api.telegram.org/bot{telegram_token}/sendMessage',
                json={
                    'chat_id': telegram_chat_id,
                    'text': message
                }
            )
    
    conn.close()
```

---

## 📝 TASK 3.5: Enrichir /api/stats avec agrégation temporelle

### Fichier à modifier
`dashboard/app.py` - route `/api/stats`

```python
@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Retourner les stats avec agrégation temporelle"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    now = datetime.now()
    
    # Periods
    periods = {
        'today': (now - timedelta(days=1)).isoformat(),
        '7days': (now - timedelta(days=7)).isoformat(),
        '30days': (now - timedelta(days=30)).isoformat(),
        'all_time': '1970-01-01T00:00:00'
    }
    
    stats = {}
    
    for period_name, from_date in periods.items():
        # Emails envoyés
        cursor.execute("""
            SELECT COUNT(*) FROM emails_envoyes 
            WHERE date_envoi >= ?
        """, (from_date,))
        sent = cursor.fetchone()[0]
        
        # Emails ouverts
        cursor.execute("""
            SELECT COUNT(*) FROM emails_envoyes 
            WHERE date_envoi >= ? AND date_ouverture IS NOT NULL
        """, (from_date,))
        opened = cursor.fetchone()[0]
        
        # Emails avec clic
        cursor.execute("""
            SELECT COUNT(*) FROM emails_envoyes 
            WHERE date_envoi >= ? AND clique = 1
        """, (from_date,))
        clicked = cursor.fetchone()[0]
        
        # Leads "chauds"
        cursor.execute("""
            SELECT COUNT(*) FROM emails_envoyes 
            WHERE date_envoi >= ? AND lead_temperature = 'chaud'
        """, (from_date,))
        hot_leads = cursor.fetchone()[0]
        
        open_rate = (opened / sent * 100) if sent > 0 else 0
        click_rate = (clicked / sent * 100) if sent > 0 else 0
        
        stats[period_name] = {
            'sent': sent,
            'opened': opened,
            'clicked': clicked,
            'hot_leads': hot_leads,
            'open_rate_pct': round(open_rate, 2),
            'click_rate_pct': round(click_rate, 2)
        }
    
    conn.close()
    
    return jsonify({
        'data': stats,
        'timestamp': now.isoformat()
    })
```

---

## 🎯 PHASE 3 - RÉSUMÉ D'EXÉCUTION

✅ **Checklist Phase 3**

- [ ] Créer table `email_sequences` dans `database/db_manager.py`
- [ ] Créer `services/lead_scoring_service.py`
- [ ] Créer `services/email_sequence_service.py`
- [ ] Ajouter alertes Telegram dans webhook Resend
- [ ] Enrichir endpoint `/api/stats` avec agrégation temporelle
- [ ] Créer un worker (cron ou scheduler) pour: 
  - Appeler `email_sequence_service.get_sequences_to_send()`
  - Valider conditions avec `should_send_sequence()`
  - Envoyer les emails via ResendSenderWithRetry
  - Mettre à jour les scores avec LeadScoringService

---

## ⚙️ WORKER DE RELANCES AUTOMATISÉES

### Fichier à créer
`workers/sequence_worker.py`

```python
#!/usr/bin/env python
"""
Worker pour exécuter les séquences de relances planifiées.
À exécuter toutes les heures via cron ou un scheduler.

Commande: python -m workers.sequence_worker
"""

import sqlite3
from datetime import datetime
from services.email_sequence_service import EmailSequenceService
from services.lead_scoring_service import LeadScoringService
from envoi.resend_sender import ResendSenderWithRetry
import os

def run_sequence_worker():
    db_path = os.getenv('DB_PATH', 'data/prospection.db')
    
    seq_service = EmailSequenceService(db_path)
    scoring_service = LeadScoringService(db_path)
    sender = ResendSenderWithRetry(
        api_key=os.getenv('RESEND_API_KEY'),
        db_path=db_path
    )
    
    # Récupérer les séquences prêtes
    sequences = seq_service.get_sequences_to_send()
    print(f"📧 {len(sequences)} séquences à traiter")
    
    for seq in sequences:
        # Vérifier les conditions
        if not seq_service.should_send_sequence(seq):
            print(f"⏭️  Séquence {seq['id']} ignorée (condition non respectée)")
            continue
        
        # Récupérer le lead et ses infos
        lead_id = seq['lead_id']
        email = seq['email']
        temp = seq['lead_temperature']
        
        # Générer le corps de l'email selon le type
        email_type = seq['email_type']
        if email_type == 'relance_1':
            subject = "Vous avez aimé notre audit ?"
            body = f"<p>Bonjour,</p><p>Nous vous avions envoyé notre audit...</p>"
        elif email_type == 'relance_2':
            subject = "L'opportunité vous intéresse ?"
            body = f"<p>Bonjour,</p><p>Je remarque que vous avez consulté l'audit...</p>"
        else:
            subject = "Offre spéciale pour vous"
            body = f"<p>Vous êtes un prospect vraiment qualifié!</p>"
        
        # Envoyer
        success, msg_id = sender.send_with_retry(
            email_record_id=seq['email_record_id'],
            email=email,
            subject=subject,
            html_body=body
        )
        
        if success:
            print(f"✅ Séquence {seq['id']} envoyée (lead {lead_id})")
            seq_service.mark_sequence_sent(seq['id'], seq['email_record_id'])
        else:
            print(f"❌ Séquence {seq['id']} échouée: {msg_id}")
        
        # Recalculer le score
        score, new_temp = scoring_service.update_lead_score(lead_id)
        print(f"   Score mis à jour: {score} ({new_temp})")

if __name__ == '__main__':
    run_sequence_worker()
```

### Ajouter au cron (Linux/Mac) ou Task Scheduler (Windows)

**Linux/Mac:**
```bash
# Exécuter toutes les heures
0 * * * * cd /chemin/vers/prospection-machine && python -m workers.sequence_worker
```

**Windows (Task Scheduler):**
```
Action: python.exe
Argument: -m workers.sequence_worker
Répertoire: d:\prospection-machine
Récurrence: Toutes les heures
```

---

## 📊 TESTING & VALIDATION

### Checklist de test end-to-end

- [ ] **Phase 1**: 
  - [ ] Générer un email → Enregistré dans emails_envoyes avec id
  - [ ] Approuver et publier le rapport → lien_rapport dans les DEUX tables
  - [ ] Envoyer via Resend avec retry → message_id_resend enregistré
  - [ ] Simuler erreur Resend → statut_envoi='erreur', retry exécutés

- [ ] **Phase 2**:
  - [ ] Recevoir webhook Resend 'opened' → email_events + date_ouverture
  - [ ] Recevoir webhook Resend 'clicked' → email_events + clique=1
  - [ ] Recevoir webhook Resend 'bounced' hard → statut_envoi='bounce_dur'
  - [ ] Vérifier table email_events peuplée correctement

- [ ] **Phase 3**:
  - [ ] Planifier séquences pour un lead → email_sequences créées
  - [ ] Calculer score: ouverture=10, clic=50, réponse=100
  - [ ] Classer température: chaud(≥100), tiède(≥30), froid(<30)
  - [ ] Exécuter sequence_worker → relances envoyées
  - [ ] Alerte Telegram reçue pour lead chaud
  - [ ] Endpoint /api/stats retourne tendances 7j/30j

---

## 📁 RÉSUMÉ DES FICHIERS À CRÉER/MODIFIER

### Fichiers à CRÉER
```
envoi/email_tracking_service.py
envoi/resend_sender_with_retry.py
services/lead_scoring_service.py
services/email_sequence_service.py
database/migrations.py
workers/sequence_worker.py
```

### Fichiers à MODIFIER
```
pipeline.py                  → Utiliser EmailTrackingService
dashboard/app.py             → Webhook enrichi, stats avec agrégation
database/db_manager.py       → Ajouter tables + migrations
envoi/resend_sender.py       → Remplacer par version avec retry
```

---

## 🚀 COMMANDES D'EXÉCUTION

```bash
# Phase 1: Corrections critiques
python -m database.migrations  # Ajouter colonnes

# Phase 2: Enrichir le tracking
# (Exécuté automatiquement via webhook)

# Phase 3: Automation
python -m workers.sequence_worker  # Exécuter relances planifiées

# Test webhook Resend (local)
curl -X POST http://localhost:5000/webhooks/resend \
  -H "Content-Type: application/json" \
  -d '{
    "type": "email.opened",
    "email_record_id": 1,
    "lead_id": 1,
    "user_agent": "Mozilla/5.0",
    "ip": "192.168.1.1"
  }'
```

---

**Prochaine étape:** Commencer par **PHASE 1 - TASK 1.1** - Créer la classe `EmailTrackingService.py`

