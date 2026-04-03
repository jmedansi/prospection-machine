/**
 * dashboard/js/modules/leads.js — Gestion des Prospects (Leads)
 */

async function loadLeads() {
    // Garder la page actuelle si elle existe
    await loadLeadsFiltered(_leadsPagination.page || 1);
}

function onFilterChanged() {
    const pgCollecte = document.getElementById('pg-collecte');
    if (pgCollecte && pgCollecte.classList.contains('active')) {
        // Si on est sur l'onglet collecte, on peut avoir une fonction spécifique ou utiliser la générique
        loadLeadsFiltered();
    } else {
        loadLeadsFiltered();
    }
}

async function loadLeadsFiltered(page = 1) {
    _leadsPagination.page = page;
    try {
        const filterStatut = document.getElementById('filter-statut');
        const filterSite = document.getElementById('filter-site');
        const filterEmail = document.getElementById('filter-email');
        const filterNote = document.getElementById('filter-note');

        if (!filterStatut || !filterSite || !filterEmail || !filterNote) return;

        const statut = filterStatut.value || 'tous';
        const site = filterSite.value || 'tous';
        const email = filterEmail.value || 'tous';
        const note = filterNote.value || 'tous';
        const filterSector = document.getElementById('filter-sector');
        const sector = filterSector ? (filterSector.value || 'tous') : 'tous';

        const p = _leadsPagination.page || 1;
        const url = '/api/leads' + _globalFilters({statut, site, email, note, sector, page: p, limit: 50});

        const r = await fetch(url);
        const d = await r.json();
        if (d.error || !d.leads) return;

        _allLeads = d.leads;
        _leadsPagination = { page: d.page, total_pages: d.total_pages, total: d.total };

        const leads = d.leads;
        const audites = leads.filter(l => l.statut === 'audite' || l.statut === 'envoye' || l.statut === 'email_genere');
        const priorit = audites.filter(l => (l.score_urgence || 0) >= 7).sort((a, b) => (b.score_urgence || 0) - (a.score_urgence || 0));

        if (typeof setText === 'function') {
            setText('leads-count-info', `${d.total} leads trouvés`);
        }

        // --- Rendu Table Collecte ---
        const rowsScraper = leads.map(l => {
            const siteIcon = l.a_site ? '<div class="bc ok">✓</div>' : '<div class="bc err">X</div>';
            const siteLink = l.site_web ? `<a href="${typeof escHtml === 'function' ? escHtml(l.site_web) : l.site_web}" target="_blank" title="Cliquer pour ouvrir le site" style="color:var(--accent);text-decoration:none;cursor:pointer">${siteIcon}</a>` : `<span title="Pas de site" style="cursor:default">${siteIcon}</span>`;
            const emailIcon = l.a_email ? '<div class="bc ok">✓</div>' : '<div class="bc warn">X</div>';
            const emailLink = l.email ? `<a href="mailto:${typeof escHtml === 'function' ? escHtml(l.email) : l.email}" target="_blank" title="Cliquer pour envoyer un email" style="color:var(--accent);text-decoration:none;cursor:pointer">${emailIcon}</a>` : `<span title="Pas d'email" style="cursor:default">${emailIcon}</span>`;
            const statusPill = l.statut === 'audite' || l.statut === 'email_genere' ? '<span class="b bb">Audité</span>' : l.statut === 'envoye' ? '<span class="b bg">Envoyé</span>' : '<span class="b bx">En attente</span>';

            return `
                <tr>
                    <td><input type="checkbox" class="lead-cb" data-id="${l.id}" data-nom="${typeof escHtml === 'function' ? escHtml(l.nom) : l.nom}"></td>
                    <td><strong>${typeof escHtml === 'function' ? escHtml(l.nom || '—') : (l.nom || '—')}</strong></td>
                    <td>${typeof escHtml === 'function' ? escHtml(l.ville || '—') : (l.ville || '—')}</td>
                    <td>${typeof escHtml === 'function' ? escHtml(l.secteur || '—') : (l.secteur || '—')}</td>
                    <td>${l.note ? l.note + ' ⭐' : '—'}</td>
                    <td>${l.avis || '—'}</td>
                    <td>${siteLink}</td>
                    <td>${emailLink}</td>
                    <td>${statusPill}</td>
                    <td style="text-align:right">
                        <button class="btn bg1 sm" onclick="openEditLead('${typeof escHtml === 'function' ? escHtml(l.nom) : l.nom}')">✏️</button>
                        ${l.statut === 'en_attente' || l.statut === 'audit_echoue' ? 
                          `<button class="btn bg1 sm" style="margin-left:5px" onclick="auditLead('${typeof escHtml === 'function' ? escHtml(l.nom) : l.nom}')">Auditer</button>` :
                          `<button class="btn bg2 sm" style="margin-left:5px" onclick="auditLead('${typeof escHtml === 'function' ? escHtml(l.nom) : l.nom}')" title="Relancer l'audit (écrase l'ancien)">🔄 Relancer</button>`
                        }
                    </td>
                </tr>`;
        }).join('');
        setInner('tbody-scraper', rowsScraper || '<tr><td colspan="10" style="text-align:center;padding:1rem">Aucun lead trouvé</td></tr>');

        // --- Rendu Table Cockpit (Derniers Prioritaires) ---
        const rowsSum = priorit.slice(0, 5).map(l => `
            <tr>
                <td><strong>${typeof escHtml === 'function' ? escHtml(l.nom) : l.nom}</strong></td>
                <td style="font-size:10px;color:var(--ink3)">${typeof synthProbleme === 'function' ? synthProbleme(l) : '—'}</td>
                <td>${typeof pillUrgence === 'function' ? pillUrgence(l.score_urgence) : l.score_urgence}</td>
                <td><button class="btn bg1 sm" onclick="openEditLead('${typeof escHtml === 'function' ? escHtml(l.nom) : l.nom}')">Gérer</button></td>
            </tr>
        `).join('');
        setInner('tbody-last-audits', rowsSum || '<tr><td colspan="4" style="text-align:center;padding:1rem">Aucun lead prioritaire</td></tr>');


        // Mettre à jour le select CRM si présent
        const crmSelect = document.getElementById('crm-prospect-select');
        if (crmSelect) {
            const currentVal = crmSelect.value;
            const opts = ['<option value="">— Sélectionner —</option>'];
            _allLeads.slice().sort((a,b)=>(a.nom||'').localeCompare(b.nom||'')).forEach(l=>{
                opts.push(`<option value="${typeof escHtml === 'function' ? escHtml(l.nom) : l.nom}" ${l.nom===currentVal?'selected':''}>${typeof escHtml === 'function' ? escHtml(l.nom) : l.nom}</option>`);
            });
            crmSelect.innerHTML = opts.join('');
        }

        updatePaginationControls();
        loadSectorFilter();

    } catch (e) { console.error('loadLeadsFiltered:', e); }
}

async function loadSectorFilter() {
    const sel = document.getElementById('filter-sector');
    if (!sel) return;
    try {
        const r = await fetch('/api/leads/sectors');
        const d = await r.json();
        if (!d.sectors) return;
        const current = sel.value;
        const opts = ['<option value="tous">Secteur: Tous</option>'];
        d.sectors.forEach(s => {
            opts.push(`<option value="${s}" ${s === current ? 'selected' : ''}>${s}</option>`);
        });
        sel.innerHTML = opts.join('');
    } catch (e) { /* silencieux */ }
}

function updatePaginationControls() {
    const p = _leadsPagination;
    if (typeof setText === 'function') setText('page-info', `page ${p.page} sur ${p.total_pages}`);

    const prevBtn = document.getElementById('btn-prev-page');
    const nextBtn = document.getElementById('btn-next-page');
    const pageSelect = document.getElementById('page-select');

    if (prevBtn) prevBtn.disabled = p.page <= 1;
    if (nextBtn) nextBtn.disabled = p.page >= p.total_pages;

    if (pageSelect) {
        pageSelect.innerHTML = '';
        for (let i = 1; i <= Math.min(p.total_pages, 20); i++) {
            const opt = document.createElement('option');
            opt.value = i;
            opt.textContent = i;
            if (i === p.page) opt.selected = true;
            pageSelect.appendChild(opt);
        }
    }
}

function changePage(delta) {
    const newPage = _leadsPagination.page + delta;
    if (newPage >= 1 && newPage <= _leadsPagination.total_pages) {
        _leadsPagination.page = newPage;
        loadLeadsFiltered();
    }
}

function goToPage(pageNum) {
    _leadsPagination.page = parseInt(pageNum);
    loadLeadsFiltered();
}

function toggleAllLeads(masterCb) {
    const checked = masterCb.checked;
    document.querySelectorAll('#tbody-scraper .lead-cb').forEach(cb => cb.checked = checked);
}

function getSelectedLeadIds() {
    const ids = [];
    document.querySelectorAll('#tbody-scraper .lead-cb:checked').forEach(cb => {
        ids.push(parseInt(cb.dataset.id));
    });
    return ids;
}

function getSelectedLeadNoms() {
    const noms = [];
    document.querySelectorAll('.lead-cb:checked').forEach(cb => {
        if (cb.dataset.nom) noms.push(cb.dataset.nom);
    });
    return noms;
}

function openEditLead(leadNom) {
    const l = _allLeads.find(x => x.nom === leadNom);
    if (!l) { showToast("Impossible de trouver les détails de " + leadNom, 'error'); return; }
    document.getElementById('edit-lead-id').value = l.id || '';
    document.getElementById('edit-lead-nom').value = l.nom || '';
    document.getElementById('edit-lead-email').value = l.email || '';
    document.getElementById('edit-lead-tel').value = l.telephone || '';
    document.getElementById('edit-lead-site').value = l.site_web || '';
    document.getElementById('edit-lead-sector').value = l.secteur || '';
    document.getElementById('edit-lead-ville').value = l.ville || '';
    if (typeof openModal === 'function') openModal('modal-edit-lead');
}

async function saveLead() {
    const id = document.getElementById('edit-lead-id').value;
    const data = {
        nom: document.getElementById('edit-lead-nom').value,
        email: document.getElementById('edit-lead-email').value,
        telephone: document.getElementById('edit-lead-tel').value,
        site_web: document.getElementById('edit-lead-site').value,
        category: document.getElementById('edit-lead-sector').value,
        ville: document.getElementById('edit-lead-ville').value
    };
    try {
        const r = await fetch('/api/leads/' + id, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data)
        });
        if (r.ok) { 
            if (typeof closeModal === 'function') closeModal('modal-edit-lead'); 
            loadLeads();
            if (typeof loadCampaignTable === 'function') loadCampaignTable();
        }
        else showToast("Erreur lors de la sauvegarde", 'error');
    } catch (e) { console.error(e); }
}

async function deleteLead() {
    const id = document.getElementById('edit-lead-id').value;
    const nom = document.getElementById('edit-lead-nom').value;
    if (!await showConfirm(`Supprimer définitivement le lead "${nom}" et tous ses audits ?`, { title: 'Supprimer le lead', confirmText: 'Supprimer', danger: true })) return;
    try {
        const r = await fetch('/api/leads/' + id, { method: 'DELETE' });
        if (r.ok) {
            if (typeof closeModal === 'function') closeModal('modal-edit-lead');
            if (typeof refreshAll === 'function') refreshAll();
            if (typeof loadCampaignTable === 'function') loadCampaignTable();
        }
    } catch (e) { console.error(e); }
}

async function deleteSelectedLeads() {
    const ids = getSelectedLeadIds();
    if (!ids.length) { showToast('Sélectionner au moins un lead', 'error'); return; }
    if (!await showConfirm(`Supprimer définitivement ${ids.length} lead(s) sélectionné(s) et tous leurs audits ?`, { title: 'Suppression en masse', confirmText: 'Supprimer', danger: true })) return;
    try {
        const r = await fetch('/api/leads/batch-delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids })
        });
        const d = await r.json();
        if (d.success) {
            showToast(`${d.deleted} lead(s) supprimé(s)`, 'success');
            loadLeads();
            if (typeof loadCampaignTable === 'function') loadCampaignTable();
        } else {
            showToast(d.error || 'Erreur lors de la suppression', 'error');
        }
    } catch (e) { console.error(e); showToast('Erreur réseau', 'error'); }
}

async function purgeZeroAvis() {
    if (!await showConfirm('Supprimer tous les leads sans avis (0 ou vide) non encore contactés ?', { title: 'Purge des leads', confirmText: 'Purger', danger: true })) return;
    try {
        const r = await fetch('/api/leads/purge-zero-avis', { method: 'POST' });
        const d = await r.json();
        if (d.success) {
            showToast(`${d.deleted} lead(s) purgé(s)`, 'success');
            if (typeof refreshAll === 'function') refreshAll();
        } else {
            showToast(d.error || 'Erreur lors de la purge', 'error');
        }
    } catch (e) { console.error(e); showToast('Erreur réseau', 'error'); }
}

async function retryFailedAudits() {
    if (!await showConfirm('Relancer l\'audit sur tous les leads en échec (ceux avec un site web) ?', { title: 'Relancer les audits échoués', confirmText: 'Relancer' })) return;
    try {
        const r = await fetch('/api/audit/retry-failed', { method: 'POST' });
        const d = await r.json();
        if (d.success) {
            if (d.count === 0) {
                showToast('Aucun audit échoué à relancer', 'info');
            } else {
                showToast(`${d.count} lead(s) remis en attente — lancez l'audit pour les traiter`, 'success');
                if (typeof refreshAll === 'function') refreshAll();
            }
        } else {
            showToast(d.error || 'Erreur', 'error');
        }
    } catch (e) { console.error(e); showToast('Erreur réseau', 'error'); }
}

function exportSelected() {
    const selected = getSelectedLeadIds();
    if (!selected.length) { showToast('Sélectionner au moins un lead', 'warning'); return; }

    const leadsToExport = _allLeads.filter(l => selected.includes(l.id));
    const csv = ['Nom,Ville,Secteur,Note,Avis,Site,Email,Statut'];
    leadsToExport.forEach(l => {
        csv.push(`"${l.nom}","${l.ville}","${l.secteur}",${l.note},${l.avis},"${l.site_web}","${l.email}","${l.statut}"`);
    });

    const blob = new Blob([csv.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `leads_export_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    if (typeof showToast === 'function') showToast(`✅ Export CSV généré (${leadsToExport.length} leads)`);
}

async function exportFilteredLeads() {
    try {
        if (typeof showToast === 'function') showToast('Récupération de tous les leads filtrés…', 'info');

        // Build filter params from current UI state
        const params = new URLSearchParams();
        const statutEl = document.getElementById('filter-statut');
        const siteEl   = document.getElementById('filter-site');
        const emailEl  = document.getElementById('filter-email');
        const sectorEl = document.getElementById('filter-sector');
        if (statutEl) params.set('statut', statutEl.value || 'tous');
        if (siteEl)   params.set('site',   siteEl.value   || 'tous');
        if (emailEl)  params.set('email',  emailEl.value  || 'tous');
        if (sectorEl && sectorEl.value && sectorEl.value !== 'tous') params.set('sector', sectorEl.value);
        params.set('limit', '500');
        params.set('page', '1');

        const r = await fetch('/api/leads?' + params.toString());
        const d = await r.json();
        if (!d.leads || !d.leads.length) { showToast('Aucun lead à exporter', 'error'); return; }

        const CSV_SEP = ';'; // semi-colon for Excel compatibility
        const escape = v => '"' + String(v || '').replace(/"/g, '""') + '"';
        const header = ['Nom', 'Ville', 'Secteur', 'Note', 'Avis', 'Site', 'Email', 'Téléphone', 'Statut', 'Score urgence'].join(CSV_SEP);
        const rows = d.leads.map(l => [
            l.nom, l.ville, l.secteur || l.category, l.note, l.avis || l.nb_avis,
            l.site_web, l.email, l.telephone, l.statut, l.score_urgence
        ].map(escape).join(CSV_SEP));

        const bom = '\uFEFF'; // UTF-8 BOM for Excel
        const blob = new Blob([bom + [header, ...rows].join('\n')], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `leads_export_${new Date().toISOString().slice(0, 10)}.csv`;
        a.click();
        URL.revokeObjectURL(url);
        if (typeof showToast === 'function') showToast(`Export CSV : ${d.leads.length} leads (sur ${d.total} au total)`, 'success');
    } catch (e) { console.error(e); if (typeof showToast === 'function') showToast('Erreur export', 'error'); }
}

function shareReport(name, url) {
    if (navigator.clipboard) {
        navigator.clipboard.writeText(url).then(() => {
            showToast(`Lien du rapport pour ${name} copié`, 'success');
        });
    } else {
        showToast("Lien du rapport: " + url, 'info');
    }
}
