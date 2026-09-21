/**
 * dashboard/js/modules/audits.js — Gestion des Audits
 */

let _auditInterval = null;

async function auditLead(leadId) {
    let nom = "Lead #" + leadId;
    if (typeof _allLeads !== 'undefined' && _allLeads) {
        const l = _allLeads.find(x => x.id == leadId);
        if (l && l.nom) nom = l.nom;
    } else if (typeof _campaignData !== 'undefined' && _campaignData) {
        const l = _campaignData.find(x => x.id == leadId);
        if (l && l.nom) nom = l.nom;
    } else if (typeof _ul !== 'undefined' && _ul && _ul.leads) {
        const l = _ul.leads.find(x => x.id == leadId);
        if (l && l.nom) nom = l.nom;
    }

    const btn = (typeof event !== 'undefined' && event && event.currentTarget) ? event.currentTarget : null;
    const originalText = btn ? btn.innerHTML : 'Audit';
    if (btn) {
        btn.innerHTML = '⏳ Audit...';
        btn.disabled = true;
    }
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
            body: JSON.stringify({ lead_ids: [leadId] })
        });
        const d = await r.json();
        if (d.error) {
            if (typeof showToast === 'function') showToast('❌ Erreur: ' + d.error, 'error');
            if (globalProgress) globalProgress.style.display = 'none';
            if (btn) {
                btn.textContent = originalText;
                btn.disabled = false;
            }
        } else {
            console.log("[Audit] Job lancé avec succès");
            if (btn) {
                btn.textContent = originalText;
                btn.disabled = false;
            }
        }
    } catch (e) { 
        if (typeof showToast === 'function') showToast('❌ Erreur: ' + e.message, 'error'); 
        if (globalProgress) globalProgress.style.display = 'none';
    } finally {
        if (btn) {
            btn.textContent = originalText;
            btn.disabled = false;
        }
    }
}

function getSelectedLeadNoms() {
    const checkboxes = document.querySelectorAll('.lead-cb:checked, .ul-cb:checked');
    return Array.from(checkboxes).map(cb => {
        const id = cb.dataset.id || cb.value;
        const lead = (typeof _campaignData !== 'undefined' && _campaignData && _campaignData.find(l => l.id == id))
                  || (typeof _allLeads !== 'undefined' && _allLeads && _allLeads.find(l => l.id == id))
                  || (typeof _ul !== 'undefined' && _ul && _ul.leads && _ul.leads.find(l => l.id == id));
        return lead ? lead.nom : (cb.dataset.nom || null);
    }).filter(Boolean);
}
window.getSelectedLeadNoms = getSelectedLeadNoms;

function startAuditPolling() {
    console.log("[Audit] Démarrage du tracking d'état d'audit...");
    const globalProgress = document.getElementById('sidebar-audit');
    if (globalProgress) {
        globalProgress.style.display = 'block';
        const textEl = document.getElementById('sidebar-audit-text');
        if (textEl) textEl.textContent = 'Démarrage de l\'audit...';
    }
}
window.startAuditPolling = startAuditPolling;

async function auditSelected() {
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

async function pollAuditStatus(d = null) {
    try {
        if (!d) {
            const r = await fetch('/api/audit/status');
            d = await r.json();
        }
        
        // Optimisation: ne pas re-logger à chaque websocket event s'il n'y a pas de changement
        if (!d.running) {
            hideAuditProgress();

            const total = d.total || 0;
            const current = d.current || 0;
            const success = Math.max(0, (d.current || d.total || 0) - (d.failed || 0));
            const failed = d.failed || 0;

            // Mettre à jour la modal
            const sEl = document.getElementById('audit-stat-success');
            const fEl = document.getElementById('audit-stat-failed');
            if (sEl) sEl.textContent = success;
            if (fEl) fEl.textContent = failed;
            
            const titleEl = document.getElementById('audit-results-title');
            const iconEl = document.getElementById('audit-results-icon');
            if (titleEl) titleEl.textContent = failed > 0 ? "Audit terminé avec des erreurs" : "Audit terminé avec succès";
            if (iconEl) iconEl.textContent = failed > 0 ? "⚠️" : "✅";
            
            // Rafraîchissement systématique quand un audit se termine
            if (typeof refreshAll === 'function') refreshAll();
            if (typeof unifiedLeadsLoad === 'function') unifiedLeadsLoad();
            
            // Mettre à jour le panneau latéral s'il est ouvert pour afficher les nouveaux scores immédiatement
            // Utilise window._selectedLeadId et window.loadPanelContent exposés par dashboard_core.js
            const panelLeadId = window._selectedLeadId;
            if (panelLeadId && typeof window.loadPanelContent === 'function') {
                const activeTab = document.querySelector('.side-panel-tab.active');
                window.loadPanelContent(panelLeadId, activeTab ? activeTab.dataset.tab : 'audit');
            }
        } else {
            showAuditProgress(d.current, d.total, d.failed);
        }
    } catch (e) { 
        console.error('[Audit] Erreur traitement statut:', e);
    }
}

// Socket.IO Listener pour les mises à jour en temps réel (Remplace le polling)
if (typeof socket !== 'undefined') {
    socket.on('audit_status', function(data) {
        pollAuditStatus(data);
    });
    
    // Au chargement, on vérifie l'état actuel une fois
    window.addEventListener('load', () => {
        pollAuditStatus();
    });
}

