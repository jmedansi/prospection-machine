/**
 * dashboard/static/js/modules/unified_leads.js
 * Table unifiée Maps + Sniper.
 */

const _ul = { leads: [], page: 1, totalPages: 1, total: 0, editingId: null, view: 'list', v2ObjectifId: null, v2ObjectifNom: '' };
// Exposer l'état sur window : objectifs.js et le sélecteur global (header) s'appuient dessus
window._ul = _ul;

const _V2_STATUTS = [
    ['qualifie', 'Qualifié'], ['en_sequence', 'En séquence'], ['relance_1', 'Relance 1'],
    ['relance_2', 'Relance 2'], ['relance_3', 'Relance 3'], ['a_traiter_humain', 'À traiter (répondu)'],
    ['rdv_obtenu', 'RDV obtenu'], ['a_relancer_plus_tard', 'À relancer plus tard'],
    ['pas_interesse', 'Pas intéressé'], ['sans_reponse', 'Sans réponse'],
    ['ne_plus_contacter', 'Ne plus contacter'], ['adresse_invalide', 'Adresse invalide'],
];

function unifiedLeadsInit() {
    const boot = () => {
        if (typeof window.ObjectifsModule !== 'undefined' && window.ObjectifsModule.init) {
            window.ObjectifsModule.init(); // charge l'objectif mémorisé puis charge les leads
        } else {
            unifiedLeadsLoad();
        }
    };
    _ulFetchTransitions();
    if (typeof window.unifiedLeadsLoadLists === 'function') {
        window.unifiedLeadsLoadLists().then(() => {
            const urlParams = new URLSearchParams(window.location.search);
            const listId = urlParams.get('list_id');
            if (listId) {
                const selectEl = document.getElementById('ul-filter-list');
                if (selectEl) {
                    selectEl.value = listId;
                }
            }
            boot();
        });
    } else {
        boot();
    }
}

window.unifiedLeadsLoadLists = async function() {
    try {
        const r = await fetch('/api/lists');
        const d = await r.json();
        const lists = d.lists || [];
        
        // Populate dropdown in Leads view
        const selectLeads = document.getElementById('ul-filter-list');
        if (selectLeads) {
            const currentVal = selectLeads.value;
            selectLeads.innerHTML = '<option value="">Toutes listes</option>' + 
                lists.map(lst => `<option value="${lst.id}">${lst.icone} ${lst.nom} (${lst.nb_leads})</option>`).join('');
            selectLeads.value = currentVal;
        }

        // Populate dropdown in Tracking Board view
        const selectTracking = document.getElementById('tracking-filter-list');
        if (selectTracking) {
            const currentVal = selectTracking.value;
            selectTracking.innerHTML = '<option value="">Toutes listes</option>' + 
                lists.map(lst => `<option value="${lst.id}">${lst.icone} ${lst.nom}</option>`).join('');
            selectTracking.value = currentVal;
        }

        // Populate dropdown in Sniper view
        const selectSniper = document.getElementById('sniper-filter-list');
        if (selectSniper) {
            const currentVal = selectSniper.value;
            selectSniper.innerHTML = '<option value="">Toutes listes</option>' + 
                lists.map(lst => `<option value="${lst.id}">${lst.icone} ${lst.nom}</option>`).join('');
            selectSniper.value = currentVal;
        }

        // Populate dropdown in CRM view (if it exists)
        const selectCRM = document.getElementById('crm-filter-list');
        if (selectCRM) {
            const currentVal = selectCRM.value;
            selectCRM.innerHTML = '<option value="">Toutes listes</option>' + 
                lists.map(lst => `<option value="${lst.id}">${lst.icone} ${lst.nom}</option>`).join('');
            selectCRM.value = currentVal;
        }
    } catch (e) {
        console.error('[unifiedLeadsLoadLists] Error:', e);
    }
};

async function unifiedLeadsLoad(page = 1) {
    _ul.page = page;
    const tbody = document.getElementById('ul-tbody');
    if (!tbody) return;
    const limit = document.getElementById('ul-filter-limit')?.value || 50;

    // Mode Objectif (v2) : la page n'affiche QUE les leads de l'objectif choisi.
    if (_ul.v2ObjectifId) return _ulV2Load(tbody, limit);

    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:24px;color:var(--ink3)">Chargement…</td></tr>`;

    const params = new URLSearchParams({ page, limit });
    const listId = document.getElementById('ul-filter-list')?.value || '';
    const source = document.getElementById('ul-filter-source')?.value || '';
    const statut = document.getElementById('ul-filter-statut')?.value || '';
    const tag = document.getElementById('ul-filter-tag')?.value || '';
    const site = document.getElementById('ul-filter-site')?.value || '';
    const email = document.getElementById('ul-filter-email')?.value || '';
    const score = document.getElementById('ul-filter-score')?.value || '';
    const notes = document.getElementById('ul-filter-notes')?.value || '';
    let sector = document.getElementById('ul-filter-sector')?.value || '';
    // Fallback au filtre global (top bar) si le local est vide
    if (!sector && typeof _activeSector !== 'undefined' && _activeSector) {
        sector = _activeSector;
    }
    const search = document.getElementById('ul-search')?.value?.trim() || '';
    const objectif = document.getElementById('ul-filter-objectif')?.value || 'tous';
    const showFlagged = document.getElementById('ul-filter-flagged')?.value === 'true';
    if (listId) params.set('list_id', listId);
    if (source) params.set('source', source);
    if (statut) params.set('statut', statut);
    if (tag) params.set('tag', tag);
    if (site) params.set('site_filter', site);
    if (email) params.set('email_filter', email);
    if (score) params.set('score_filter', score);
    if (notes) params.set('notes_filter', notes);
    if (sector) params.set('sector', sector);
    if (typeof _activeCampaignId !== 'undefined' && _activeCampaignId) {
        params.set('campaign_id', _activeCampaignId);
    }
    if (search) params.set('search', search);
    if (objectif && objectif !== 'tous') params.set('objectif', objectif);
    if (showFlagged) {
        params.set('show_ecartes', 'true');
        params.set('show_desinscrits', 'true');
    }

    try {
        const r = await fetch(`/api/leads/all?${params}`);
        const d = await r.json();
        if (d.error) {
            tbody.innerHTML = `<tr><td colspan="8" style="color:var(--error);text-align:center;padding:16px">${_ulEsc(d.error)}</td></tr>`;
            return;
        }
        _ul.leads = d.leads || [];
        _ul.page = d.page;
        _ul.totalPages = d.total_pages;
        _ul.total = d.total;

        // Alimente le cache du side panel existant
        if (typeof _campaignData !== 'undefined') _campaignData = _ul.leads;

        if (_ul.view === 'kanban') {
            renderKanban(_ul.leads);
        } else {
            tbody.innerHTML = _ul.leads.length
                ? _ul.leads.map(_ulRow).join('')
                : `<tr><td colspan="8" style="text-align:center;padding:24px;color:var(--ink3)">Aucun lead</td></tr>`;
        }

        _ulUpdatePagination();
        _ulUpdateCount();
    } catch (e) {
        console.error('[unified_leads]', e);
        if (tbody) tbody.innerHTML = `<tr><td colspan="8" style="color:var(--error);text-align:center;padding:16px">Erreur : ${e.message}</td></tr>`;
    }
}

async function _ulV2Load(tbody, limit) {
    const params = new URLSearchParams({ page: _ul.page, limit });
    const search = document.getElementById('ul-search')?.value?.trim() || '';
    const statut = document.getElementById('ul-filter-statut')?.value || '';
    if (search) params.set('search', search);
    if (statut) params.set('statut', statut);
    try {
        const r = await fetch(`/api/v2/objectifs/${_ul.v2ObjectifId}/leads?${params}`);
        const d = await r.json();
        if (d.error) {
            tbody.innerHTML = `<tr><td colspan="8" style="color:var(--error);text-align:center;padding:16px">${_ulEsc(d.error)}</td></tr>`;
            return;
        }
        _ul.leads = d.leads || [];
        _ul.page = d.page;
        _ul.totalPages = d.total_pages;
        _ul.total = d.total;
        if (typeof _campaignData !== 'undefined') _campaignData = _ul.leads;
        tbody.innerHTML = _ul.leads.length
            ? _ul.leads.map(_ulRow).join('')
            : `<tr><td colspan="8" style="text-align:center;padding:24px;color:var(--ink3)">
                Aucun lead dans cet objectif — cliquez sur « Importer CSV » pour en ajouter.</td></tr>`;
        _ulUpdatePagination();
        _ulUpdateCount();
    } catch (e) {
        console.error('[unified_leads v2]', e);
        if (tbody) tbody.innerHTML = `<tr><td colspan="8" style="color:var(--error);text-align:center;padding:16px">Erreur : ${e.message}</td></tr>`;
    }
}

// Bascule le filtre « statut » entre valeurs legacy et statuts v2 de la machine à états.
function _ulSetStatutFilter(v2mode) {
    const el = document.getElementById('ul-filter-statut');
    if (!el) return;
    if (v2mode) {
        if (!_ul._legacyStatutOptions) _ul._legacyStatutOptions = el.innerHTML;
        el.innerHTML = '<option value="">Tous les statuts</option>' +
            _V2_STATUTS.map(([v, l]) => `<option value="${v}">${l}</option>`).join('');
    } else if (_ul._legacyStatutOptions) {
        el.innerHTML = _ul._legacyStatutOptions;
    }
}

// Chargement des transitions autorisées (machine à états) pour la file humaine.
async function _ulFetchTransitions() {
    try {
        const r = await fetch('/api/v2/statuts/transitions', { cache: 'no-store' });
        const d = await r.json();
        if (d.success) {
            _ul.transitions = d.transitions || {};
            _ul.statutLabels = d.labels || {};
        }
    } catch (e) {
        console.error('[unified_leads] transitions', e);
    }
}

// Statuts "réciproques" que la file humaine peut ré-ouvrir vers le flux d'envoi.
const _REOPEN = { a_traiter_humain: 1, sans_reponse: 1, a_relancer_plus_tard: 1 };

// Sélecteur rapide de statut (file humaine) — vide si aucun choix possible.
function _ulStatutQuick(l) {
    if (!_ul.transitions || !_ul.v2ObjectifId) return '';
    const next = (_ul.transitions[l.statut] || []).filter(s => s !== l.statut);
    if (!next.length || _REOPEN[l.statut] && next.every(s => ['ne_plus_contacter', 'adresse_invalide'].includes(s))) {
        return '';
    }
    const opts = next
        .filter(s => !['ne_plus_contacter', 'adresse_invalide'].includes(s) || _REOPEN[l.statut])
        .map(s => `<option value="${s}">${_ul.statutLabels[s] || s}</option>`).join('');
    return `<select class="inp sm" style="max-width:150px;padding:3px 6px;font-size:11px"
                onchange="unifiedLeadsChangeStatut(${l.id}, this.value); this.selectedIndex = -1;"
                onclick="event && event.stopPropagation()">
                <option value="" selected>→ Statut</option>${opts}</select>`;
}

async function unifiedLeadsChangeStatut(id, statut) {
    if (!statut) return;
    const l = _ul.leads.find(x => x.id == id);
    const ok = window.confirm(`Passer « ${l?.nom || id} » → ${_ul.statutLabels[statut] || statut} ?`);
    if (!ok) return;
    try {
        const r = await fetch(`/api/v2/leads/${id}/statut`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ statut, reason: 'file humaine (UI)' }),
        });
        const d = await r.json();
        if (!d.success) { showToast?.('Erreur : ' + (d.error || 'transition refusée'), 'error'); return; }
        showToast?.(`${l?.nom || 'Prospect'} → ${_ul.statutLabels[statut] || statut}`, 'success');
        unifiedLeadsLoad(_ul.page);
    } catch (e) {
        console.error('[unified_leads] changeStatut', e);
        showToast?.('Erreur réseau', 'error');
    }
}

function _ulRow(l) {
    if (l.id === _ul.leads[0]?.id) console.log('[UL DEBUG] Row data:', l);
    const nom = _ulEsc(l.nom || '—');
    const initial = nom.charAt(0).toUpperCase();
    const siteUrl = _ulEsc(l.site_web || '');

    // Badge source
    const srcMap = { maps: '#6b7280', ads: '#f97316', fb_ads: '#1877f2', tech: '#8b5cf6', ecom: '#8b5cf6', jobs: '#06b6d4', bodacc: '#10b981' };
    const srcCol = srcMap[l.source] || '#9ca3af';
    const srcBadge = `<span style="background:${srcCol}15;color:${srcCol};padding:1px 5px;border-radius:4px;font-size:9px;font-weight:700;text-transform:uppercase;margin-right:5px">${l.source || '?'}</span>`;

    const nomCell = siteUrl
        ? `<a href="${siteUrl}" target="_blank" class="lead-name" style="color:var(--ink1);text-decoration:none">${nom}</a>`
        : `<strong class="lead-name">${nom}</strong>`;

    // Catégorie étudiée/IA (si présente), sinon catégorie Maps comme avant
    const meta = l.categorie
        ? `${srcBadge}${_ulEsc(l.categorie)}`
        : `${srcBadge}${_ulEsc(l.category || l.secteur || 'Prospect')}`;

    // Marquage écarté / désinscrit
    const flags = [];
    if (l.ecarte) flags.push('<span style="font-size:9px;padding:1px 5px;border-radius:3px;background:#ef444420;color:#ef4444">écarté</span>');
    if (l.desinscrit) flags.push('<span style="font-size:9px;padding:1px 5px;border-radius:3px;background:#6b728020;color:#6b7280">désinscrit</span>');

    const rowClick = _ul.v2ObjectifId ? `unifiedLeadsOpenEdit(${l.id})` : `openLeadPanel(${l.id})`;
    return `<tr onclick="${rowClick}" style="cursor:pointer" class="${_selectedLeadId === l.id ? 'selected' : ''}${(l.ecarte || l.desinscrit) ? ' ul-flagged' : ''}">
        <td class="col-check" onclick="event && event.stopPropagation()">
            <input type="checkbox" class="ul-cb lead-cb" data-id="${l.id}" data-nom="${_ulEsc(l.nom)}">
        </td>
        <td class="col-prospect">
            <div class="lead-cell-flex">
                <div class="lead-avatar">${initial}</div>
                <div class="lead-info">
                    ${nomCell}
                    <div class="lead-meta">${meta}${flags.length ? ' ' + flags.join(' ') : ''}</div>
                </div>
            </div>
        </td>
        <td class="col-source" style="font-size:11px;color:var(--ink3)">${_ulEsc(l.ville || '')}</td>
        <td class="col-contact">${_ulContactCell(l)}</td>
        <td class="col-objectif">${_ulObjectifBadge(l)}</td>
        <td class="col-score">${_ulScoreCell(l)}</td>
        <td class="col-statut">${_ulStatutBadge(l.statut_display)}</td>
        <td class="col-actions" style="text-align:right;white-space:nowrap" onclick="event && event.stopPropagation()">${_ulActions(l)}</td>
    </tr>`;
}

function _ulObjectifBadge(l) {
    if (_ul.v2ObjectifId) {
        const nom = _ul.v2ObjectifNom || l.objectif_nom || 'Objectif';
        return `<span style="background:#10b98120;color:#10b981;border:1px solid #10b98140;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700">${_ulEsc(nom)}</span>`;
    }
    const isWeb = (l.objectif || 'general') === 'web';
    const color = isWeb ? '#10b981' : '#3b82f6';
    const label = isWeb ? 'Web' : 'Gén.';
    const title = isWeb ? 'Objectif Sites Web — cliquer pour basculer en Général' : 'Objectif Général (ni qualification web ni maquette) — cliquer pour basculer en Sites Web';
    return `<button class="ul-obj-badge" data-id="${l.id}" title="${title}" onclick="event.stopPropagation(); ulToggleObjectif(${l.id})" style="background:${color}20;color:${color};border:1px solid ${color}40;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700;cursor:pointer">${label}</button>`;
}

async function ulToggleObjectif(leadId) {
    if (_ul.v2ObjectifId) return; // classement Web/Général réservé à la vue Archive
    const lead = _ul.leads.find(x => x.id === leadId);
    if (!lead) return;
    const current = (lead.objectif || 'general') === 'web' ? 'web' : 'general';
    const next = current === 'web' ? 'general' : 'web';
    try {
        const r = await fetch(`/api/leads/${leadId}/objectif`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ objectif: next })
        });
        const d = await r.json();
        if (!d.success) throw new Error(d.error);
        showToast?.(next === 'web' ? 'Objectif : Sites Web' : 'Objectif : Général', 'success');
        unifiedLeadsLoad(_ul.page);
    } catch (e) {
        console.error('[ulToggleObjectif]', e);
        showToast?.('Erreur bascule objectif', 'error');
    }
}

async function ulToggleEcarte(leadId) {
    const lead = _ul.leads.find(x => x.id === leadId);
    if (!lead) return;
    const next = !lead.ecarte;
    try {
        const url = _ul.v2ObjectifId ? `/api/v2/leads/${leadId}/ecarter` : `/api/leads/${leadId}/ecarter`;
        const r = await fetch(url, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ecarte: next })
        });
        const d = await r.json();
        if (!d.success) throw new Error(d.error);
        showToast?.(next ? "Lead écarté des flux d'envoi" : 'Lead réintégré', 'success');
        unifiedLeadsLoad(_ul.page);
    } catch (e) {
        console.error('[ulToggleEcarte]', e);
        showToast?.('Erreur', 'error');
    }
}

async function ulToggleDesinscrit(leadId) {
    const lead = _ul.leads.find(x => x.id === leadId);
    if (!lead) return;
    const next = !lead.desinscrit;
    try {
        const url = _ul.v2ObjectifId ? `/api/v2/leads/${leadId}/desinscrire` : `/api/leads/${leadId}/desinscrire`;
        const body = _ul.v2ObjectifId ? { ne_plus_contacter: next } : { desinscrit: next };
        const r = await fetch(url, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
        });
        const d = await r.json();
        if (!d.success) throw new Error(d.error);
        showToast?.(next ? 'Lead désinscrit' : 'Lead réactivé', 'success');
        unifiedLeadsLoad(_ul.page);
    } catch (e) {
        console.error('[ulToggleDesinscrit]', e);
        showToast?.('Erreur', 'error');
    }
}

async function ulToggleAllObjectif() {
    if (_ul.v2ObjectifId) { showToast?.('Le classement Web ⇄ Général ne concerne pas les objectifs', 'error'); return; }
    const ids = ulGetSelectedIds();
    if (!ids.length) { showToast?.('Sélectionner au moins un lead', 'error'); return; }
    const current = _ul.leads[0]?.objectif || 'general';
    const obj = current === 'web' ? 'general' : 'web';
    try {
        const r = await fetch('/api/leads/batch-classify', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lead_ids: ids, action: 'set_objectif', objectif: obj })
        });
        const d = await r.json();
        if (!d.success) throw new Error(d.error);
        showToast?.(`${d.updated} lead(s) → ${obj === 'web' ? 'Sites Web' : 'Général'}`, 'success');
        unifiedLeadsLoad(_ul.page);
    } catch (e) {
        console.error('[ulToggleAllObjectif]', e);
        showToast?.('Erreur', 'error');
    }
}

async function ulEcarterSelection() {
    const ids = ulGetSelectedIds();
    if (!ids.length) { showToast?.('Sélectionner au moins un lead', 'error'); return; }
    try {
        const r = await fetch('/api/leads/batch-classify', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lead_ids: ids, action: 'ecarter' })
        });
        const d = await r.json();
        if (!d.success) throw new Error(d.error);
        showToast?.(`${d.updated} lead(s) écarté(s)`, 'success');
        unifiedLeadsLoad(_ul.page);
    } catch (e) {
        console.error('[ulEcarterSelection]', e);
        showToast?.('Erreur', 'error');
    }
}

// ─── Import CSV (objectif + liste de destination) ──────────────────────────
let _ulImportLists = [];

async function ulOpenImportDialog() {
    // Construit une modale légère dans le DOM
    let m = document.getElementById('ul-import-modal');
    if (!m) {
        m = document.createElement('div');
        m.id = 'ul-import-modal';
        m.style.cssText = 'position:fixed;inset:0;background:rgba(15,23,42,.5);z-index:9999;display:flex;align-items:center;justify-content:center;';
        m.innerHTML = `
        <div style="background:#fff;border-radius:14px;padding:22px;width:min(520px,92vw);box-shadow:0 10px 40px rgba(0,0,0,.2);font-family:inherit">
          <h3 style="margin:0 0 6px;font-size:1.05rem;font-weight:700">Importer des leads (CSV)</h3>
          <p style="margin:0 0 14px;font-size:12px;color:#64748b">Lignes <code>nom,ville,telephone,email,site_web,secteur</code>. Ne fait jamais d'envoi.</p>
          <div id="ul-import-objectif-badge" style="margin-bottom:10px;font-size:12px;color:#2563eb;font-weight:600;display:none"></div>
          <label style="display:block;font-size:12px;font-weight:600;color:#475569;margin-bottom:4px">Fichier CSV (.csv / .txt)</label>
          <input type="file" id="ul-import-file" accept=".csv,.txt" style="margin-bottom:12px;width:100%">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px">
            <div id="ul-import-objectif-wrap">
              <label style="display:block;font-size:12px;font-weight:600;color:#475569;margin-bottom:4px">Objectif</label>
              <select id="ul-import-objectif" style="width:100%;padding:7px;border:1px solid #cbd5e1;border-radius:8px;background:#fff">
                <option value="general">Général</option>
                <option value="web">Web · maquette + email</option>
              </select>
            </div>
            <div>
              <label style="display:block;font-size:12px;font-weight:600;color:#475569;margin-bottom:4px">Liste de destination</label>
              <select id="ul-import-list" style="width:100%;padding:7px;border:1px solid #cbd5e1;border-radius:8px;background:#fff">
                <option value="">— Sans liste —</option>
              </select>
            </div>
          </div>
          <div id="ul-import-log" style="font-size:12px;color:#475569;margin-bottom:12px;min-height:18px"></div>
          <div style="display:flex;gap:10px;justify-content:flex-end">
            <button onclick="ulCloseImportDialog()" style="padding:8px 14px;border:1px solid #cbd5e1;background:#fff;border-radius:8px;cursor:pointer">Annuler</button>
            <button onclick="ulSubmitImport()" style="padding:8px 14px;border:0;background:#2563eb;color:#fff;border-radius:8px;cursor:pointer;font-weight:600">Importer</button>
          </div>
        </div>`;
        document.body.appendChild(m);
    }
    m.style.display = 'flex';
    const v2mode = !!_ul.v2ObjectifId;
    const objWrap = document.getElementById('ul-import-objectif-wrap');
    const objBadge = document.getElementById('ul-import-objectif-badge');
    if (objWrap) objWrap.style.display = v2mode ? 'none' : '';
    if (objBadge) {
        objBadge.style.display = v2mode ? '' : 'none';
        objBadge.textContent = v2mode ? `Import dans l'objectif « ${_ul.v2ObjectifNom || _ul.v2ObjectifId} »` : '';
    }
    const log = document.getElementById('ul-import-log');
    if (log) log.textContent = '';
    const file = document.getElementById('ul-import-file');
    if (file) file.value = '';
    // Charge les listes
    try {
        const r = await fetch('/api/lists');
        const d = await r.json();
        _ulImportLists = d.lists || d || [];
        const sel = document.getElementById('ul-import-list');
        if (sel) {
            sel.innerHTML = '<option value="">— Sans liste —</option>' + _ulImportLists
                .filter(l => l && (l.id !== undefined))
                .map(l => `<option value="${l.id}">${String(l.nom || ('Liste ' + l.id)).replace(/</g, '&lt;')}</option>`)
                .join('');
        }
    } catch (e) { console.error('[ul import] lists', e); }
}

function ulCloseImportDialog() {
    const m = document.getElementById('ul-import-modal');
    if (m) m.style.display = 'none';
}

function _parseCsvToList(text) {
    const lines = text.split(/\r?\n/).filter(l => l.trim() !== '');
    if (!lines.length) return [];
    const header = lines[0].split(',').map(h => h.trim().toLowerCase().replace(/^["']|["']$/g, '').replace(/^\uFEFF/, ''));
    const idx = {
        nom: header.indexOf('nom'), ville: header.indexOf('ville'), telephone: header.indexOf('telephone') >= 0 ? header.indexOf('telephone') : header.indexOf('tel'),
        email: header.indexOf('email'), site_web: header.indexOf('site_web') >= 0 ? header.indexOf('site_web') : header.indexOf('site'),
        secteur: header.indexOf('secteur') >= 0 ? header.indexOf('secteur') : header.indexOf('category'),
    };
    const out = [];
    for (let i = 1; i < lines.length; i++) {
        const c = lines[i].split(',');
        const nom = idx.nom >= 0 ? (c[idx.nom] || '').trim() : '';
        if (!nom) continue;
        out.push({
            nom,
            ville: idx.ville >= 0 ? (c[idx.ville] || '').trim() : '',
            telephone: idx.telephone >= 0 ? (c[idx.telephone] || '').trim() : '',
            email: idx.email >= 0 ? (c[idx.email] || '').trim() : '',
            site_web: idx.site_web >= 0 ? (c[idx.site_web] || '').trim() : '',
            secteur: idx.secteur >= 0 ? (c[idx.secteur] || '').trim() : '',
        });
    }
    return out;
}

async function ulSubmitImport() {
    const fileInput = document.getElementById('ul-import-file');
    const file = fileInput?.files && fileInput.files[0];
    if (!file) { showToast?.('Choisir un fichier CSV', 'error'); return; }
    const text = await file.text();
    const rows = _parseCsvToList(text);
    if (!rows.length) { showToast?.('Aucune ligne exploitable', 'error'); return; }
    const listId = document.getElementById('ul-import-list')?.value || null;
    const log = document.getElementById('ul-import-log');
    if (log) log.textContent = `Import de ${rows.length} lead(s)…`;
    try {
        if (_ul.v2ObjectifId) {
            // Mode Objectif : import DANS l'objectif actif (endpoint v2)
            const r = await fetch(`/api/v2/objectifs/${_ul.v2ObjectifId}/leads/import`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rows, source: 'import' })
            });
            const d = await r.json();
            if (!r.ok || d.error) throw new Error(d.error || 'Erreur import');
            if (log) log.textContent = `✓ ${d.importes} importé(s), ${d.doublons} doublon(s), ${d.supprimes} désinscrit(s), ${d.errors} erreur(s).`;
            showToast?.(`${d.importes} lead(s) importés dans l'objectif`, 'success');
            unifiedLeadsLoad(_ul.page);
            window.ObjectifsModule?.refreshStats();
            return;
        }
        const objectif = document.getElementById('ul-import-objectif')?.value || 'general';
        const r = await fetch('/api/leads/import', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rows, objectif, list_id: listId ? parseInt(listId) : null, source: 'import' })
        });
        const d = await r.json();
        if (!r.ok || d.error) throw new Error(d.error || 'Erreur import');
        if (log) log.textContent = `✓ ${d.importes} importé(s), ${d.doublons} doublon(s), ${d.errors} erreur(s)${listId ? ' · liste appliquée' : ''}.`;
        showToast?.(`${d.importes} lead(s) importés`, 'success');
        unifiedLeadsLoad(_ul.page);
    } catch (e) {
        console.error('[ul import]', e);
        showToast?.(e.message || 'Erreur import', 'error');
    }
}

async function ulDesinscrireSelection() {
    const ids = ulGetSelectedIds();
    if (!ids.length) { showToast?.('Sélectionner au moins un lead', 'error'); return; }
    try {
        const r = await fetch('/api/leads/batch-classify', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lead_ids: ids, action: 'desinscrire' })
        });
        const d = await r.json();
        if (!d.success) throw new Error(d.error);
        showToast?.(`${d.updated} lead(s) désinscrit(s)`, 'success');
        unifiedLeadsLoad(_ul.page);
    } catch (e) {
        console.error('[ulDesinscrireSelection]', e);
        showToast?.('Erreur', 'error');
    }
}

function _ulContactCell(l) {
    const parts = [];

    // Indicateurs visuels pour site et email
    const hasSite = l.site_web && l.site_web.trim() !== '';
    const hasEmail = (l.email && l.email.trim() !== '') || (l.email_valide && l.email_valide.trim() !== '');

    const indicators = `<div style="display:flex;gap:4px;margin-bottom:4px">
        <span style="font-size:9px;padding:1px 4px;border-radius:3px;background:${hasSite ? '#10b98120' : '#ef444420'};color:${hasSite ? '#10b981' : '#ef4444'}">${hasSite ? '🌐' : '—'}</span>
        <span style="font-size:9px;padding:1px 4px;border-radius:3px;background:${hasEmail ? '#10b98120' : '#ef444420'};color:${hasEmail ? '#10b981' : '#ef4444'}">${hasEmail ? '✉️' : '—'}</span>
    </div>`;
    parts.push(indicators);

    if (l.ceo_prenom) {
        const srcIcon = { api_gouv: '🏛', groq: '🤖', ollama: '💻' }[l.ceo_source] || '';
        parts.push(`<span style="font-size:11px;font-weight:600">${srcIcon} ${_ulEsc(l.ceo_prenom)} ${_ulEsc(l.ceo_nom)}</span>`);
    }
    const email = (l.email_valide && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(l.email_valide)) ? l.email_valide : l.email;
    if (email) {
        const validated = !!l.email_valide;
        parts.push(`<a href="mailto:${_ulEsc(email)}" style="font-size:10px;color:var(--accent);text-decoration:none">${validated ? '✓ ' : ''}${_ulEsc(email)}</a>`);
    }
    return parts.join('');
}

function _ulScoreCell(l) {
    if (l.score_mobile && l.score_mobile > 0) {
        const c = l.score_mobile >= 70 ? '#10b981' : l.score_mobile >= 50 ? '#f59e0b' : '#ef4444';
        return `<span style="font-weight:700;color:${c}">${l.score_mobile}<span style="font-size:10px;color:var(--ink3)">/100</span></span>`;
    }
    if (l.audit_partial) {
        return '<span style="color:var(--ink3);font-size:11px" title="Mesure de performance bloquée par le site">Indisponible</span>';
    }
    if (l.rating && l.rating > 0) {
        return `<span style="font-size:12px">${parseFloat(l.rating).toFixed(1)} ⭐ <span style="color:var(--ink3);font-size:10px">${l.nb_avis || 0} avis</span></span>`;
    }
    return '<span style="color:var(--ink3)">—</span>';
}

// --- Détail prospect (file humaine) -----------------------------------------
const _LEVENT = {
    creation: ['📦', 'Création'], import: ['📥', 'Import'], note: ['📝', 'Note'],
    initial: ['✉️', 'Envoi initial'], relance_1: ['🔁', 'Relance 1'], relance_2: ['🔁', 'Relance 2'],
    relance_3: ['🔁', 'Relance 3'], status_change: ['🔄', 'Changement de statut'],
    reponse: ['💬', 'Réponse'], ndr: ['⚠️', 'NDR / mail en échec'], auto_reply: ['🤖', 'Réponse auto'],
    validation_requete: ['🧾', 'Validation envoyée'], desinscription: ['🚫', 'Désinscription'],
};
const _EVSTAT = {
    rdv_obtenu: 'ok', pas_interesse: 'ko', a_relancer_plus_tard: 'warn',
    ne_plus_contacter: 'ko', sans_reponse: 'warn',
};
function _ulEvLabel(t) {
    const meta = _LEVENT[t] || ['•', t];
    return `<b>${meta[0]}</b> ${meta[1]}`;
}
function _ulEvDate(ev) { return new Date((ev.created_at || '').replace(' ', 'T')).toLocaleString('fr-FR'); }
function _ulPayloadLine(ev) {
    const p = ev.payload || {};
    const bits = [];
    if (p.objet) bits.push(`<b>« ${esc(p.objet)} »</b>`);
    if (p.email) bits.push(esc(p.email));
    if (p.from) bits.push(esc(p.from));
    if (p.raison) bits.push(`<i>${esc(p.raison)}</i>`);
    if (p.champ && p.from_statut && p.to) bits.push(`${esc(p.from_statut)} → <b>${esc(p.to)}</b>`);
    if (p.nb_envoi != null) bits.push(`${p.nb_envoi}ᵉ envoi`);
    return bits.join(' · ');
}
function unifiedLeadsOpenDetail(id) {
    _ul.detailId = id;
    openModal('modal-ul-detail');
    const box = (sel('#ul-detail-title'));
    box.textContent = 'Chargement…';
    fetch(`/api/v2/leads/${id}`, { cache: 'no-store' })
        .then(r => r.json())
        .then(d => {
            if (!d.success) throw new Error(d.error || 'errcode');
            _ulDetailRender(d.lead);
        })
        .catch(e => {
            console.error('[unified_leads] detail', e);
            box.textContent = 'Erreur de chargement';
        });
}
function _ulDetailRender(l) {
    sel('#ul-detail-title').textContent = `${l.nom || ''}${l.prenom ? ' ' + l.prenom : ''}`.trim() || 'Prospect';
    sel('#ul-detail-sub').innerHTML =
        `<b>${esc(l.objectif_nom || '')}</b> · <span class="status-badge ${l.statut === 'rdv_obtenu' ? 'ok' : 'warn'}">${_ul.statutLabels[l.statut] || l.statut}</span>` +
        (l.entreprise ? ` · ${esc(l.entreprise)}` : '') + (l.ville ? ` · ${esc(l.ville)}` : '') +
        (l.email ? ` · <a href="mailto:${esc(l.email)}">${esc(l.email)}</a>` : '');
    const reply = (l.events || []).find(e => e.event_type === 'reponse');
    const box = sel('#ul-detail-reply');
    const p = reply ? reply.payload || {} : {};
    if (reply && (p.corps || p.snippet)) {
        box.style.display = '';
        sel('#ul-detail-reply-head').innerHTML =
            `${_ulEvDate(reply)} · de <b>${esc(p.from || (p.email || ''))}</b> · objet <b>« ${esc(p.objet || '(sans objet)')} »</b>`;
        sel('#ul-detail-reply-body').textContent = (p.corps || p.snippet || '').slice(0, 2000);
    } else {
        box.style.display = 'none';
    }
    const rows = (l.events || []).map(ev => {
        const meta = _EVSTAT[ev.payload && ev.payload.to] || '';
        return `<tr>
            <td style="width:210px;white-space:nowrap;color:var(--ink3)" class="sm2">${_ulEvDate(ev)}</td>
            <td style="white-space:nowrap">${_ulEvLabel(ev.event_type)}${meta ? ` <span class="status-badge ${meta}">${_ul.statutLabels[ev.payload.to] || ev.payload.to}</span>` : ''}</td>
            <td style="color:var(--ink2)" class="sm2">${_ulPayloadLine(ev)}</td></tr>`;
    }).join('');
    sel('#ul-detail-timeline').innerHTML = rows
        ? `<table class="tbl"><tbody>${rows}</tbody></table>`
        : '<div style="font-size:12px;color:var(--ink3)">Aucun événement.</div>';
}
// ---------------------------------------------------------------------------
function _ulActions(l) {
    const b = [];
    b.push(`<button class="btn bg1 sm" onclick="unifiedLeadsOpenDetail(${l.id})" style="font-size:11px;padding:3px 8px" title="Détail & historique">👁</button>`);
    b.push(`<button class="btn bg1 sm" onclick="unifiedLeadsOpenEdit(${l.id})" style="font-size:11px;padding:3px 8px">✏️</button>`);
    const quick = _ulStatutQuick(l);
    if (quick) b.push(quick);
    if (l.pipeline === 'sniper' && l.statut_prospection === 'repondu' && l.audit_id)
        b.push(`<button class="btn accent sm" onclick="sniperSendStep2(${l.audit_id})" style="font-size:11px;padding:3px 9px">Step 2</button>`);
    if (l.lien_rapport)
        b.push(`<a href="${_ulEsc(l.lien_rapport)}" target="_blank" class="btn bg2 sm" style="font-size:11px;padding:3px 8px">Rapport</a>`);
    if (l.pipeline === 'maps') {
        const canAudit = !l.audit_id || l.statut === 'en_attente' || l.statut === 'scrape';
        b.push(`<button class="btn bg1 sm" onclick="auditLead(${l.id})" style="font-size:11px;padding:3px 9px">${canAudit ? 'Auditer' : '🔄'}</button>`);
    }
    b.push(`<button class="btn ${l.ecarte ? 'accent' : 'bg2'} sm" onclick="ulToggleEcarte(${l.id})" title="${l.ecarte ? 'Réintégrer' : "Écarter des flux d'envoi"}" style="font-size:11px;padding:3px 8px">${l.ecarte ? '↩' : '🚫'}</button>`);
    b.push(`<button class="btn bg2 sm" onclick="ulToggleDesinscrit(${l.id})" title="${l.desinscrit ? 'Réactiver' : 'Désinscrire (opposition)'}" style="font-size:11px;padding:3px 8px">${l.desinscrit ? '✓' : '✋'}</button>`);
    return b.join(' ');
}

// ─── Modal édition ──────────────────────────────────────────────────────────

function _ulPopulateEditForm(l) {
    _ul.editingId = l.id;
    const v2 = !!_ul.v2ObjectifId;
    _ulSetVal('ul-edit-id', l.id);
    _ulSetVal('ul-edit-nom', l.nom);
    if (v2) {
        _ulSetVal('ul-edit-email', l.email);
        _ulSetVal('ul-edit-email-2', '');
        _ulSetVal('ul-edit-tel', l.telephone);
        _ulSetVal('ul-edit-tel-2', '');
        _ulSetVal('ul-edit-site', l.site_web);
        _ulSetVal('ul-edit-category', l.secteur);
        _ulSetVal('ul-edit-ville', l.ville);
        _ulSetVal('ul-edit-notes', '');
        _ulSetVal('ul-edit-ceo-prenom', l.prenom);
        _ulSetVal('ul-edit-ceo-nom', '');
        const ceoRow = document.getElementById('ul-edit-ceo-row');
        if (ceoRow) ceoRow.style.display = l.prenom ? '' : 'none';
        const lbl = document.getElementById('ul-edit-pipeline-label');
        if (lbl) lbl.textContent = `Objectif · ${l.objectif_nom || _ul.v2ObjectifNom || '—'}`;
    } else {
        _ulSetVal('ul-edit-email', l.email);
        _ulSetVal('ul-edit-email-2', l.email_2);
        _ulSetVal('ul-edit-tel', l.telephone);
        _ulSetVal('ul-edit-tel-2', l.telephone_2);
        _ulSetVal('ul-edit-site', l.site_web);
        _ulSetVal('ul-edit-category', l.category);
        _ulSetVal('ul-edit-ville', l.ville);
        _ulSetVal('ul-edit-notes', l.notes);
        _ulSetVal('ul-edit-ceo-prenom', l.ceo_prenom);
        _ulSetVal('ul-edit-ceo-nom', l.ceo_nom);
        const ceoRow = document.getElementById('ul-edit-ceo-row');
        if (ceoRow) ceoRow.style.display = (l.pipeline === 'sniper' || l.ceo_prenom) ? '' : 'none';
        const lbl = document.getElementById('ul-edit-pipeline-label');
        if (lbl) lbl.textContent = l.pipeline === 'sniper' ? `Sniper — ${_ulSourceLabel(l.source)}` : 'Maps';
    }

    // S'assurer que le modal n'est pas piégé dans un parent display:none
    // (ex: vue Listes ouvre ce modal qui vit dans #subtab-leads caché)
    const _ulEditModal = document.getElementById('modal-ul-edit');
    if (_ulEditModal && _ulEditModal.parentElement !== document.body) {
        const parentStyle = window.getComputedStyle(_ulEditModal.parentElement).display;
        if (parentStyle === 'none') {
            document.body.appendChild(_ulEditModal);
        }
    }
    openModal('modal-ul-edit');
}

async function unifiedLeadsOpenEdit(id, fallbackCache) {
    console.log('[UL EDIT] Opening edit for lead', id);
    let l = _ul.leads.find(x => x.id == id);
    if (l) {
        console.log('[UL EDIT] Found in _ul.leads cache');
    } else if (fallbackCache) {
        l = fallbackCache.find(x => x.id == id);
        if (l) console.log('[UL EDIT] Found in fallbackCache');
    }
    if (!l) {
        console.log('[UL EDIT] Not in cache, fetching from API...');
        try {
            const url = _ul.v2ObjectifId ? `/api/v2/leads/${id}` : `/api/leads/${id}`;
            const r = await fetch(url, { cache: 'no-store' });
            console.log('[UL EDIT] API response:', r.status, r.ok);
            if (r.ok) {
                const d = await r.json();
                l = d.lead || d;
                console.log('[UL EDIT] Lead from API:', l?.id, l?.nom);
            }
        } catch (e) {
            console.error('[UL EDIT] API fetch error:', e);
        }
    }
    if (!l || l.error) { showToast?.('Lead non trouvé.', 'error'); return false; }
    console.log('[UL EDIT] Calling _ulPopulateEditForm for', l.id, l.nom);
    _ulPopulateEditForm(l);
}

async function unifiedLeadsSave() {
    const id = _ul.editingId; if (!id) return;
    if (_ul.v2ObjectifId) {
        const data = {
            nom: _ulGetVal('ul-edit-nom'),
            prenom: _ulGetVal('ul-edit-ceo-prenom'),
            email: _ulGetVal('ul-edit-email'),
            telephone: _ulGetVal('ul-edit-tel'),
            site_web: _ulGetVal('ul-edit-site'),
            secteur: _ulGetVal('ul-edit-category'),
            ville: _ulGetVal('ul-edit-ville'),
        };
        try {
            const r = await fetch(`/api/v2/leads/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
            const d = await r.json();
            if (!d.success) { showToast?.('Erreur : ' + (d.error || 'inconnue'), 'error'); return; }
            closeModal?.('modal-ul-edit');
            showToast?.('Lead mis à jour', 'success');
            unifiedLeadsLoad(_ul.page);
        } catch (e) { console.error('[unified_leads] save v2', e); }
        return;
    }
    const data = {
        nom: _ulGetVal('ul-edit-nom'),
        email: _ulGetVal('ul-edit-email'),
        email_2: _ulGetVal('ul-edit-email-2'),
        telephone: _ulGetVal('ul-edit-tel'),
        telephone_2: _ulGetVal('ul-edit-tel-2'),
        site_web: _ulGetVal('ul-edit-site'),
        category: _ulGetVal('ul-edit-category'),
        ville: _ulGetVal('ul-edit-ville'),
        notes: _ulGetVal('ul-edit-notes'),
        ceo_prenom: _ulGetVal('ul-edit-ceo-prenom'),
        ceo_nom: _ulGetVal('ul-edit-ceo-nom'),
    };
    try {
        const r = await fetch(`/api/leads/${id}/edit`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
        const d = await r.json();
        if (!d.success) { showToast?.('Erreur : ' + (d.error || 'inconnue'), 'error'); return; }
        closeModal?.('modal-ul-edit');
        showToast?.('Lead mis à jour', 'success');
        if (typeof triggerGlobalLeadRefresh === 'function') {
            triggerGlobalLeadRefresh(id);
        } else {
            unifiedLeadsLoad(_ul.page);
        }
        // Rafraîchir le panneau latéral s'il est ouvert sur ce lead (DetailsModule)
        if (typeof window.DetailsModule !== 'undefined' && window.DetailsModule.currentLead && window.DetailsModule.currentLead.id === id) {
            window.DetailsModule.openLead(id);
        }
        // Rafraîchir le panneau latéral s'il est ouvert sur ce lead (dashboard_core.js)
        if (typeof openLeadPanel === 'function' && typeof _selectedLeadId !== 'undefined' && _selectedLeadId === id) {
            const currentTab = document.querySelector('.side-panel-tab.active')?.dataset?.tab || 'audit';
            openLeadPanel(id, currentTab);
        }
    } catch (e) { console.error('[unified_leads] save', e); }
}

async function unifiedLeadsDelete() {
    const id = _ul.editingId; if (!id) return;
    const nom = _ul.leads.find(x => x.id === id)?.nom || `#${id}`;
    const ok = typeof window.UI !== 'undefined'
        ? await window.UI.confirm(`Supprimer "${nom}" ?`, { danger: true })
        : typeof showConfirm === 'function'
            ? await showConfirm(`Supprimer "${nom}" ?`, { title: 'Supprimer', confirmText: 'Supprimer', danger: true })
            : confirm(`Supprimer "${nom}" ?`);
    if (!ok) return;
    try {
        if (_ul.v2ObjectifId) {
            await fetch(`/api/v2/leads/${id}`, { method: 'DELETE' });
            closeModal?.('modal-ul-edit'); showToast?.('Lead supprimé', 'success');
            unifiedLeadsLoad(_ul.page);
            if (typeof window.ObjectifsModule !== 'undefined') window.ObjectifsModule.refreshStats();
            return;
        }
        await fetch(`/api/lead/delete?id=${id}`, { method: 'DELETE' });
        closeModal?.('modal-ul-edit'); showToast?.('Lead supprimé', 'success');
        if (typeof triggerGlobalLeadRefresh === 'function') {
            triggerGlobalLeadRefresh(id);
        } else {
            unifiedLeadsLoad(_ul.page);
        }
    } catch (e) { console.error('[unified_leads] delete', e); }
}

// ─── Sélection / pagination ──────────────────────────────────────────────────

function ulToggleAll(cb) { document.querySelectorAll('.ul-cb').forEach(c => c.checked = cb.checked); }
function ulGetSelectedIds() { return [...document.querySelectorAll('.ul-cb:checked')].map(c => parseInt(c.dataset.id)).filter(Boolean); }

async function ulDeleteSelected() {
    const ids = ulGetSelectedIds();
    if (!ids.length) { showToast?.('Sélectionner au moins un lead', 'error'); return; }
    const ok = typeof window.UI !== 'undefined'
        ? await window.UI.confirm(`Supprimer ${ids.length} lead(s) ?`, { danger: true })
        : typeof showConfirm === 'function'
            ? await showConfirm(`Supprimer ${ids.length} lead(s) ?`, { title: 'Suppression', confirmText: 'Supprimer', danger: true })
            : confirm(`Supprimer ${ids.length} lead(s) ?`);
    if (!ok) return;
    try {
        if (_ul.v2ObjectifId) {
            await Promise.all(ids.map(id => fetch(`/api/v2/leads/${id}`, { method: 'DELETE' })));
            showToast?.(`${ids.length} lead(s) supprimé(s)`, 'success');
            unifiedLeadsLoad(_ul.page);
            if (typeof window.ObjectifsModule !== 'undefined') window.ObjectifsModule.refreshStats();
            return;
        }
        await fetch('/api/leads/batch-delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids }) });
        showToast?.(`${ids.length} lead(s) supprimé(s)`, 'success');
        unifiedLeadsLoad(_ul.page);
    } catch (e) { console.error('[unified_leads] batch-delete', e); }
}

function _ulUpdatePagination() {
    const p = document.getElementById('ul-prev'), n = document.getElementById('ul-next'), i = document.getElementById('ul-page-info');
    if (p) p.disabled = _ul.page <= 1;
    if (n) n.disabled = _ul.page >= _ul.totalPages;
    if (i) i.textContent = `page ${_ul.page} / ${_ul.totalPages}`;
}
function _ulUpdateCount() { const el = document.getElementById('ul-count'); if (el) el.textContent = `${_ul.total} lead${_ul.total > 1 ? 's' : ''}`; }
function ulChangePage(delta) { const p = Math.max(1, Math.min(_ul.totalPages, _ul.page + delta)); if (p !== _ul.page) unifiedLeadsLoad(p); }

// ─── Badges / helpers ────────────────────────────────────────────────────────

const _SOURCE_MAP = {
    maps: ['#6b7280', 'Maps'], ads: ['#f97316', 'Ads'], fb_ads: ['#1877f2', 'FB Ads'],
    tech: ['#8b5cf6', 'Tech'], ecom: ['#8b5cf6', 'E-com'], jobs: ['#06b6d4', 'Jobs'], bodacc: ['#10b981', 'BODACC'],
};
function _ulSourceBadge(s) {
    const [c, l] = _SOURCE_MAP[s] || ['#9ca3af', s || '?'];
    return `<span style="background:${c}20;color:${c};padding:2px 7px;border-radius:10px;font-size:10px;font-weight:700">${l}</span>`;
}
function _ulSourceLabel(s) { return (_SOURCE_MAP[s] || ['', '?'])[1]; }
function _ulStatutBadge(d) {
    if (!d) return '<span style="color:var(--ink3)">—</span>';
    return `<span style="background:${d.color}20;color:${d.color};padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600">${d.label}</span>`;
}
function _ulEsc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function _ulSetVal(id, v) { const el = document.getElementById(id); if (el) el.value = v ?? ''; }
function _ulGetVal(id) { return document.getElementById(id)?.value?.trim() ?? ''; }

// ─── KANBAN (Phase 4.1) ──────────────────────────────────────────────────────

function setLeadsView(view) {
    if (view === 'kanban' && _ul.v2ObjectifId) {
        showToast?.('Le Kanban reste disponible en vue « Archive ». Les objectifs utilisent la vue Liste.', 'error');
        return;
    }
    _ul.view = view;
    document.getElementById('leads-list-view').style.display = view === 'list' ? '' : 'none';
    document.getElementById('leads-kanban-view').style.display = view === 'kanban' ? '' : 'none';

    document.getElementById('view-list').classList.toggle('active', view === 'list');
    document.getElementById('view-kanban').classList.toggle('active', view === 'kanban');

    if (view === 'kanban') renderKanban(_ul.leads);
    else unifiedLeadsLoad(_ul.page);
}

function ulToggleSection(section) {
    const el = document.getElementById(`ul-section-${section}`);
    const btn = event.currentTarget;
    if (!el) return;
    const isOpen = el.classList.toggle('open');
    btn.classList.toggle('active', isOpen);
    const arrow = btn.querySelector('.leads-collapse-arrow');
    if (arrow) arrow.textContent = isOpen ? '▴' : '▾';
}

function renderKanban(leads) {
    const columns = ['en_attente', 'audite', 'email_genere', 'envoye', 'repondu'];
    const containers = {};
    columns.forEach(col => {
        const el = document.getElementById(`cards-${col}`);
        if (el) {
            el.innerHTML = '';
            containers[col] = el;
        }
    });

    const counts = { en_attente: 0, audite: 0, email_genere: 0, envoye: 0, repondu: 0 };

    leads.forEach(l => {
        const targetCol = columns.includes(l.kanban_status) ? l.kanban_status : 'en_attente';
        if (containers[targetCol]) {
            containers[targetCol].innerHTML += _ulKanbanCard(l);
            counts[targetCol]++;
        }
    });

    columns.forEach(col => {
        const countEl = document.querySelector(`.kanban-col[data-status="${col}"] .kanban-col-count`);
        if (countEl) countEl.textContent = counts[col];
    });

    initKanbanSortable();
}

function _ulKanbanCard(l) {
    const score = l.score_performance || l.mobile_score || 0;
    const scoreClass = score >= 80 ? 'hot' : score >= 50 ? 'warm' : 'cold';
    const email = (l.email_valide && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(l.email_valide)) ? l.email_valide : (l.email || '—');

    return `
        <div class="kanban-card" data-id="${l.id}" onclick="openLeadPanel(${l.id})">
            <div class="kc-name">${_ulEsc(l.nom)}</div>
            <div class="kc-meta">${_ulEsc(l.ville)} · ${_ulEsc(l.category)}</div>
            <div style="font-size:11px;color:var(--ink2);margin-bottom:8px">${_ulEsc(email)}</div>
            <div class="kc-footer">
                <div class="kc-score ${scoreClass}">${score}%</div>
                <div style="font-size:10px;color:var(--ink3)">${_ulEsc(l.source)}</div>
            </div>
        </div>
    `;
}

function initKanbanSortable() {
    if (typeof Sortable === 'undefined') return;
    const columns = document.querySelectorAll('.kanban-cards');
    columns.forEach(el => {
        Sortable.create(el, {
            group: 'kanban',
            animation: 150,
            ghostClass: 'sortable-ghost',
            dragClass: 'sortable-drag',
            onEnd: async function (evt) {
                const leadId = evt.item.dataset.id;
                const newStatus = evt.to.id.replace('cards-', '');
                if (evt.from === evt.to) return;

                try {
                    const r = await fetch(`/api/leads/${leadId}/status`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ status: newStatus })
                    });
                    const d = await r.json();
                    if (d.success) {
                        showToast?.('Statut mis à jour', 'success');
                        // Update local data
                        const lead = _ul.leads.find(x => x.id == leadId);
                        if (lead) {
                            lead.statut = newStatus;
                            lead.statut_prospection = newStatus;
                        }
                        // Refresh counts
                        _ulUpdateKanbanCounts();
                    } else {
                        showToast?.('Erreur lors de la mise à jour', 'error');
                        unifiedLeadsLoad(_ul.page);
                    }
                } catch (e) {
                    console.error('[Kanban Drop]', e);
                    showToast?.('Erreur réseau', 'error');
                }
            }
        });
    });
}

function _ulUpdateKanbanCounts() {
    const columns = ['en_attente', 'audite', 'email_genere', 'envoye', 'repondu'];
    columns.forEach(col => {
        const count = document.getElementById(`cards-${col}`).children.length;
        const countEl = document.querySelector(`.kanban-col[data-status="${col}"] .kanban-col-count`);
        if (countEl) countEl.textContent = count;
    });
}

