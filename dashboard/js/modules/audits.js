/**
 * dashboard/js/modules/audits.js — Gestion des Audits
 */

let _auditInterval = null;

async function auditLead(nom) {
    const btn = event.currentTarget;
    const originalText = btn.innerHTML;
    btn.innerHTML = '⏳ Audit...';
    btn.disabled = true;
    if (typeof showToast === 'function') showToast(`Audit en cours pour ${nom}...`, 'info');
    const globalProgress = document.getElementById('sidebar-audit');
    if (globalProgress) {
        globalProgress.style.display = 'block';
        const textEl = document.getElementById('sidebar-audit-text');
        if (textEl) textEl.textContent = `Démarrage pour ${nom}...`;
    }
    
    try {
        const r = await fetch('/api/audit/launch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lead_names: [nom] })
        });
        const d = await r.json();
        if (d.error) {
            if (typeof showToast === 'function') showToast('❌ Erreur: ' + d.error, 'error');
            if (globalProgress) globalProgress.style.display = 'none';
            btn.textContent = originalText;
            btn.disabled = false;
        } else {
            if (_auditInterval) clearInterval(_auditInterval);
            _auditInterval = setInterval(pollAuditStatus, 3000);
            pollAuditStatus();
            // The button reset will happen after polling finishes naturally, but we can't easily track the exact btn across multiple files/rerenders, so we'll just reset it here after starting the poll.
            btn.textContent = originalText;
            btn.disabled = false;
        }
    } catch (e) { 
        if (typeof showToast === 'function') showToast('❌ Erreur: ' + e.message, 'error'); 
        if (globalProgress) globalProgress.style.display = 'none';
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

async function auditSelected() {
    if (typeof getSelectedLeadNoms !== 'function') return;
    const noms = getSelectedLeadNoms();
    if (!noms.length) { showToast('Sélectionner au moins un lead', 'warning'); return; }
    await auditMultiple(noms);
}

function auditAllPending() {
    if (!_allLeads || !_allLeads.length) return;
    const pending = _allLeads.filter(l => l.statut === 'en_attente').map(l => l.nom);
    if (!pending.length) { showToast('Aucun lead en attente', 'info'); return; }
    auditMultiple(pending);
}

async function auditMultiple(noms) {
    if (_auditInterval) { showToast('Un audit est déjà en cours', 'warning'); return; }
    showToast(`Lancement de l'audit pour ${noms.length} lead(s)...`, 'info');
    const globalProgress = document.getElementById('sidebar-audit');
    if (globalProgress) {
        globalProgress.style.display = 'block';
        const textEl = document.getElementById('sidebar-audit-text');
        if (textEl) textEl.textContent = 'Démarrage de l\'audit...';
    }
    try {
        const r = await fetch('/api/audit/launch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lead_names: noms })
        });
        const d = await r.json();
        if (d.error) {
            showToast('Erreur: ' + d.error, 'error');
            if (globalProgress) globalProgress.style.display = 'none';
        } else {
            _auditInterval = setInterval(pollAuditStatus, 3000);
            pollAuditStatus();
        }
    } catch (e) { 
        console.error("auditSelected error:", e);
        if (globalProgress) globalProgress.style.display = 'none';
    }
}

function showAuditProgress(current, total, failed) {
    const el = document.getElementById('sidebar-audit');
    if (!el) return;
    const pct = total > 0 ? Math.round((current / total) * 100) : 0;
    el.style.display = 'block';
    
    const pctEl = document.getElementById('sidebar-audit-pct');
    if (pctEl) pctEl.textContent = pct + '%';
    
    const barEl = document.getElementById('sidebar-audit-bar');
    if (barEl) barEl.style.width = pct + '%';
    
    const textEl = document.getElementById('sidebar-audit-text');
    if (textEl) {
        textEl.innerHTML = `<strong>${current}</strong>/${total}` + (failed ? ` &middot; <span style="color:var(--red)">${failed} ❌</span>` : '');
    }
}

function hideAuditProgress() {
    const el = document.getElementById('sidebar-audit');
    if (el) {
        el.style.display = 'none';
    }
}

async function pollAuditStatus() {
    try {
        const r = await fetch('/api/audit/status');
        const d = await r.json();
        if (!d.running) {
            if (_auditInterval) clearInterval(_auditInterval);
            _auditInterval = null;
            hideAuditProgress();
            if (d.current > 0 && typeof showToast === 'function') {
                showToast(`✅ Audit terminé : ${d.current - d.failed}/${d.total} leads audités`, 'success');
            }
            if (typeof refreshAll === 'function') refreshAll();
        } else {
            showAuditProgress(d.current, d.total, d.failed);
        }
    } catch (e) { 
        if (_auditInterval) clearInterval(_auditInterval);
        _auditInterval = null;
    }
}
