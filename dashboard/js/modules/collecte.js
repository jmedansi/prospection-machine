/**
 * dashboard/js/modules/collecte.js — Logique de Scraping et Historique
 */

let _activeScrapingId = null;
let _campaignStatsInterval = null;

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

        const html = d.collectes.map(c => {
            const name = c.nom || `Collecte ${c.id}`;
            const isChecked = _selectedCollecteIds.includes(c.id);
            const countText = c.nb_demande > 0 ? `${c.leads_total || 0}/${c.nb_demande}` : `${c.leads_total || 0}`;
            return `
                <label class="ci" style="padding:6px 12px;background:var(--surface2);border-radius:20px;font-size:11px;cursor:pointer;white-space:nowrap;display:flex;align-items:center;gap:6px">
                    <input type="checkbox" class="cb-collecte" value="${c.id}" ${isChecked ? 'checked' : ''} onchange="toggleCollecte(${c.id}, this)">
                    <b>${typeof escHtml === 'function' ? escHtml(name) : name}</b>
                    <span style="color:var(--ink3);font-size:10px">${countText} leads</span>
                </label>
            `;
        }).join('');
        container.innerHTML = html;
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
    if (cb.checked) {
        _selectedCollecteIds = Array.from(checks).map(el => parseInt(el.value));
    } else {
        _selectedCollecteIds = [];
    }
    checks.forEach(el => el.checked = cb.checked);
    if (typeof loadStats === 'function') loadStats();
    if (typeof loadLeadsFiltered === 'function') loadLeadsFiltered();
}

function updateAllCollectesCheckbox() {
    const checks = document.querySelectorAll('.cb-collecte');
    const allCb = document.getElementById('cb-all-collectes');
    const checkedCount = Array.from(checks).filter(c => c.checked).length;
    if (allCb) allCb.checked = checks.length > 0 && checkedCount === checks.length;
}

function syncCampaignName() {
    const kw = document.getElementById('keyword')?.value.trim();
    const city = document.getElementById('city')?.value.trim();
    const cn = document.getElementById('campaign-name');
    if (cn && !cn.value.trim() && kw && city) {
        cn.value = `${kw.charAt(0).toUpperCase() + kw.slice(1)} ${city}`;
    }
}

async function launchScraper() {
    const kw = document.getElementById('keyword')?.value.trim();
    const city = document.getElementById('city')?.value.trim();
    const limitInput = document.getElementById('limit');
    const limit = parseInt(limitInput?.value) || 20;
    const minEmailsInput = document.getElementById('min-emails');
    const minEmails = minEmailsInput?.value ? parseInt(minEmailsInput.value) : null;

    if (!kw || !city) return alert('Saisir mot-clé et ville');
    if (limit < 1 || limit > 500) return alert('Le nombre de leads doit être entre 1 et 500');
    if (minEmails && (minEmails < 1 || minEmails > 500)) return alert('Le nombre min d\'emails doit être entre 1 et 500');

    const today = new Date().toISOString().split('T')[0];
    const campaignName = `${kw.charAt(0).toUpperCase() + kw.slice(1)} ${city} ${today}`;

    let logEl = document.getElementById('scraper-log');
    if (!logEl) {
        logEl = document.createElement('pre');
        logEl.id = 'scraper-log';
        logEl.style = 'background:var(--surface2);padding:10px;border-radius:8px;font-size:11px;margin-top:10px;max-height:200px;overflow:auto;display:block;white-space:pre-wrap;border:1px solid var(--border)';
        const card = document.querySelector('#pg-collecte .card');
        if (card) card.appendChild(logEl);
    }

    const targetMsg = minEmails ? ` (objectif: ${minEmails} emails min)` : '';
    logEl.textContent = `Lancement: ${campaignName}${targetMsg}\n`;
    const globalProgress = document.getElementById('sidebar-scrape');
    if (globalProgress) { 
        globalProgress.style.display = 'block'; 
        const textEl = document.getElementById('sidebar-scrape-text');
        if (textEl) textEl.textContent = 'Démarrage du scraping...';
    }

    const multiZone = document.getElementById('multi-zone')?.checked || false;

    try {
        const payload = { 
            keyword: kw, 
            city, 
            limit: parseInt(limit), 
            campaign_name: campaignName,
            multi_zone: multiZone
        };
        if (minEmails) payload.min_emails = minEmails;

        const r = await fetch('/api/scraper/launch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const d = await r.json();
        if (d.error) {
            if (globalProgress) globalProgress.style.display = 'none';
            return logEl.textContent += `❌ ${d.error}`;
        }

        _activeScrapingId = d.campaign_id;

        const pollId = setInterval(async () => {
            try {
                const rs = await fetch('/api/scraper/status');
                const ds = await rs.json();

                // Logs (last 20 lines)
                const logs = ds.logs || [];
                logEl.textContent = logs.join('\n');

                // Stats live
                const total = ds.total || limit;
                const scraped = ds.current || 0;
                const withSite = ds.with_site || 0;
                const withEmail = ds.with_email || 0;
                const pct = total > 0 ? Math.round(scraped * 100 / total) : 0;
                const globalProgress = document.getElementById('sidebar-scrape');
                if (globalProgress) {
                    globalProgress.style.display = 'block';
                    
                    const pctEl = document.getElementById('sidebar-scrape-pct');
                    if (pctEl) pctEl.textContent = pct + '%';
                    
                    const barEl = document.getElementById('sidebar-scrape-bar');
                    if (barEl) barEl.style.width = pct + '%';
                    
                    const textEl = document.getElementById('sidebar-scrape-text');
                    if (textEl) textEl.innerHTML = `<strong>${scraped}</strong>/${total} &middot; <span style="color:var(--green)">${withEmail} ✉</span>`;
                }

                if (!ds.running) {
                    clearInterval(pollId);
                    if (_campaignStatsInterval) clearInterval(_campaignStatsInterval);
                    logEl.textContent += `\n✅ Terminé — ${scraped} leads scrapés (${withEmail} emails)`;
                    if (globalProgress) {
                        globalProgress.style.display = 'none';
                    }
                    _activeScrapingId = null;
                    if (typeof refreshAll === 'function') refreshAll();
                }
            } catch (e) { 
                clearInterval(pollId); 
                if (globalProgress) globalProgress.style.display = 'none';
            }
        }, 2000);
    } catch (e) { 
        logEl.textContent += `❌ Erreur: ${e.message}`; 
        if (globalProgress) globalProgress.style.display = 'none';
    }
}

async function loadCampaigns() {
    try {
        const dateFilter = document.getElementById('global-date-start')?.value;
        let url = '/api/campaigns';
        if (dateFilter) url += `?date_start=${dateFilter}&date_end=${dateFilter}`;
        
        const r = await fetch(url);
        const d = await r.json();
        if (d.error) return;

        // Update global select
        const select = document.getElementById('global-campaign-select');
        if (select) {
            const current = select.value;
            let html = '<option value="">Toutes les campagnes</option>';
            d.campaigns.forEach(c => {
                const campName = c.nom || (c.secteur && c.ville ? `${c.secteur} ${c.ville}` : 'Campagne ' + c.id);
                html += `<option value="${c.id}" ${c.id == _activeCampaignId ? 'selected' : ''}>${typeof escHtml === 'function' ? escHtml(campName) : campName}</option>`;
            });
            select.innerHTML = html;
        }

        // Update Badges
        if (typeof setInner === 'function') setInner('nav-badge-campagnes', d.total || '0');

        // Update Campaign View Table
        const tbody = document.getElementById('tbody-campaign-list');
        if (tbody) {
            const rows = d.campaigns.map(c => {
                const date = c.date_creation ? c.date_creation.split(' ')[0] : '—';
                const campName = c.nom || (c.secteur && c.ville ? `${c.secteur} ${c.ville}` : 'Campagne');
                return `
                <tr style="${c.id == _activeCampaignId ? 'background: rgba(var(--brand-rgb), 0.05)' : ''}">
                    <td><strong>${typeof escHtml === 'function' ? escHtml(campName) : campName}</strong></td>
                    <td>${date}</td>
                    <td><span class="b bb">${c.leads_total || 0}</span></td>
                    <td><span class="b" style="color:var(--orange)">${c.nb_audites || 0}</span></td>
                    <td><span class="b bg">${c.emails_envoyes || 0}</span></td>
                    <td><span class="b bb">${c.nb_ouverts || 0}</span></td>
                    <td><span class="b bg">${c.nb_cliques || 0}</span></td>
                    <td><span class="b ok">${c.nb_reponses || 0}</span></td>
                    <td style="text-align:right; white-space:nowrap">
                        <button class="btn ${c.id == _activeCampaignId ? 'bg2' : 'bg1'} sm" onclick="changeGlobalCampaign(${c.id}); nav('cockpit', document.getElementById('nav-cockpit'))">
                            ${c.id == _activeCampaignId ? 'Active' : 'Sélectionner'}
                        </button>
                        <button class="btn bg-error sm" style="margin-left:5px" onclick="deleteCampaign(${c.id}, '${typeof escHtml === 'function' ? escHtml(campName) : campName}')">🗑️</button>
                    </td>
                </tr>`;
            }).join('');
            tbody.innerHTML = rows || '<tr><td colspan="6" style="text-align:center;padding:1rem">Aucune campagne trouvée</td></tr>';
        }
    } catch (e) { console.error('loadCampaigns:', e); }
}

async function deleteCampaign(id, name) {
    if (!confirm(`Êtes-vous sûr de vouloir supprimer la campagne "${name}" ?\nLes leads ne seront pas supprimés mais ne seront plus associés à cette campagne.`)) return;
    try {
        const r = await fetch(`/api/campaigns/${id}`, { method: 'DELETE' });
        if (r.ok) {
            if (typeof showToast === 'function') showToast('✅ Campagne supprimée');
            if (_activeCampaignId == id) _activeCampaignId = null;
            loadCampaigns();
        } else if (typeof showToast === 'function') showToast('❌ Erreur lors de la suppression', 'error');
    } catch (e) { 
        if (typeof showToast === 'function') showToast('❌ Erreur réseau', 'error'); 
    }
}
