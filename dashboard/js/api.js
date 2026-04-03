/**
 * dashboard/js/api.js — Communications avec le backend et filtres globaux
 */

// --- Gestion des Filtres Globaux ---

function _globalFilters(extra = {}) {
    const p = new URLSearchParams();
    if (_activeCampaignId) p.set('campaign_id', _activeCampaignId);
    
    // Si on a des collectes spécifiques cochées, on les passe au backend
    if (typeof _selectedCollecteIds !== 'undefined' && _selectedCollecteIds.length > 0) {
        p.set('campaign_ids', _selectedCollecteIds.join(','));
    }

    if (_activeDateStart) p.set('date_start', _activeDateStart);
    if (_activeDateEnd) p.set('date_end', _activeDateEnd);
    for (const [k, v] of Object.entries(extra)) {
        if (v !== null && v !== undefined) p.set(k, v);
    }
    const s = p.toString();
    return s ? '?' + s : '';
}


function clearGlobalDate() {
    _activeDateStart = null;
    _activeDateEnd = null;
    if (typeof _drpReset === 'function') _drpReset();
    if (typeof showToast === 'function') showToast('Période réinitialisée');
    refreshAll();
}

async function changeGlobalCampaign(id) {
    _activeCampaignId = id ? parseInt(id) : null;
    const select = document.getElementById('global-campaign-select');
    if (select) select.value = id || '';
    if (typeof showToast === 'function') {
        showToast(_activeCampaignId ? `Filtrage par campagne active` : `Affichage de toutes les données`);
    }
    refreshAll();
}

// --- Fonctions d'API ---

async function loadStats() {
    try {
        const filters = typeof _globalFilters === 'function' ? _globalFilters() : '';
        const r = await fetch('/api/stats' + filters);
        if (!r.ok) throw new Error('Stats API error');
        const d = await r.json();
        if (d.error) return;

        // Stats principales
        setText('stat-scrapes', d.pipeline.leads_scrapes);
        setText('stat-audites', d.pipeline.leads_audites);
        setText('stat-prets', d.pipeline.emails_prets);
        setText('stat-envoyes', d.pipeline.envoyes);
        setText('stat-scrapes-big', d.pipeline.leads_scrapes);

        // Stats détaillées
        setText('stat-audits-total', d.pipeline.leads_audites);
        setText('stat-pending-total', '+' + (d.leads_en_attente || 0) + ' en attente');
        
        // Sidebar stats
        setText('sidebar-stat-scrapes', d.pipeline.leads_scrapes || 0);
        setText('sidebar-stat-audits', d.pipeline.leads_audites || 0);
        setText('sidebar-stat-emails', d.pipeline.emails_prets || 0);
        setText('sidebar-stat-sent', d.pipeline.envoyes || 0);

        // Stats site
        const sitePct = d.pipeline.leads_scrapes > 0 ? Math.round((d.leads_site || 0) * 100 / d.pipeline.leads_scrapes) : 0;
        setText('stat-with-site-pct', sitePct + '%');
        setText('stat-with-site', (d.leads_site || 0) + ' avec site');
        setText('stat-with-site-2', (d.leads_site || 0));

        // Stats emails
        setText('stat-sent-total', d.pipeline.envoyes);
        setText('stat-emails-found', d.emails_trouves || 0);
        
        // Stats supplémentaires (nouvelles)
        setText('stat-sans-site', d.leads_sans_site || 0);
        setText('stat-en-attente', d.leads_en_attente || 0);
        
        // Stats batches
        setText('stat-batches-pending', d.batches?.pending || 0);
        setText('stat-batches-queued', d.batches?.queued || 0);
        setText('stat-emails-pending', d.batches?.emails_pending || 0);

        // Gauge performance cockpit
        const gauge = document.querySelector('#pg-cockpit svg circle:nth-child(2)');
        const gaugeVal = document.querySelector('#pg-cockpit .card div[style*="font-size:18px"]');
        if (gauge && gaugeVal) {
            const score = Math.round(d.performance.score_moyen * 10);
            const dash = Math.round((201 * score) / 100);
            gauge.style.strokeDasharray = `${dash} 201`;
            gauge.style.stroke = score >= 70 ? 'var(--green)' : score >= 40 ? 'var(--orange)' : 'var(--red)';
            gaugeVal.textContent = score + '%';
            const gaugeTitle = gaugeVal.parentElement.nextElementSibling.querySelector('div:first-child');
            if (gaugeTitle) gaugeTitle.textContent = score >= 70 ? 'Excellente' : score >= 40 ? 'Améliorable' : 'Critique';
        }

        setText('nav-badge-scrapes', d.pipeline.leads_scrapes);
        setText('nav-badge-audits', d.pipeline.leads_scrapes - d.pipeline.leads_audites);
        setText('nav-badge-emails', d.pipeline.emails_prets);

        // Quotas
        setText('quota-resend-val', `${d.quotas.resend || 0} envoyés`);
        setText('quota-groq-val', `${d.quotas.groq || 0} / 14 400`);
        setText('quota-anthropic-val', `${d.quotas.anthropic || 0} utilisés`);
        setText('quota-carbone-val', `${d.quotas.carbone || 0} rapports`);

        // CRM Stats Cockpit
        if (d.email_stats) {
            setText('crm-stat-envoyes', d.email_stats.nb_envoyes || 0);
            setText('crm-stat-ouvertures', (d.email_stats.taux_ouverture || 0) + '%');
            setText('crm-stat-clics', (d.email_stats.taux_clic || 0) + '%');
            setText('crm-stat-reponses', (d.email_stats.taux_reponse || 0) + '%');
            setText('crm-stat-positives', d.email_stats.reponses_positives || 0);
            setText('crm-stat-rdv', d.email_stats.rdv_obtenus || 0);
            setText('crm-stat-bounces', d.email_stats.bounces || 0);
            setText('crm-stat-spam', d.email_stats.spam || 0);

            // Cockpit cards
            const totalReponses = Math.round(d.pipeline.envoyes * (d.email_stats.taux_reponse || 0) / 100);
            setText('stat-reponses', totalReponses);
            setText('stat-reponses-positives', (d.email_stats.reponses_positives || 0) + ' positives');
            setText('stat-rdv', d.email_stats.rdv_obtenus || 0);
            // Pipeline
            setText('stat-pipeline-reponses', d.email_stats.reponses_positives || 0);
            setText('stat-pipeline-rdv', d.email_stats.rdv_obtenus || 0);
        }

        const resendPct = Math.min(100, Math.round((d.quotas.resend || 0) / 100 * 100));
        const groqPct = Math.min(100, Math.round((d.quotas.groq || 0) / 14400 * 100));

        const resFill = document.getElementById('quota-resend-fill');
        if (resFill) {
            resFill.style.width = resendPct + '%';
            resFill.style.background = resendPct > 80 ? 'var(--red)' : 'var(--green)';
        }
        const groqFill = document.getElementById('quota-groq-fill');
        if (groqFill) {
            groqFill.style.width = groqPct + '%';
            groqFill.style.background = groqPct > 80 ? 'var(--red)' : 'var(--green)';
        }
        const antFill = document.getElementById('quota-anthropic-fill');
        if (antFill) antFill.style.width = '0%';
        const carbFill = document.getElementById('quota-carbone-fill');
        if (carbFill) carbFill.style.width = '0%';

    } catch (e) { console.error('loadStats:', e); }
}

async function loadConfig() {
    try {
        const r = await fetch('/api/config');
        const d = await r.json();
        if (d.error) return;

        // Topbar Provider
        const provEl = document.getElementById('status-provider');
        const provTxt = document.getElementById('status-provider-text');
        if (provEl && provTxt) {
            const ok = d.resend_configured || d.brevo_configured;
            provEl.removeAttribute('style');
            provEl.className = ok ? 'sp ok' : 'sp';
            provTxt.textContent = ok ? `${d.provider_name} prêt` : 'Email non configuré';
        }

        // Topbar Groq
        const groqEl = document.getElementById('status-groq');
        const groqTxt = document.getElementById('status-groq-text');
        if (groqEl && groqTxt) {
            groqEl.removeAttribute('style');
            groqEl.className = d.groq_configured ? 'sp ok' : 'sp';
            groqTxt.textContent = d.groq_configured ? 'Groq actif' : 'Groq non configuré';
        }

        // Cockpit Alert
        const provStatusText = document.getElementById('provider-status-text');
        const alertProv = document.getElementById('alert-provider');
        if (provStatusText && alertProv) {
            const ok = d.resend_configured || d.brevo_configured;
            provStatusText.textContent = ok
                ? `Envoi via ${d.provider_name} — Système opérationnel`
                : 'Aucun provider email configuré — Voir les paramètres';
            alertProv.className = ok ? 'alert ao' : 'alert aw';
        }
    } catch (e) { console.error('loadConfig:', e); }
}

async function refreshAll() {
    // Note: l'ordre Promise.all est plus rapide
    await Promise.all([
        typeof loadCollectes === 'function' ? loadCollectes() : Promise.resolve(),
        typeof loadCampaigns === 'function' ? loadCampaigns() : Promise.resolve(),
        typeof loadSectors === 'function' ? loadSectors() : Promise.resolve(),
        loadStats(),
        typeof loadLeads === 'function' ? loadLeads() : Promise.resolve(),
        typeof loadEmails === 'function' ? loadEmails() : Promise.resolve(),
        typeof loadTracking === 'function' ? loadTracking() : Promise.resolve(),
        typeof loadCRM === 'function' ? loadCRM() : Promise.resolve(),
        typeof loadReports === 'function' ? loadReports() : Promise.resolve(),
        typeof loadSettings === 'function' ? loadSettings() : Promise.resolve(),
        loadConfig(),
        typeof loadCampaignTable === 'function' ? loadCampaignTable() : Promise.resolve()
    ]);
}

// --- Auto-refresh : stats sidebar + panneau latéral (intervalle unique) ---
const _autoRefreshId = setInterval(async () => {
    try { await loadStats(); } catch (e) {}
    try {
        if (_selectedLeadId && typeof loadPanelContent === 'function') {
            const activeTab = document.querySelector('.side-panel-tab.active');
            loadPanelContent(_selectedLeadId, activeTab ? activeTab.dataset.tab : 'audit');
        }
    } catch (e) {}
}, 30000);

window.addEventListener('beforeunload', () => clearInterval(_autoRefreshId));
