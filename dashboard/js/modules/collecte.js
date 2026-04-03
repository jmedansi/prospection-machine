/**
 * dashboard/js/modules/collecte.js — Logique de Scraping et Historique
 */

let _activeScrapingId = null;
let _scraperPollId    = null;

// ─── Lancement ────────────────────────────────────────────────────────────────

/**
 * Lance un scraping.
 * @param {object} params  { keyword, city, limit, minEmails, multiZone }
 */
async function launchScraper(params) {
    const { keyword, city, sector = '', limit = 20, minEmails = null, multiZone = false } = params || {};

    // Validation
    if (!keyword || !city) { showToast('Saisir mot-clé et ville', 'warning'); return; }
    if (limit < 1 || limit > 500) { showToast('Le nombre de leads doit être entre 1 et 500', 'warning'); return; }
    if (minEmails !== null && (minEmails < 1 || minEmails > 500)) {
        showToast("Le nombre min d'emails doit être entre 1 et 500", 'warning');
        return;
    }
    if (_scraperPollId) { showToast('Un scraping est déjà en cours', 'warning'); return; }

    const today = new Date().toISOString().split('T')[0];
    const campaignName = `${keyword.charAt(0).toUpperCase() + keyword.slice(1)} ${city} ${today}`;

    // Barre latérale
    _showScraperProgress(0, limit, 0, 'Démarrage...');

    const payload = { keyword, city, sector, limit, campaign_name: campaignName, multi_zone: multiZone };
    if (minEmails) payload.min_emails = minEmails;

    let response;
    try {
        const r = await fetch('/api/scraper/launch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        response = await r.json();
    } catch (e) {
        _hideScraperProgress();
        showToast('Erreur réseau : ' + e.message, 'error');
        return;
    }

    if (response.error) {
        _hideScraperProgress();
        showToast('Erreur : ' + response.error, 'error');
        return;
    }

    _activeScrapingId = response.campaign_id;
    _scraperPollId = setInterval(() => _pollScraperStatus(limit), 2000);
    _pollScraperStatus(limit);
}

// ─── Polling ──────────────────────────────────────────────────────────────────

async function _pollScraperStatus(expectedTotal) {
    let ds;
    try {
        const r = await fetch('/api/scraper/status');
        ds = await r.json();
    } catch (e) {
        _stopScraperPoll();
        _hideScraperProgress();
        return;
    }

    const total    = ds.total    || expectedTotal || 20;
    const scraped  = ds.current  || 0;
    const withEmail = ds.with_email || ds.emails_found || 0;
    _scraperLogAppend(ds.logs || []);

    if (ds.running) {
        _showScraperProgress(scraped, total, withEmail);
        return;
    }

    // Terminé
    _stopScraperPoll();
    _hideScraperProgress();
    _activeScrapingId = null;

    if (scraped > 0) {
        showToast(`Scraping terminé — ${scraped} leads (${withEmail} emails)`, 'success');
    }
    if (typeof refreshAll === 'function') refreshAll();
}

function _stopScraperPoll() {
    if (_scraperPollId) { clearInterval(_scraperPollId); _scraperPollId = null; }
}

// ─── UI sidebar progress ──────────────────────────────────────────────────────

function _showScraperProgress(current, total, withEmail) {
    const el = document.getElementById('sidebar-scrape');
    if (!el) return;
    el.style.display = 'block';

    const pct = total > 0 ? Math.round(current * 100 / total) : 0;
    const pctEl  = document.getElementById('sidebar-scrape-pct');
    const barEl  = document.getElementById('sidebar-scrape-bar');
    const textEl = document.getElementById('sidebar-scrape-text');

    if (pctEl)  pctEl.textContent = pct + '%';
    if (barEl)  barEl.style.width = pct + '%';
    if (textEl) textEl.innerHTML  =
        `<strong>${current}</strong>/${total} &middot; <span style="color:var(--green)">${withEmail} ✉</span>`;
}

function _hideScraperProgress() {
    const el = document.getElementById('sidebar-scrape');
    if (el) el.style.display = 'none';
}

// ─── Log ─────────────────────────────────────────────────────────────────────

function _scraperLogAppend(lines) {
    const el = document.getElementById('scraper-log');
    if (!el || !lines.length) return;
    el.textContent = lines.join('\n');
    el.scrollTop = el.scrollHeight;
}

// ─── Collectes (sidebar filtres) ─────────────────────────────────────────────

async function loadCollectes() {
    try {
        const r = await fetch('/api/collectes');
        const d = await r.json();
        if (d.error || !d.collectes) return;

        const container = document.getElementById('collectes-list');
        if (!container) return;

        if (d.collectes.length === 0) {
            container.innerHTML = '<div style="font-size:11px;color:var(--ink3);width:100%;text-align:center;padding:10px">Aucune collecte disponible.</div>';
            return;
        }

        if (typeof setText === 'function') setText('collectes-count', `${d.collectes.length} collecte(s)`);

        container.innerHTML = d.collectes.map(c => {
            const name      = c.nom || `Collecte ${c.id}`;
            const isChecked = _selectedCollecteIds.includes(c.id);
            const countText = c.nb_demande > 0 ? `${c.leads_total || 0}/${c.nb_demande}` : `${c.leads_total || 0}`;
            return `
                <label class="ci" style="padding:6px 12px;background:var(--surface2);border-radius:20px;font-size:11px;cursor:pointer;white-space:nowrap;display:flex;align-items:center;gap:6px">
                    <input type="checkbox" class="cb-collecte" value="${c.id}" ${isChecked ? 'checked' : ''} onchange="toggleCollecte(${c.id}, this)">
                    <b>${typeof escHtml === 'function' ? escHtml(name) : name}</b>
                    <span style="color:var(--ink3);font-size:10px">${countText} leads</span>
                </label>`;
        }).join('');
        updateAllCollectesCheckbox();
    } catch (e) { console.error('loadCollectes:', e); }
}

function toggleCollecte(id, cb) {
    id = parseInt(id);
    if (cb.checked) {
        if (!_selectedCollecteIds.includes(id)) _selectedCollecteIds.push(id);
    } else {
        _selectedCollecteIds = _selectedCollecteIds.filter(x => x !== id);
    }
    updateAllCollectesCheckbox();
    if (typeof loadStats === 'function') loadStats();
    if (typeof loadLeadsFiltered === 'function') loadLeadsFiltered();
}

function toggleAllCollectes(cb) {
    const checks = document.querySelectorAll('.cb-collecte');
    _selectedCollecteIds = cb.checked ? Array.from(checks).map(el => parseInt(el.value)) : [];
    checks.forEach(el => el.checked = cb.checked);
    if (typeof loadStats === 'function') loadStats();
    if (typeof loadLeadsFiltered === 'function') loadLeadsFiltered();
}

function updateAllCollectesCheckbox() {
    const checks  = document.querySelectorAll('.cb-collecte');
    const allCb   = document.getElementById('cb-all-collectes');
    const checked = Array.from(checks).filter(c => c.checked).length;
    if (allCb) allCb.checked = checks.length > 0 && checked === checks.length;
}

// ─── Campagnes ────────────────────────────────────────────────────────────────

async function loadCampaigns() {
    try {
        const dateFilter = document.getElementById('global-date-start')?.value;
        let url = '/api/campaigns';
        if (dateFilter) url += `?date_start=${dateFilter}&date_end=${dateFilter}`;

        const r = await fetch(url);
        const d = await r.json();
        if (d.error) return;

        // Sélecteur global
        const select = document.getElementById('global-campaign-select');
        if (select) {
            let html = '<option value="">Toutes les campagnes</option>';
            d.campaigns.forEach(c => {
                const name = c.nom || (c.secteur && c.ville ? `${c.secteur} ${c.ville}` : 'Campagne ' + c.id);
                html += `<option value="${c.id}" ${c.id == _activeCampaignId ? 'selected' : ''}>${typeof escHtml === 'function' ? escHtml(name) : name}</option>`;
            });
            select.innerHTML = html;
        }

        if (typeof setInner === 'function') setInner('nav-badge-campagnes', d.total || '0');

        // Tableau campagnes
        const tbody = document.getElementById('tbody-campaign-list');
        if (tbody) {
            const rows = d.campaigns.map(c => {
                const date    = c.date_creation ? c.date_creation.split(' ')[0] : '—';
                const name    = c.nom || (c.secteur && c.ville ? `${c.secteur} ${c.ville}` : 'Campagne');
                const safeName = typeof escHtml === 'function' ? escHtml(name) : name;
                return `
                <tr style="${c.id == _activeCampaignId ? 'background:rgba(var(--brand-rgb),0.05)' : ''}">
                    <td><strong>${safeName}</strong></td>
                    <td>${date}</td>
                    <td><span class="b bb">${c.leads_total || 0}</span></td>
                    <td><span class="b" style="color:var(--orange)">${c.nb_audites || 0}</span></td>
                    <td><span class="b bg">${c.emails_envoyes || 0}</span></td>
                    <td><span class="b bb">${c.nb_ouverts || 0}</span></td>
                    <td><span class="b bg">${c.nb_cliques || 0}</span></td>
                    <td><span class="b ok">${c.nb_reponses || 0}</span></td>
                    <td style="text-align:right;white-space:nowrap">
                        <button class="btn ${c.id == _activeCampaignId ? 'bg2' : 'bg1'} sm"
                            onclick="changeGlobalCampaign(${c.id}); nav('cockpit', document.getElementById('nav-cockpit'))">
                            ${c.id == _activeCampaignId ? 'Active' : 'Sélectionner'}
                        </button>
                        <button class="btn bg-error sm" style="margin-left:5px"
                            onclick="deleteCampaign(${c.id}, '${safeName}')">🗑️</button>
                    </td>
                </tr>`;
            }).join('');
            tbody.innerHTML = rows || '<tr><td colspan="9" style="text-align:center;padding:1rem">Aucune campagne trouvée</td></tr>';
        }
    } catch (e) { console.error('loadCampaigns:', e); }
}

async function loadSectors() {
    try {
        const r = await fetch('/api/campaigns');
        const d = await r.json();
        if (d.error) return;

        const sectors = [...new Set(d.campaigns.map(c => c.secteur || '').filter(s => s))];
        const select  = document.getElementById('global-sector-select');
        if (!select) return;

        let html = '<option value="">Tous secteurs</option>';
        sectors.forEach(s => { html += `<option value="${escHtml(s)}">${escHtml(s)}</option>`; });
        select.innerHTML = html;
    } catch (e) { console.error('loadSectors:', e); }
}

async function loadCampaignsForSector(sector) {
    if (!sector) { loadCampaigns(); return; }
    try {
        const r = await fetch('/api/campaigns');
        const d = await r.json();
        if (d.error) return;

        const filtered = d.campaigns.filter(c => c.secteur === sector);
        const select   = document.getElementById('global-campaign-select');
        if (!select) return;

        let html = '<option value="">Toutes les campagnes</option>';
        filtered.forEach(c => {
            const name = c.nom || (c.secteur && c.ville ? `${c.secteur} ${c.ville}` : 'Campagne ' + c.id);
            html += `<option value="${c.id}">${escHtml(name)}</option>`;
        });
        select.innerHTML = html;
    } catch (e) { console.error('loadCampaignsForSector:', e); }
}

async function deleteCampaign(id, name) {
    if (!await showConfirm(`Supprimer la campagne "${name}" ? Les leads ne seront pas supprimés mais ne seront plus associés à cette campagne.`,
        { title: 'Supprimer la campagne', confirmText: 'Supprimer', danger: true })) return;
    try {
        const r = await fetch(`/api/campaigns/${id}`, { method: 'DELETE' });
        if (r.ok) {
            if (typeof showToast === 'function') showToast('Campagne supprimée');
            if (_activeCampaignId == id) _activeCampaignId = null;
            loadCampaigns();
        } else {
            if (typeof showToast === 'function') showToast('Erreur lors de la suppression', 'error');
        }
    } catch (e) {
        if (typeof showToast === 'function') showToast('Erreur réseau', 'error');
    }
}
