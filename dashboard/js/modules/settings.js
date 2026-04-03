/**
 * dashboard/js/modules/settings.js — Configuration et Paramètres
 */

async function loadSettings() {
    try {
        const r = await fetch('/api/config?_t=' + Date.now());
        const d = await r.json();
        if (d.error) return;
        
        // Mise à jour du statut du provider (dans l'onglet Paramètres)
        const providerName = d.provider_name || 'Aucun';
        const isConfigured = d.resend_configured || d.brevo_configured;
        
        const statusEl = document.getElementById('provider-status-text');
        const subtitleEl = document.getElementById('provider-subtitle');
        const alertEl = document.getElementById('alert-provider');
        
        if (statusEl) {
            if (isConfigured) {
                statusEl.innerHTML = `<strong>${providerName} opérationnel</strong> — Prêt pour l'envoi des audits approuvés.`;
            } else {
                statusEl.innerHTML = `<strong>Aucun provider email configuré</strong> — Veuillez configurer Resend ou Brevo.`;
            }
        }
        
        if (alertEl) {
            alertEl.className = isConfigured ? 'alert ao' : 'alert aw';
            alertEl.style.display = 'flex';
        }
        
        if (subtitleEl) {
            subtitleEl.textContent = isConfigured ? `${providerName} opérationnel` : 'Non configuré';
        }
        
        const fields = {
            'set-hunter-key': d.hunter_key,
            'set-groq-key': d.groq_key,
            'set-brevo-key': d.brevo_key,
            'set-sheet-id': d.sheet_id
        };

        console.log("  [Settings] Populating fields:", fields);
        for (const [id, val] of Object.entries(fields)) {
            const el = document.getElementById(id);
            if (el) {
                el.value = val || '';
            } else {
                console.warn(`  [Settings] Element #${id} not found in DOM`);
            }
        }
    } catch (e) { console.error('loadSettings:', e); }
}

async function saveSettings() {
    const data = {
        hunter_key: document.getElementById('set-hunter-key')?.value,
        groq_key: document.getElementById('set-groq-key')?.value,
        brevo_key: document.getElementById('set-brevo-key')?.value
    };
    try {
        const r = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const d = await r.json();
        if (d.success) showToast('Paramètres sauvegardés', 'success');
        else showToast('Erreur lors de la sauvegarde', 'error');
    } catch (e) { showToast('Erreur réseau', 'error'); }
}

async function saveIdentity() {
    const btn = document.getElementById('btn-save-identity');
    const name = document.getElementById('setting-name')?.value;
    const email = document.getElementById('setting-email')?.value;
    const signature = document.getElementById('setting-sig')?.value;

    if (btn) { btn.textContent = 'Enregistrement...'; btn.disabled = true; }
    try {
        const r = await fetch('/api/settings/identity', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email, signature })
        });
        const d = await r.json();
        if (d.success) {
            if (typeof showToast === 'function') showToast('✅ ' + d.message);
        } else {
            if (typeof showToast === 'function') showToast('❌ ' + (d.error || 'Erreur'), 'error');
        }
    } catch (e) { 
        if (typeof showToast === 'function') showToast('❌ Erreur réseau', 'error'); 
    }
    finally { if (btn) { btn.textContent = 'Sauvegarder'; btn.disabled = false; } }
}

async function testConnections() {
    showToast('Vérification des APIs — fonctionnalité à venir', 'info');
}
