/**
 * dashboard/static/js/modules/actions.js
 * Handles Toolbar actions (Scrape, Audit, etc.)
 */

// Helpers to get API & UI (handles late loading of core modules)
const getAPI = () => window.API_V5 || window.API;
const getUI = () => {
    // 1. Prioritize V5 UI Module
    if (window.UI && typeof window.UI.confirm === 'function') return window.UI;
    
    // 2. Fallback to Legacy custom UI functions
    return {
        toast: (m, t) => typeof window.showToast === 'function' ? window.showToast(m, t) : console.log('Toast:', m),
        confirm: (m, o) => typeof window.showConfirm === 'function' ? window.showConfirm(m, o) : Promise.resolve(confirm(m))
    };
};

class ActionsModule {
    static init() {
        console.log('[ActionsModule] Initialized');
        
        // Expose all functions to window.ActionsModule for HTML onclick handlers
        window.ActionsModule = this;
        
        // Also keep global aliases for legacy support
        window.launchSelectedAudits = () => this.launchAuditForSelected();
        window.launchSelectedEmailSearch = () => this.launchSelectedEmailSearch();
        window.findEmailsForSelected = () => this.launchSelectedEmailSearch();
        window.findEmailsForSelectedLeads = () => this.launchSelectedEmailSearch();
        window.refreshCampaignData = () => this.refreshAll();
        window.openScraperModal = () => getUI().toast('Scraper non migré (Placeholder)', 'info');
        window.generateSelectedEmails = () => this.generateSelectedEmailsImpl();
        window.sendApprovedEmails = () => this.sendApprovedEmailsImpl();
        window.deleteSelectedLeads = () => getUI().toast('Suppression non migrée (Placeholder)', 'info');
        window.purgeZeroAvis = () => getUI().toast('Purge non migrée (Placeholder)', 'info');
        window.exportFilteredLeads = () => this.exportFilteredLeadsImpl();
        window.retryFailedAudits = () => this.retryFailedAuditsImpl();
        window.checkSniperResponses = () => this.checkSniperResponsesImpl();
        window.sendSniperStep1 = () => this.sendSniperStep1Impl();
        window.sniperSendStep2 = (auditId) => this.sendSniperStep2Impl(auditId);
        
        console.log('[ActionsModule] Functions exposed on window.ActionsModule and window');
    }

    static async retryFailedAuditsImpl() {
        const UI = getUI();
        if (!await UI.confirm('Relancer l\'audit sur tous les leads en échec ?')) return;
        try {
            UI.toast('Relance des audits échoués...', 'info');
            const r = await fetch('/api/audit/retry-failed', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
            const d = await r.json();
            if (d.success) {
                UI.toast(`${d.count || 0} lead(s) relancés`, 'success');
                this.refreshAll();
            } else {
                UI.toast(d.error || 'Erreur', 'error');
            }
        } catch (e) { UI.toast('Erreur réseau', 'error'); }
    }

    static async exportFilteredLeadsImpl() {
        const UI = getUI();
        UI.toast('Export en cours...', 'info');
        try {
            const resp = await fetch('/api/leads?limit=10000');
            const d = await resp.json();
            const leads = d.leads || d || [];
            const csv = ['Nom,Ville,Secteur,Note,Avis,Site,Email,Statut'];
            leads.forEach(l => csv.push(`"${l.nom}","${l.ville}","${l.secteur}",${l.note},${l.avis},"${l.site_web}","${l.email}","${l.statut}"`));
            const blob = new Blob([csv.join('\n')], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `leads_${new Date().toISOString().slice(0,10)}.csv`;
            a.click();
            UI.toast(`${leads.length} leads exportés`, 'success');
        } catch (e) { UI.toast('Erreur export', 'error'); }
    }

    static async sendApprovedEmailsImpl() {
        const UI = getUI();
        UI.toast('Envoi des emails approuvés...', 'info');
        try {
            const r = await fetch('/api/email/send-approved', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
            const d = await r.json();
            if (d.error) UI.toast('Erreur: ' + d.error, 'error');
            else UI.toast(`${d.sent || 0} emails envoyés`, 'success');
        } catch (e) { UI.toast('Erreur: ' + e.message, 'error'); }
    }

    static async generateSelectedEmailsImpl() {
        const UI = getUI();
        const selected = this.getSelectedIds();
        if (selected.length === 0) {
            UI.toast('Veuillez sélectionner au moins un lead', 'warning');
            return;
        }

        const ok = await UI.confirm(`Générer des emails pour ${selected.length} lead(s) ?`);
        if (!ok) return;

        UI.toast(`Génération d'emails pour ${selected.length} lead(s)...`, 'info');
        try {
            const r = await fetch('/api/email/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lead_ids: selected.map(Number) })
            });
            const d = await r.json();
            if (d.error) {
                console.error('[ActionsModule] generate error:', d.error);
                UI.toast('Erreur : ' + d.error, 'error');
            } else {
                UI.toast('✅ Emails générés !', 'success');
                this.refreshAll();
            }
        } catch (e) {
            console.error('[ActionsModule] generate fetch error:', e);
            UI.toast('Erreur réseau : ' + e.message, 'error');
        }
    }

    static async launchAuditForSelected() {
        const UI = getUI();
        const selected = this.getSelectedIds();
        if (selected.length === 0) {
            UI.toast('Veuillez sélectionner au moins un lead', 'warning');
            return;
        }

        const ok = await UI.confirm(`Lancer l'audit pour ${selected.length} lead(s) ?`);
        if (!ok) return;

        UI.toast(`Lancement de ${selected.length} audit(s)...`, 'info');
        try {
            const r = await fetch('/api/audit/launch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lead_ids: selected.map(Number) })
            });
            const d = await r.json();
            if (d.error) {
                console.error('[ActionsModule] audit error:', d.error);
                UI.toast('Erreur : ' + d.error, 'error');
            } else {
                UI.toast('✅ Audit lancé !', 'success');
                if (typeof window.startAuditPolling === 'function') {
                    window.startAuditPolling();
                }
                this.refreshAll();
            }
        } catch (e) {
            console.error('[ActionsModule] audit fetch error:', e);
            UI.toast('Erreur réseau : ' + e.message, 'error');
        }
    }

    static async launchSelectedEmailSearch() {
        const UI = getUI();
        const selected = this.getSelectedIds();
        if (selected.length === 0) {
            UI.toast('Veuillez sélectionner au moins un lead', 'warning');
            return;
        }

        const ok = await UI.confirm(`Rechercher les emails pour ${selected.length} lead(s) ?`);
        if (!ok) return;

        UI.toast(`Recherche d'emails pour ${selected.length} lead(s)...`, 'info');
        try {
            const r = await fetch('/api/leads/find-emails', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lead_ids: selected.map(Number) })
            });
            const d = await r.json();
            if (d.error) {
                console.error('[ActionsModule] find-emails error:', d.error);
                UI.toast('Erreur : ' + d.error, 'error');
            } else {
                UI.toast(`✅ ${d.message || 'Recherche lancée !'}`, 'success');
            }
        } catch (e) {
            console.error('[ActionsModule] find-emails fetch error:', e);
            UI.toast('Erreur réseau : ' + e.message, 'error');
        }
    }

    // ─── Sniper Migrated Actions ──────────────────────────────────────────────

    static async checkSniperResponsesImpl() {
        const UI = getUI();
        UI.toast('⏳ Vérification des réponses (IMAP)...', 'info');
        try {
            const r = await fetch('/api/sniper/poll-imap', { 
                method: 'POST', 
                headers: {'Content-Type':'application/json'}, 
                body: JSON.stringify({ hours: 48 }) 
            });
            const d = await r.json();
            if (d.error) { UI.toast('Erreur : ' + d.error, 'error'); return; }
            UI.toast(`IMAP : ${d.matched || 0} réponse(s) détectée(s)`, d.matched > 0 ? 'success' : 'info');
            this.refreshAll();
        } catch (e) { UI.toast('Erreur réseau', 'error'); }
    }

    static async sendSniperStep1Impl() {
        const UI = getUI();
        const ok = await UI.confirm(`Envoyer les emails de premier contact (Step 1) Sniper ?`);
        if (!ok) return;

        UI.toast('⏳ Envoi des emails Step 1...', 'info');
        try {
            const r = await fetch('/api/sniper/send-step1', { 
                method: 'POST', 
                headers: {'Content-Type':'application/json'}, 
                body: '{}' 
            });
            const d = await r.json();
            if (d.error) { UI.toast('Erreur : ' + d.error, 'error'); return; }
            if (d.message) { UI.toast(d.message, 'info'); return; }
            UI.toast(`Envoi : ${d.success || 0} succès · ${d.failed || 0} échecs`, 'success');
            this.refreshAll();
        } catch (e) { UI.toast('Erreur réseau', 'error'); }
    }

    static async sendSniperStep2Impl(auditId) {
        const UI = getUI();
        if (!auditId) { UI.toast('ID audit manquant', 'error'); return; }

        const ok = await UI.confirm(`Envoyer le rapport (Step 2) pour ce lead ?`);
        if (!ok) return;

        UI.toast('⏳ Envoi du rapport...', 'info');
        try {
            const r = await fetch('/api/sniper/send-step2', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({ audit_id: auditId }),
            });
            const d = await r.json();
            if (d.ok) {
                UI.toast('Step 2 envoyé !', 'success');
                this.refreshAll();
            } else {
                UI.toast('Erreur : ' + (d.message || d.error || 'inconnue'), 'error');
            }
        } catch (e) { UI.toast('Erreur réseau', 'error'); }
    }

    // Alias for compatibility
    static async findEmailsForSelected() {
        return this.launchSelectedEmailSearch();
    }


    static getSelectedIds() {
        // Collect IDs from both old (.lead-cb) and new (.ul-cb) table versions
        return Array.from(document.querySelectorAll('.lead-cb:checked, .ul-cb:checked'))
            .map(cb => cb.dataset.id || cb.value);
    }

    static async refreshAll() {
        const UI = getUI();
        UI.toast('Actualisation...', 'info');
        try {
            const promises = [];
            
            // 1. Refresh Unified Leads (New V5 View)
            if (typeof window.unifiedLeadsLoad === 'function') {
                promises.push(window.unifiedLeadsLoad());
            }
            
            // 2. Refresh Classic Leads Module (Legacy fallback)
            if (window.LeadsModule && typeof window.LeadsModule.refresh === 'function') {
                promises.push(window.LeadsModule.refresh());
            }
            
            // 3. Refresh Stats (Cockpit)
            if (window.StatsModule && typeof window.StatsModule.refresh === 'function') {
                promises.push(window.StatsModule.refresh());
            }
            
            await Promise.all(promises);
            UI.toast('Données actualisées', 'success');
        } catch (e) {
            console.error('[ActionsModule] Refresh error:', e);
            UI.toast('Erreur lors de l\'actualisation', 'error');
        }
    }
}

// Expose to window
window.ActionsModule = ActionsModule;

