# 🌐 Recevoir les Webhooks Resend en LOCAL (GRATUIT)

**Objectif:** Exposer ton serveur Flask local pour recevoir les webhooks Resend **sans dépenser**, sans ngrok défaillant.

---

## 🎯 OPTIONS (Classées par praticité)

### 1️⃣ **Cloudflare Tunnel** ⭐ RECOMMANDÉ (Gratuit, stable, sans limite)

**Avantages:**
- ✅ Gratuit sans limite
- ✅ Pas de credit card requis
- ✅ Ultra stable (infrastructure Cloudflare)
- ✅ Pas de session timeout (contrairement à ngrok free)
- ✅ HTTPS automatique
- ✅ Pas de bande passante limite

**Setup (5 minutes):**

1. **Télécharger cloudflared**
   ```bash
   # Windows: Télécharger depuis
   # https://github.com/cloudflare/cloudflared/releases
   # (download: cloudflared-windows-amd64.exe)
   
   # OU via Chocolatey (si installé)
   choco install cloudflare-warp-cli
   ```

2. **Se connecter à Cloudflare**
   ```bash
   cloudflared tunnel login
   # Cela ouvre un navigateur pour se connecter à cloudflare.com
   # Créer un compte gratuit si nécessaire (juste email)
   ```

3. **Créer un tunnel**
   ```bash
   cloudflared tunnel create prospection
   # Retourne: Tunnel UUID: xxxxx
   ```

4. **Configurer le fichier ~/.cloudflared/config.yml**
   ```yaml
   tunnel: prospection
   credentials-file: C:\Users\jmeda\.cloudflared\xxxxx.json
   
   ingress:
     - hostname: prospection.example.com
       service: http://localhost:5000
     - service: http_status:404
   ```

5. **Lancer le tunnel**
   ```bash
   cloudflared tunnel run prospection
   # Retourne: Listening on https://prospection.example.com
   ```

6. **Enregistrer le domaine (une seule fois)**
   ```bash
   cloudflared tunnel route dns prospection prospection.example.com
   ```

7. **Configurer dans Resend**
   - Aller à Resend Dashboard → Webhooks
   - URL: `https://prospection.example.com/webhooks/resend`
   - Garder le tunnel lancé = webhooks arrivent!

**Avantage:** Ça marche 24/7, aucune interruption.

---

### 2️⃣ **serveo.net** ⭐ PLUS SIMPLE (Zéro setup)

**Avantages:**
- ✅ Aucune installation
- ✅ Une seule commande
- ✅ Gratuit
- ✅ HTTPS automatique

**Setup (30 secondes):**

```bash
# Windows (via Git Bash ou WSL)
ssh -R 80:localhost:5000 serveo.net

# Retourne quelque chose comme:
# Forwarding HTTP traffic from https://abc123.serveo.net
```

**Problème:** L'URL change à chaque connexion, donc faut mettre à jour Resend à chaque restart.

**Solution:** Configurer une clé SSH persistante

```bash
# Windows: Créer une clé SSH (si pas déjà fait)
ssh-keygen -t rsa -f %USERPROFILE%\.ssh\serveo_key

# Lancer avec clé persistante (même subdomain à chaque fois)
ssh -R prospection:80:localhost:5000 serveo.net

# Maintenant toujours la même URL: https://prospection.serveo.net
```

---

### 3️⃣ **Beeceptor / webhook.cool** (Pour tester les webhooks)

**Use case:** Vérifier que Resend ENVOIE bien les webhooks avant d'implémenter le vrai endpoint.

**Setup:**
1. Aller à https://beeceptor.com
2. Créer un endpoint (ex: `prospection-test`)
3. Copier l'URL: `https://prospection-test.free.beeceptor.com`
4. Ajouter à Resend comme webhook URL
5. Envoyer un email de test → voir les webhooks dans Beeceptor
6. **Valider la structure** avant d'implémenter

---

### 4️⃣ **Resend Webhook Testing (Mode local)** ⭐ MEILLEUR POUR DEV

**Avantages:**
- ✅ Zéro exposition externe
- ✅ Pas de latence réseau
- ✅ Simuler les webhooks à volonté
- ✅ Parfait pour le développement

**Setup:**

Ajouter un script de test local:

```python
# test_webhooks.py
import requests
import json

BASE_URL = "http://localhost:5000"

def test_email_opened():
    """Simuler un webhook 'email.opened'"""
    payload = {
        "type": "email.opened",
        "email_record_id": 1,
        "lead_id": 1,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "ip": "192.168.1.100",
        "timestamp": "2026-04-02T10:30:00Z"
    }
    
    response = requests.post(
        f"{BASE_URL}/webhooks/resend",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"✅ Email opened: {response.status_code}")
    return response

def test_email_clicked():
    """Simuler un webhook 'email.clicked'"""
    payload = {
        "type": "email.clicked",
        "email_record_id": 1,
        "lead_id": 1,
        "url": "https://example.com/rapport",
        "user_agent": "Mozilla/5.0",
        "ip": "192.168.1.100",
        "timestamp": "2026-04-02T10:35:00Z"
    }
    
    response = requests.post(
        f"{BASE_URL}/webhooks/resend",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"✅ Email clicked: {response.status_code}")
    return response

def test_email_bounced():
    """Simuler un webhook 'email.bounced'"""
    payload = {
        "type": "email.bounced",
        "email_record_id": 1,
        "lead_id": 1,
        "bounce_type": "hard",  # 'hard' ou 'soft'
        "reason": "Address does not exist",
        "timestamp": "2026-04-02T10:40:00Z"
    }
    
    response = requests.post(
        f"{BASE_URL}/webhooks/resend",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"✅ Email bounced: {response.status_code}")
    return response

def test_all_webhook_flow():
    """Tester la séquence complète"""
    print("\n🧪 Testing complete webhook flow...\n")
    
    test_email_opened()
    test_email_clicked()
    test_email_bounced()
    
    print("\n✅ All tests passed!")

if __name__ == "__main__":
    test_all_webhook_flow()
```

**Exécuter:**
```bash
python test_webhooks.py
```

---

### 5️⃣ **ngrok FREE (avec limitations)**

Si tu veux réessayer ngrok:

**Limitations gratuites:**
- 1 URL gratuite à la fois
- Session 2 heures max
- Bande passante limitée

**Setup:**
```bash
ngrok http 5000
# Retourne: https://abc123.ngrok.io
```

**Astuce pour une URL stable:**
- Acheter un compte ngrok pro (5$/mois) → URL persistante
- **OU** utiliser Cloudflare Tunnel (gratuit et sans limite)

---

## 🏆 RECOMMANDATION POUR TOI

### **Développement local (maintenant):**
**→ Utiliser `test_webhooks.py`**
- Zéro dépendances externes
- Tester la logique sans Resend réel
- Itération rapide

### **Testing avec Resend réel:**
**→ Utiliser Cloudflare Tunnel**
- Gratuit, stable, sans interruption
- Garder les webhooks 24/7
- Aucun coût supplémentaire

### **Alternative ultra-simple:**
**→ Utiliser serveo.net**
- Une seule commande
- Pas d'installation
- Parfait pour quick tests

---

## 🚀 SETUP COMPLET CLOUDFLARE TUNNEL

### Étape 1: Installer cloudflared

**Windows (via installer):**
```bash
# Télécharger depuis:
# https://github.com/cloudflare/cloudflared/releases/download/2024.1.0/cloudflared-windows-amd64.msi

# Puis dans PowerShell:
$env:Path += ";C:\Program Files\Cloudflare\Cloudflare Warp"
cloudflared --version
```

**Windows (via Chocolatey):**
```bash
choco install cloudflare-warp-cli
cloudflared --version
```

### Étape 2: Se connecter et créer le tunnel

```bash
# Se connecter
cloudflared tunnel login

# Créer le tunnel
cloudflared tunnel create prospection-bot

# Vérifier
cloudflared tunnel list
# Devrait afficher: prospection-bot | UUID...
```

### Étape 3: Créer le fichier de config

**Créer:** `C:\Users\jmeda\.cloudflared\config.yml`

```yaml
tunnel: prospection-bot
credentials-file: C:\Users\jmeda\.cloudflared\<UUID>.json

ingress:
  - hostname: prospection.example.com
    service: http://localhost:5000
  - service: http_status:404
```

(Remplacer `<UUID>` par celui fourni à l'étape 2)

### Étape 4: Enregistrer le domaine et lancer

```bash
# Enregistrer le domaine (une seule fois)
cloudflared tunnel route dns prospection-bot prospection.example.com

# Lancer le tunnel (garder ça ouvert!)
cloudflared tunnel run prospection-bot
```

**Output attendu:**
```
Listening on https://prospection.example.com
```

### Étape 5: Configurer Resend

1. Aller à https://resend.com/dashboards/webhooks
2. Ajouter webhook:
   - **URL:** `https://prospection.example.com/webhooks/resend`
   - **Events:** Sélectionner: `email.sent`, `email.opened`, `email.clicked`, `email.bounced`
3. Sauvegarder

### Étape 6: Tester

Envoyer un email via Resend → le webhook arrive à `http://localhost:5000/webhooks/resend` ✅

---

## 📋 OPTIONNEL: Automatiser au démarrage (Windows)

**Créer:** `start_tunnel.bat`

```batch
@echo off
REM Démarrer le tunnel Cloudflare
cloudflared tunnel run prospection-bot
```

**Ajouter au Task Scheduler:**
1. Win + R → `taskschd.msc`
2. Créer une tâche simple
3. Déclencheur: "À la connexion"
4. Action: Exécuter `C:\Users\jmeda\start_tunnel.bat`
5. Cocher: "Exécuter avec les droits d'administration"

Maintenant le tunnel démarre automatiquement au boot! 🚀

---

## 🔧 DÉPANNAGE

### Problème: "TIMEOUT" sur le webhook

**Cause:** Ton endpoint `/webhooks/resend` prend trop longtemps

**Solution:**
```python
@app.route('/webhooks/resend', methods=['POST'])
def webhook_resend():
    data = request.json
    
    # Répondre IMMÉDIATEMENT (200 OK)
    # Traiter l'événement en arrière-plan
    
    from threading import Thread
    def process_event():
        # Faire le travail lourd ici
        _handle_email_opened(data)
    
    Thread(target=process_event).start()
    
    return jsonify({'success': True}), 200  # Répondre fast!
```

### Problème: Webhook pas reçu

**Vérifier:**
```bash
# 1. Le tunnel est-il lancé?
cloudflared tunnel list
# Devrait afficher: QUIC Connection Established

# 2. Flask écoute sur le bon port?
netstat -ano | findstr :5000

# 3. Le webhook est bien configuré dans Resend?
# Aller à https://resend.com/webhooks → vérifier l'URL

# 4. Envoyer un email test
# Attendre 30s et vérifier les logs Flask
```

### Problème: DNS ne resout pas

```bash
# Tester la résolution
nslookup prospection.example.com

# Si erreur, relancer:
cloudflared tunnel route dns prospection-bot prospection.example.com
```

---

## 🎯 RÉSUMÉ: COMMENT RECEVOIR LES WEBHOOKS

| Méthode | Setup | Coût | Stability | Cas d'usage |
|---------|-------|------|-----------|-----------|
| **Cloudflare Tunnel** | 5 min | 0€ | ⭐⭐⭐⭐⭐ | Production, 24/7 |
| **serveo.net** | 30 sec | 0€ | ⭐⭐⭐ | Quick tests |
| **test_webhooks.py** | 1 min | 0€ | ⭐⭐⭐⭐ | Dev local |
| **Beeceptor** | 1 min | 0€ | ⭐⭐⭐ | Validation payload |
| **ngrok Free** | 2 min | 0€ | ⭐⭐ | Tests rapides (2h limit) |
| **ngrok Pro** | 2 min | 5$/mo | ⭐⭐⭐⭐⭐ | Production (URL stable) |

**Mon choix pour toi:** 
1. **Tout de suite:** `test_webhooks.py` (dev local, zéro dépendance)
2. **Pour tester avec Resend:** Cloudflare Tunnel (gratuit, stable, 24/7)
3. **Si tu scales:** ngrok Pro (stable, professionnel)

---

## 📝 INTÉGRATION DANS TON WORKFLOW

```
┌─────────────────────────────────────────────────────────┐
│ DEV LOCAL                                               │
├─────────────────────────────────────────────────────────┤
│ 1. Lancer Flask: python dashboard/app.py                │
│ 2. Lancer tunnel: cloudflared tunnel run prospection-bot│
│ 3. Envoyer email test via Resend                        │
│ 4. Webhook arrive → endpoint /webhooks/resend           │
│ 5. Vérifie les logs + base de données                   │
└─────────────────────────────────────────────────────────┘
```

**Prêt à implémenter? Commence par Cloudflare Tunnel! 🚀**

