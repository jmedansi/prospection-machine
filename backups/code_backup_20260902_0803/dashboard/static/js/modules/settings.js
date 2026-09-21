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

// ── Santé Système ────────────────────────────────────────────────────
const _healthColors = { ok: '#10b981', warn: '#f59e0b', fail: '#ef4444' };
const _overallColors = { ok: '#10b981', degraded: '#f59e0b', critical: '#ef4444' };
const _overallLabels = { ok: 'Système opérationnel', degraded: 'Dégradé', critical: 'Critique' };

function runHealthCheck() {
    const btn = document.getElementById('health-run-btn');
    const container = document.getElementById('health-checks-container');
    if (btn) { btn.disabled = true; btn.textContent = 'Vérification…'; }
    if (container) container.innerHTML = '<div style="text-align:center;padding:3rem;color:var(--ink3);font-size:14px">Vérification en cours…</div>';

    fetch('/api/health')
        .then(r => r.json())
        .then(data => _renderHealthResult(data))
        .catch(e => {
            if (container) container.innerHTML = `<div style="padding:2rem;color:#ef4444;font-size:14px">Impossible de joindre /api/health : ${e.message}</div>`;
        })
        .finally(() => {
            if (btn) { btn.disabled = false; btn.textContent = 'Tester maintenant'; }
        });
}

async function restartBrowser() {
    if (!await showConfirm('Voulez-vous vraiment redémarrer le navigateur ? Cela fermera tous les onglets en cours.', { title: 'Redémarrage Chrome', danger: true })) return;
    
    showToast('Redémarrage du navigateur en cours...', 'info');
    try {
        const r = await fetch('/api/health/restart-browser', { method: 'POST' });
        const d = await r.json();
        if (d.status === 'ok') {
            showToast('Navigateur redémarré avec succès');
            runHealthCheck();
        } else {
            showToast(d.message || 'Erreur lors du redémarrage', 'error');
        }
    } catch (e) {
        showToast('Erreur réseau lors du redémarrage', 'error');
    }
}

function _renderHealthResult(data) {
    const dot    = document.getElementById('health-overall-dot');
    const text   = document.getElementById('health-overall-text');
    const line   = document.getElementById('health-score-line');
    const navDot = document.getElementById('health-dot');

    const color = _overallColors[data.status] || '#6b7280';
    if (dot)  dot.style.background = color;
    if (text) text.textContent = _overallLabels[data.status] || data.status;
    if (line && data.score) {
        line.textContent = `${data.score.ok} OK · ${data.score.warn} avertissements · ${data.score.fail} échecs sur ${data.score.total} vérifications`;
    }
    if (navDot) navDot.style.background = color;

    const categories = {};
    (data.checks || []).forEach(c => {
        if (!categories[c.category]) categories[c.category] = [];
        categories[c.category].push(c);
    });

    const catLabels = { database: 'Base de données', agents: 'Agents', env: "Variables d'env", filesystem: 'Fichiers', browser: 'Navigateur' };
    const catOrder  = ['browser', 'database', 'filesystem', 'agents', 'env'];
    let html = '';
    catOrder.forEach(cat => {
        if (!categories[cat]) return;
        html += `<div class="card" style="margin-bottom:1rem;padding:0;overflow:hidden">
            <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid var(--border);background:var(--surface2)">
                <div style="font-size:12px;font-weight:700;color:var(--ink3);text-transform:uppercase;letter-spacing:.5px;">${catLabels[cat] || cat}</div>
                ${cat === 'browser' ? '<button class="btn br sm" style="padding:2px 8px;font-size:10px" onclick="restartBrowser()">Redémarrer Chrome</button>' : ''}
            </div>
            <table style="width:100%;border-collapse:collapse">`;
        categories[cat].forEach((c, i) => {
            const col    = _healthColors[c.status] || '#6b7280';
            const bg     = c.status === 'fail' ? 'rgba(239,68,68,.04)' : c.status === 'warn' ? 'rgba(245,158,11,.04)' : '';
            const border = i < categories[cat].length - 1 ? 'border-bottom:1px solid var(--surface2)' : '';
            html += `<tr style="background:${bg};${border}">
                <td style="padding:10px 16px;width:200px">
                    <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${col};margin-right:8px"></span>
                    <span style="font-size:13px;font-weight:600">${c.name}</span>
                </td>
                <td style="padding:10px 8px;font-size:12px;color:var(--ink3)">${c.message}</td>
                <td style="padding:10px 16px;text-align:right;font-size:11px;color:var(--ink3);white-space:nowrap">${c.duration_ms}ms</td>
            </tr>`;
        });
        html += '</table></div>';
    });
    const container = document.getElementById('health-checks-container');
    if (container) container.innerHTML = html || '<div style="padding:2rem;color:var(--ink3)">Aucun check retourné.</div>';
}

// ── Logs Système ─────────────────────────────────────────────────────
async function loadLogs() {
    const viewer = document.getElementById('log-viewer');
    const stats = document.getElementById('log-stats');
    if (!viewer) return;
    
    try {
        viewer.value = 'Chargement des logs...';
        const r = await fetch('/api/logs?_t=' + Date.now());
        const d = await r.json();
        
        if (d.logs) {
            viewer.value = d.logs;
            // Scroll to bottom
            viewer.scrollTop = viewer.scrollHeight;
            
            if (stats && d.file_size !== undefined) {
                const sizeMb = (d.file_size / (1024 * 1024)).toFixed(2);
                stats.textContent = `${sizeMb} MB · ${d.total_lines} lignes`;
            }
        } else {
            viewer.value = 'Aucun log disponible.';
        }
    } catch (e) {
        viewer.value = 'Erreur lors du chargement des logs : ' + e.message;
    }
}

