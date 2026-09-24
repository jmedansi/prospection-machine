/**
 * dashboard/static/js/modules/unified_leads.js
 * Table unifiée Maps + Sniper.
 */

const _ul = { leads: [], page: 1, totalPages: 1, total: 0, editingId: null, view: 'list', v2CampagneId: null, v2CampagneNom: '' };
// Exposer l'état sur window : campagnes.js et le sélecteur global (header) s'appuient dessus.
// Aliases dépréciés v2ObjectifId/v2ObjectifNom → v2CampagneId/v2CampagneNom (compat lecteurs legacy).
Object.defineProperty(_ul, 'v2ObjectifId', {
    get() { return _ul.v2CampagneId; },
    set(v) { _ul.v2CampagneId = v; },
    enumerable: true,
});
Object.defineProperty(_ul, 'v2ObjectifNom', {
    get() { return _ul.v2CampagneNom; },
    set(v) { _ul.v2CampagneNom = v; },
    enumerable: true,
});
window._ul = _ul;

// Helper sélecteur utilisé par ce module (notamment le modal détail #ul-detail-*).
// Exposé en global : aucun autre module V6/V5 ne déclare de `sel` au niveau racine
// (campagnes.js, listes.js, suivi.js scopes le leur dans un IIFE).
function sel(s) { return document.querySelector(s); }

// Mode v2 : actif en V6 (toutes campagnes) comme quand une campagne est choisie.
// Les actions (éditer, écarter, désinscrire, statut) doivent alors viser les
// endpoints /api/v2/... ; les branches legacy restent pour la vue Archive (V5).
function _ulIsV2() {
    return !!(window.V6_MODE || _ul.v2CampagneId);
}

const _V2_STATUTS = [
    ['qualifie', 'Qualifié'], ['en_sequence', 'En séquence'], ['relance_1', 'Relance 1'],
    ['relance_2', 'Relance 2'], ['relance_3', 'Relance 3'], ['a_traiter_humain', 'À traiter (répondu)'],
    ['rdv_obtenu', 'RDV obtenu'], ['a_relancer_plus_tard', 'À relancer plus tard'],
    ['pas_interesse', 'Pas intéressé'], ['sans_reponse', 'Sans réponse'],
    ['ne_plus_contacter', 'Ne plus contacter'], ['adresse_invalide', 'Adresse invalide'],
];

function unifiedLeadsInit() {
    const boot = () => {
        if (typeof window.CampagnesModule !== 'undefined' && window.CampagnesModule.init) {
            window.CampagnesModule.init(); // charge la campagne mémorisée puis charge les leads
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
        const v2 = !!_ulIsV2();
        const url = v2
            ? `/api/v2/listes${_ul.v2CampagneId ? `?campagne_id=${_ul.v2CampagneId}` : ''}`
            : '/api/lists';
        const r = await fetch(url);
        const d = await r.json();
        const lists = d.listes || d.lists || [];
        
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
    const limit = _ulCurrentLimit();

    // Mode Campagne (v2) : la page n'affiche QUE les leads de la campagne choisie.
    if (_ul.v2CampagneId) return _ulV2Load(tbody, limit);
    // Mode « toutes campagnes » (V6) : leads v2 groupés par campagne.
    if (window.V6_MODE) return _ulV2AllLoad(tbody, limit);

    tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;padding:24px;color:var(--ink3)">Chargement…</td></tr>`;

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
            tbody.innerHTML = `<tr><td colspan="10" style="color:var(--error);text-align:center;padding:16px">${_ulEsc(d.error)}</td></tr>`;
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
                : `<tr><td colspan="10" style="text-align:center;padding:24px;color:var(--ink3)">Aucun lead</td></tr>`;
        }

        _ulUpdatePagination();
        _ulUpdateCount();
    } catch (e) {
        console.error('[unified_leads]', e);
        if (tbody) tbody.innerHTML = `<tr><td colspan="10" style="color:var(--error);text-align:center;padding:16px">Erreur : ${e.message}</td></tr>`;
    }
}

async function _ulV2Load(tbody, limit) {
    const params = new URLSearchParams(_ulV2Params());
    try {
        const r = await fetch(`/api/v2/campagnes/${_ul.v2CampagneId}/leads?${params}`);
        const d = await r.json();
        if (d.error) {
            tbody.innerHTML = `<tr><td colspan="10" style="color:var(--error);text-align:center;padding:16px">${_ulEsc(d.error)}</td></tr>`;
            return;
        }
        _ul.leads = d.leads || [];
        _ul.page = d.page;
        _ul.totalPages = d.total_pages;
        _ul.total = d.total;
        if (typeof _campaignData !== 'undefined') _campaignData = _ul.leads;
        if (_ul.view === 'kanban') {
            _ulRenderBoardV2();
        } else {
            tbody.innerHTML = _ul.leads.length
                ? _ul.leads.map(_ulRow).join('')
                : `<tr><td colspan="10" style="text-align:center;padding:24px;color:var(--ink3)">
                    Aucun lead dans cet objectif — cliquez sur « Importer CSV » pour en ajouter.</td></tr>`;
        }
        _ulUpdatePagination();
        _ulUpdateCount();
    } catch (e) {
        console.error('[unified_leads v2]', e);
        if (tbody) tbody.innerHTML = `<tr><td colspan="10" style="color:var(--error);text-align:center;padding:16px">Erreur : ${e.message}</td></tr>`;
    }
}

// Mode « toutes campagnes » v2 : les prospects de toutes les campagnes, groupés
// en sections par campagne (chaque ligne porte campagne_id / campagne_nom / liste_id).
async function _ulV2AllLoad(tbody, limit) {
    const params = new URLSearchParams(_ulV2Params());
    try {
        const r = await fetch(`/api/v2/leads?${params}`);
        const d = await r.json();
        if (d.error) {
            tbody.innerHTML = `<tr><td colspan="10" style="color:var(--error);text-align:center;padding:16px">${_ulEsc(d.error)}</td></tr>`;
            return;
        }
        _ul.leads = d.leads || [];
        _ul.page = d.page;
        _ul.totalPages = d.total_pages;
        _ul.total = d.total;
        if (_ul.view === 'kanban') {
            _ulRenderBoardV2();
        } else {
            tbody.innerHTML = _ul.leads.length
                ? _ulRenderByCampagne()
                : `<tr><td colspan="10" style="text-align:center;padding:24px;color:var(--ink3)">
                    Aucun prospect — sélectionnez une campagne ou importez des leads.</td></tr>`;
        }
        _ulUpdatePagination();
        _ulUpdateCount();
    } catch (e) {
        console.error('[unified_leads v2 all]', e);
        if (tbody) tbody.innerHTML = `<tr><td colspan="10" style="color:var(--error);text-align:center;padding:16px">Erreur : ${e.message}</td></tr>`;
    }
}

function _ulRenderByCampagne() {
    const grp = new Map();
    for (const l of _ul.leads) {
        const cid = l.campagne_id ?? 0;
        if (!grp.has(cid)) grp.set(cid, { nom: l.campagne_nom || 'Campagne', leads: [] });
        grp.get(cid).leads.push(l);
    }
    let html = '';
    for (const [cid, g] of grp) {
        html += `<tr class="ul-campagne-section" style="background:rgba(var(--brand-rgb,96,165,250),0.06)">
            <td colspan="10" style="padding:8px 12px;border-top:1px solid var(--border)">
                <span style="font-weight:700;font-size:12px;letter-spacing:.02em;color:var(--ink)">
                    <span style="margin-right:6px;color:var(--ink3)">▸</span>${_ulEsc(g.nom)}
                </span>
                <span style="font-size:11px;color:var(--ink3);margin-left:8px">${g.leads.length} affiché${g.leads.length > 1 ? 's' : ''}</span>
            </td>
        </tr>`;
        html += g.leads.map(_ulRow).join('');
    }
    return html;
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
    _ulSetFiltersV2(!!v2mode);
}

// Options v2 du filtre « Source » (colonnes réelles de prospects.source).
const _V2_SOURCES = [
    ['legacy_maps', '🗺️ Maps (legacy)'], ['legacy_sniper', '🔫 Sniper (legacy)'],
    ['legacy_ecoles', '🎓 Écoles (legacy)'], ['scraping', 'Scraping'],
    ['csv', 'CSV'], ['json', 'JSON'], ['manuel', 'Manuel'], ['ia', 'IA'],
];

// Adapter le panneau Filtres au mode v2 : les selects legacy (source/notes/tag)
// n'ont pas de sémantique v2 — on les bascule sur les équivalents réels, sauf
// « tag » qui n'a aucun équivalent v2 (masqué). Le select « liste » est
// repopulé via les endpoints v2. En mode archive (legacy), tout est restauré.
function _ulSetFiltersV2(v2mode) {
    const v2 = !!(v2mode && (window.V6_MODE || _ul.v2CampagneId));
    const _swap = (id, opts, legacyKey) => {
        const el = document.getElementById(id);
        if (!el) return;
        if (v2) {
            if (!_ul[legacyKey]) _ul[legacyKey] = el.innerHTML;
            el.innerHTML = '<option value="">Tous</option>' +
                opts.map(([v, l]) => `<option value="${v}">${l}</option>`).join('');
        } else if (_ul[legacyKey]) {
            el.innerHTML = _ul[legacyKey];
        }
    };
    const _hideTag = document.getElementById('ul-filter-tag');
    if (v2) {
        _swap('ul-filter-source', _V2_SOURCES, '_legacySourceOptions');
        _swap('ul-filter-notes', [['with', 'Avec note'], ['sans', 'Sans note']], '_legacyNotesOptions');
        const flagged = document.getElementById('ul-filter-flagged');
        if (flagged) {
            if (!_ul._legacyFlaggedOptions) _ul._legacyFlaggedOptions = flagged.innerHTML;
            flagged.innerHTML =
                '<option value="" selected>Tous (y c. écartés/désin.)</option>' +
                '<option value="0">Masquer écartés/désin.</option>' +
                '<option value="1">Uniquement écartés/désin.</option>';
        }
        if (_hideTag) _hideTag.style.display = 'none';
        if (typeof window.unifiedLeadsLoadLists === 'function') window.unifiedLeadsLoadLists();
    } else {
        if (_ul._legacySourceOptions) _ulSetFilterHTML('ul-filter-source', _ul._legacySourceOptions);
        if (_ul._legacyNotesOptions) _ulSetFilterHTML('ul-filter-notes', _ul._legacyNotesOptions);
        if (_ul._legacyFlaggedOptions) _ulSetFilterHTML('ul-filter-flagged', _ul._legacyFlaggedOptions);
        if (_hideTag) _hideTag.style.display = '';
        if (typeof window.unifiedLeadsLoadLists === 'function') window.unifiedLeadsLoadLists();
    }
}

function _ulSetFilterHTML(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
}

// Limite de page : 10000 en Kanban v2 (board complet), sinon la valeur du select.
function _ulCurrentLimit() {
    if (_ul.view === 'kanban' && _ulIsV2()) return 10000;
    return parseInt(document.getElementById('ul-filter-limit')?.value || '50', 10) || 50;
}

// Paramètres de filtre v2 (miroir des selects du panneau Filtres).
function _ulV2Params() {
    const p = { page: _ul.page, limit: _ulCurrentLimit() };
    const v = (id) => document.getElementById(id)?.value || '';
    const search = document.getElementById('ul-search')?.value?.trim() || '';
    if (search) p.search = search;
    const statut = v('ul-filter-statut');
    if (statut) p.statut = statut;
    const source = v('ul-filter-source');
    if (source) p.source = source;
    const secteur = v('ul-filter-sector');
    if (secteur) p.secteur = secteur;
    const site = v('ul-filter-site');
    if (site === 'with' || site === 'without') p.site = site;
    const email = v('ul-filter-email');
    if (email === 'with' || email === 'without') p.email = email;
    const notes = v('ul-filter-notes');
    if (notes === 'with' || notes === 'sans') p.notes = notes;
    const score = v('ul-filter-score');
    if (score) p.score = score;
    const objectif = v('ul-filter-objectif');
    if (objectif && objectif !== 'tous') p.objectif_liste = objectif;
    const listId = v('ul-filter-list');
    if (listId) p.liste_id = listId;
    const flagged = v('ul-filter-flagged');
    if (flagged === '0') { p.ecarte = '0'; p.desinscrit = '0'; }
    else if (flagged === '1') { p.ecarte = '1'; p.desinscrit = '1'; }
    return p;
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
    if (!_ul.transitions || !_ulIsV2()) return '';
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
    const ok = window.confirm(`Passer « ${l?.nom || id} » → ${(_ul.statutLabels || {})[statut] || statut} ?`);
    if (!ok) return;
    try {
        const r = await fetch(`/api/v2/leads/${id}/statut`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ statut, reason: 'file humaine (UI)' }),
        });
        const d = await r.json();
        if (!d.success) { showToast?.('Erreur : ' + (d.error || 'transition refusée'), 'error'); return; }
        showToast?.(`${l?.nom || 'Prospect'} → ${(_ul.statutLabels || {})[statut] || statut}`, 'success');
        unifiedLeadsLoad(_ul.page);
        if (window.ListesModule && typeof window.ListesModule.onProspectsChanged === 'function') {
            window.ListesModule.onProspectsChanged();
        }
    } catch (e) {
        console.error('[unified_leads] changeStatut', e);
        showToast?.('Erreur réseau', 'error');
    }
}

function _ulRow(l) {
    const nom = _ulEsc(l.nom || '—');
    const initial = nom.charAt(0).toUpperCase();
    const siteUrl = _ulEsc(l.site_web || '');

    const nomCell = siteUrl
        ? `<a href="${siteUrl}" target="_blank" class="lead-name" style="color:var(--ink1);text-decoration:none">${nom}</a>`
        : `<strong class="lead-name">${nom}</strong>`;

    // Objectif (web/général) + secteur dans la meta ; la ville vit dans sa colonne dédiée.
    const secteur = _ulEsc(l.secteur || l.category || l.categorie || '');
    const meta = `${_ulSourceBadge(l.source)}${_ulObjectifChip(l)}${secteur ? ' ' + secteur : ''}`;

    // Exclusions (écarté / désinscrit) : pastilles « hors flux », PAS des statuts du cycle de vie.
    const flags = [];
    if (l.ecarte) flags.push('<span class="ul-xp" title="Exclu des flux d\'envoi">⛔ écarté</span>');
    if (l.desinscrit) flags.push('<span class="ul-xp ul-xp-opp" title="Opposition / désinscrit">✋ désinscrit</span>');

    const av = _ulAvatarColor(l.nom || '');
    const rowClick = `openLeadPanel(${l.id})`;
    return `<tr onclick="${rowClick}" style="cursor:pointer" class="${window._selectedLeadId === l.id ? 'selected' : ''}${(l.ecarte || l.desinscrit) ? ' ul-flagged' : ''}">
        <td class="col-check" onclick="event && event.stopPropagation()">
            <input type="checkbox" class="ul-cb lead-cb" data-id="${l.id}" data-nom="${_ulEsc(l.nom)}">
        </td>
        <td class="col-id">${l.id}</td>
        <td class="col-prospect">
            <div class="lead-cell-flex">
                <div class="lead-avatar" style="background:${av.bg};color:${av.fg}">${initial}</div>
                <div class="lead-info">
                    ${nomCell}
                    <div class="lead-meta">${meta}${flags.length ? ' ' + flags.join(' ') : ''}</div>
                </div>
            </div>
        </td>
        <td class="col-source">${_ulEsc(l.ville || '')}</td>
        <td class="col-contact">${_ulContactCell(l)}</td>
        <td class="col-objectif">${_ulObjectifBadge(l)}</td>
        <td class="col-score">${_ulScoreCell(l)}</td>
        <td class="col-avis">${_ulAvisCell(l)}</td>
        <td class="col-statut">${_ulStatutBadge(l.statut_display)}</td>
        <td class="col-actions" onclick="event && event.stopPropagation()">${_ulActions(l)}</td>
    </tr>`;
}

// Couleur déterministe pour l'avatar du prospect (fonction du nom).
function _ulAvatarColor(name) {
    let h = 0;
    const s = String(name || '');
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    const hue = h % 360;
    const sat = 38 + (h % 3) * 14;      // 38 → 66 %
    const lum = 58 + (h % 4) * 5;       // 58 → 73 %
    const bg = `hsl(${hue} ${sat}% ${lum}%)`;
    const fg = `hsl(${hue} ${sat}% ${Math.max(8, lum - 48)}%)`;
    return { bg, fg };
}

// Badge Objectif (web / général) — classement de la liste porteuse (source de vérité).
function _ulObjectifChip(l) {
    const o = l.objectif || ((l.campagne_id) ? 'general' : (l.objectif || 'general'));
    const isWeb = o === 'web';
    const title = isWeb ? 'Objectif Sites Web — qualification + maquette IA' : 'Objectif Général — pas de qualification web ni de maquette';
    return `<span class="ul-objchip ${isWeb ? 'web' : 'gen'}" title="${title}">${isWeb ? 'Web' : 'Gén.'}</span>`;
}

// Nombre d'avis Google (colonne dédiée).
function _ulAvisCell(l) {
    const r = parseFloat(l.rating) || 0;
    const n = parseInt(l.nb_avis) || 0;
    if (!r && !n) return '<span class="avis-num">—</span>';
    const star = r ? `<span class="avis-val">${r.toFixed(1)} ⭐</span>` : '';
    const count = n ? `<span class="avis-num">(${n})</span>` : '';
    return `<span class="avis-cell" title="Note Google">${star} ${count}</span>`;
}

function _ulObjectifBadge(l) {
    if (_ulIsV2()) {
        const nom = _ul.v2CampagneNom || l.campagne_nom || 'Campagne';
        return `<span style="background:#10b98120;color:#10b981;border:1px solid #10b98140;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700">${_ulEsc(nom)}</span>`;
    }
    const isWeb = (l.objectif || 'general') === 'web';
    const color = isWeb ? '#10b981' : '#3b82f6';
    const label = isWeb ? 'Web' : 'Gén.';
    const title = isWeb ? 'Objectif Sites Web — cliquer pour basculer en Général' : 'Objectif Général (ni qualification web ni maquette) — cliquer pour basculer en Sites Web';
    return `<button class="ul-obj-badge" data-id="${l.id}" title="${title}" onclick="event.stopPropagation(); ulToggleObjectif(${l.id})" style="background:${color}20;color:${color};border:1px solid ${color}40;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700;cursor:pointer">${label}</button>`;
}

async function ulToggleObjectif(leadId) {
    if (_ulIsV2()) return; // classement Web/Général réservé à la vue Archive
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
        const url = _ulIsV2() ? `/api/v2/leads/${leadId}/ecarter` : `/api/leads/${leadId}/ecarter`;
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
        const url = _ulIsV2() ? `/api/v2/leads/${leadId}/desinscrire` : `/api/leads/${leadId}/desinscrire`;
        const body = _ulIsV2() ? { ne_plus_contacter: next } : { desinscrit: next };
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
    if (_ulIsV2()) { showToast?.('Le classement Web ⇄ Général ne concerne pas les objectifs', 'error'); return; }
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
    const v2mode = !!_ulIsV2();
    const objWrap = document.getElementById('ul-import-objectif-wrap');
    const objBadge = document.getElementById('ul-import-objectif-badge');
    if (objWrap) objWrap.style.display = v2mode ? 'none' : '';
    if (objBadge) {
        objBadge.style.display = v2mode ? '' : 'none';
        objBadge.textContent = v2mode ? `Import dans la campagne « ${_ul.v2CampagneNom || _ul.v2CampagneId} »` : '';
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
if (_ulIsV2()) {
            if (!_ul.v2CampagneId) { showToast?.("Sélectionnez une campagne avant d'importer", 'error'); return; }
            // Mode Campagne : import DANS la campagne active (endpoint v2)
            const r = await fetch(`/api/v2/campagnes/${_ul.v2CampagneId}/leads/import`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rows, source: 'import' })
            });
            const d = await r.json();
            if (!r.ok || d.error) throw new Error(d.error || 'Erreur import');
            if (log) log.textContent = `✓ ${d.importes} importé(s), ${d.doublons} doublon(s), ${d.supprimes} désinscrit(s), ${d.errors} erreur(s).`;
            showToast?.(`${d.importes} lead(s) importés dans la campagne`, 'success');
            unifiedLeadsLoad(_ul.page);
            window.CampagnesModule?.refreshStats();
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

    parts.push(`<div class="contact-ind">
        <span class="ul-ind ${hasSite ? 'has' : 'miss'}" title="Site web">${hasSite ? '🌐' : '—'}</span>
        <span class="ul-ind ${hasEmail ? 'has' : 'miss'}" title="Email">${hasEmail ? '✉️' : '—'}</span>
    </div>`);

    if (l.ceo_prenom) {
        const srcIcon = { api_gouv: '🏛', groq: '🤖', ollama: '💻' }[l.ceo_source] || '';
        parts.push(`<span class="contact-ceo">${srcIcon} ${_ulEsc(l.ceo_prenom)} ${_ulEsc(l.ceo_nom)}</span>`);
    }
    const email = (l.email_valide && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(l.email_valide)) ? l.email_valide : l.email;
    if (email) {
        const validated = !!l.email_valide;
        parts.push(`<a href="mailto:${_ulEsc(email)}" class="contact-mail">${validated ? '✓ ' : ''}${_ulEsc(email)}</a>`);
    }
    return parts.join('');
}

function _ulVerdictChip(reco) {
    // Verdict proposé par la qualification IA (Reco) : a_contacter / a_verifier / a_ecarter.
    const M = {
        a_contacter: ['✓', 'À contacter', 'ok'],
        a_verifier: ['?', 'À vérifier', 'warn'],
        a_ecarter: ['⛔', 'À écarter', 'ko'],
    };
    const v = (M[reco] || [])[2];
    if (!v) return '';
    return `<span class="verdict-chip ${v}" title="Verdict proposé : ${_ulEsc(M[reco][1])}">${M[reco][0]}</span>`;
}

function _ulScoreCell(l) {
    // Score = qualification IA (0-100).
    // Un lead « général » sans qualification IA : Score = « — »,
    // mais s'il a été qualifié (score ou reco présents), on l'affiche.
    const reco = (l.data_extra && l.data_extra.ia_reco) ? l.data_extra.ia_reco : (l.ia_reco || '');
    const raw = (l.score != null && l.score !== '') ? l.score : ((l.score_mobile && l.score_mobile > 0) ? l.score_mobile : null);
    if ((l.objectif || '') === 'general' && raw === null && !reco) {
        return '<span class="score-mut" title="Pas de score IA — qualification web uniquement">—</span>';
    }
    if (raw !== null && raw !== undefined && !isNaN(parseFloat(raw))) {
        const s = parseFloat(raw);
        const c = s >= 70 ? '#10b981' : s >= 50 ? '#f59e0b' : '#ef4444';
        const title = 'Score de qualification IA' + (reco ? ` — verdict proposé : ${reco}` : '');
        return `<span class="score-cell"><span class="score-chip" style="--c:${c}" title="${title}">${Math.round(s)}<i>/100</i></span>${_ulVerdictChip(reco)}</span>`;
    }
    if (reco) {
        return `<span class="score-cell">${_ulVerdictChip(reco)}</span>`;
    }
    if (l.audit_partial) {
        return '<span class="score-mut" style="font-style:italic" title="Mesure de performance bloquée par le site">Indisponible</span>';
    }
    return '<span class="score-mut">—</span>';
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
    if (p.objet) bits.push(`<b>« ${_ulEsc(p.objet)} »</b>`);
    if (p.email) bits.push(_ulEsc(p.email));
    if (p.from) bits.push(_ulEsc(p.from));
    if (p.raison) bits.push(`<i>${_ulEsc(p.raison)}</i>`);
    if (p.champ && p.from_statut && p.to) bits.push(`${_ulEsc(p.from_statut)} → <b>${_ulEsc(p.to)}</b>`);
    if (p.nb_envoi != null) bits.push(`${p.nb_envoi}ᵉ envoi`);
    return bits.join(' · ');
}
function unifiedLeadsOpenDetail(id) {
    _ul.detailId = id;
    // Le modal vit dans #subtab-leads (display:none quand on l'ouvre depuis l'onglet
    // Listes). Le rattacher au <body> pour qu'il s'affiche quoi qu'il arrive.
    const detailModal = document.getElementById('modal-ul-detail');
    if (detailModal && detailModal.parentElement !== document.body) {
        document.body.appendChild(detailModal);
    }
    if (!_ul.statutLabels || !_ul.transitions) {
        _ulFetchTransitions();
    }
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
        `<b>${_ulEsc(l.campagne_nom || '')}</b> · <span class="status-badge ${l.statut === 'rdv_obtenu' ? 'ok' : 'warn'}">${(_ul.statutLabels || {})[l.statut] || l.statut}</span>` +
        (l.entreprise ? ` · ${_ulEsc(l.entreprise)}` : '') + (l.ville ? ` · ${_ulEsc(l.ville)}` : '') +
        (l.email ? ` · <a href="mailto:${_ulEsc(l.email)}">${_ulEsc(l.email)}</a>` : '');
    const reply = (l.events || []).find(e => e.event_type === 'reponse');
    const box = sel('#ul-detail-reply');
    const p = reply ? reply.payload || {} : {};
    if (reply && (p.corps || p.snippet)) {
        box.style.display = '';
        sel('#ul-detail-reply-head').innerHTML =
            `${_ulEvDate(reply)} · de <b>${_ulEsc(p.from || (p.email || ''))}</b> · objet <b>« ${_ulEsc(p.objet || '(sans objet)')} »</b>`;
        sel('#ul-detail-reply-body').textContent = (p.corps || p.snippet || '').slice(0, 2000);
    } else {
        box.style.display = 'none';
    }
    const rows = (l.events || []).map(ev => {
        const meta = _EVSTAT[ev.payload && ev.payload.to] || '';
        return `<tr>
            <td style="width:210px;white-space:nowrap;color:var(--ink3)" class="sm2">${_ulEvDate(ev)}</td>
            <td style="white-space:nowrap">${_ulEvLabel(ev.event_type)}${meta ? ` <span class="status-badge ${meta}">${(_ul.statutLabels || {})[ev.payload.to] || ev.payload.to}</span>` : ''}</td>
            <td style="color:var(--ink2)" class="sm2">${_ulPayloadLine(ev)}</td></tr>`;
    }).join('');
    sel('#ul-detail-timeline').innerHTML = rows
        ? `<table class="tbl"><tbody>${rows}</tbody></table>`
        : '<div style="font-size:12px;color:var(--ink3)">Aucun événement.</div>';
}

// ─── Panneau latéral droit — port à l'IDENTIQUE du dashboard V5 ────────────
// Copie stricte (verbatim) des fonctions du panneau de dashboard_core.js
// (renderAuditPanel / renderEmailPanel / renderSuiviPanel + tout le stack),
// fournies par la V6 puisque dashboard_core n'y est pas chargé.
// Seule adaptation au point d'entrée (les données v2) : loadPanelContent
// lit /api/v2/leads/<id> au lieu de /api/leads/<id>. Installe uniquement si
// absents (V5 archive les fournit via son propre block).

if (typeof window.openLeadPanel !== 'function') {
    let _selectedLeadId = null;

    function _openPanelWithOverlay() {
        const _sp = document.getElementById('lead-details-panel') || document.getElementById('side-panel');
        if (_sp) _sp.classList.add('open');
        const mc = document.querySelector('.main-content');
        if (mc) mc.classList.add('with-panel');
        const overlay = document.getElementById('panel-overlay');
        if (overlay) overlay.style.display = 'block';
    }

    // Side Panel Functions
    function openLeadPanel(leadId, tab = 'audit') {
        _selectedLeadId = leadId;
        // Synchroniser la référence globale
        window._selectedLeadId = leadId;
        // Skeleton immédiat pendant le chargement
        const content = document.getElementById('panel-content');
        if (content) content.innerHTML = typeof skeletonPanel === 'function' ? skeletonPanel() : '';
        _openPanelWithOverlay();
        // Activer l'onglet sélectionné
        document.querySelectorAll('.side-panel-tab').forEach(t => {
            t.classList.toggle('active', t.dataset.tab === tab);
        });
        // Charger le contenu
        loadPanelContent(leadId, tab);
    }

    function closeSidePanel() {
        const _sp2 = document.getElementById('lead-details-panel') || document.getElementById('side-panel');
        if (_sp2) _sp2.classList.remove('open');
        const mc = document.querySelector('.main-content');
        if (mc) mc.classList.remove('with-panel');
        const overlay = document.getElementById('panel-overlay');
        if (overlay) overlay.style.display = 'none';
        // Réinitialiser l'état de sélection
        _selectedLeadId = null;
        window._selectedLeadId = null;
        // Vider le contenu pour la prochaine ouverture
        const content = document.getElementById('panel-content');
        if (content) content.innerHTML = '';
    }

    function switchPanelTab(tab, el) {
        document.querySelectorAll('.side-panel-tab').forEach(t => t.classList.remove('active'));
        el.classList.add('active');
        if(_selectedLeadId) {
            // Vider immédiatement, puis recharger
            const content = document.getElementById('panel-content');
            if (content) content.innerHTML = typeof skeletonPanel === 'function' ? skeletonPanel() : '';
            loadPanelContent(_selectedLeadId, tab);
        } else {
            // Panel ouvert sans prospect sélectionné : fermer
            closeSidePanel();
        }
    }

    // Endpoint v2 → prépare l'objet legacy attendu par les renderers V5 :
    // les champs source du prospect sont remontés au niveau racine (data_extra).
function _ulPanelComposeLead(p) {
        const extra = (p && p.data_extra && typeof p.data_extra === 'object') ? p.data_extra : {};
        const composed = Object.assign({}, p || {}, extra);
        // v2 : la note vit dans la colonne prospects.note → l'exposer comme « notes »
        // attendue par le panneau (copie verbatim V5).
        if (p && typeof p.note === 'string' && p.note.trim()) composed.notes = p.note;
        return composed;
    }

    // v2 : le payload prospect n'expose pas « objectif » → un lead avec site_web est 'web'.
    function _ulPanelIsWebLead(lead) {
        if (!lead) return false;
        return (lead.objectif || 'general') === 'web';
    }

    function _ulPanelFindCache(leadIdNum) {
        const pools = [];
        if (window._ul && Array.isArray(window._ul.leads)) pools.push(window._ul.leads);
        if (window.ListesModule && window.ListesModule._state && Array.isArray(window.ListesModule._state.leads)) pools.push(window.ListesModule._state.leads);
        for (let i = 0; i < pools.length; i++) {
            const hit = pools[i].find(l => l.id == leadIdNum);
            if (hit) return hit;
        }
        return null;
    }

    // v2 : ense de l'email réel (template de campagne rendu → coquille HTML) pour
    // afficher l'aperçu tel que le prospect le verra, même sans email_objet/corps stocké.
    async function _ulFetchV2Email(leadIdNum) {
        try {
            const r = await fetch('/api/v2/leads/' + leadIdNum + '/email', { cache: 'no-store' });
            if (!r.ok) return null;
            const d = await r.json();
            return (d && d.success && d.email) ? d.email : null;
        } catch (e) {
            return null;
        }
    }

    async function renderEmailTab(lead, content, leadIdNum) {
        // v2 : récupère le rendu « tel qu'envoyé » et l'injecte dans le lead
        // (les renderers V5 attendent email_corps/email_objet au top-level).
        let v2m = null;
        if (_ulIsV2() && lead && lead.id) {
            v2m = await _ulFetchV2Email(lead.id);
            if (_selectedLeadId != leadIdNum) return;
            if (v2m && v2m.corps) {
                if (!lead.email_corps) {
                    lead = Object.assign({}, lead, { email_corps: v2m.corps, email_objet: lead.email_objet || v2m.objet });
                }
                lead._v2Email = v2m;
            }
        }
        content.innerHTML = renderEmailPanel(lead);
        _setEmailPreviewSrc(lead);
        if (_ulPanelIsWebLead(lead) && document.getElementById('email-maq-' + leadIdNum)) {
            _loadLeadMaquette(leadIdNum, 'email-maq-' + leadIdNum);
        }
    }

    async function loadPanelContent(leadId, tab) {
        const content = document.getElementById('panel-content');
        if (!content) return;

        // Garder la référence du prospect courant pour éviter les données croisées
        const currentLeadId = leadId;
        const leadIdNum = Number(leadId);

        // Utiliser d'abord les données en cache pour affichage immédiat
        let leadFromCache = _ulPanelFindCache(leadIdNum);
        if (leadFromCache) {
            leadFromCache = _ulPanelComposeLead(leadFromCache);
            const titleEl = document.getElementById('panel-title');
            if (titleEl) titleEl.textContent = leadFromCache.nom || 'Détails';
if (tab === 'audit') {
                content.innerHTML = renderAuditPanel(leadFromCache);
                if (_ulPanelIsWebLead(leadFromCache) && document.getElementById('ia-maq-' + leadIdNum)) {
                    _loadLeadMaquette(leadIdNum, 'ia-maq-' + leadIdNum);
                }
            }
else if (tab === 'email') { renderEmailTab(leadFromCache, content, leadIdNum); }
            else if (tab === 'suivi') content.innerHTML = renderSuiviPanel(leadFromCache);
        }

        // Rafraîchir depuis l'API pour avoir les données à jour
        try {
            const r = await fetch('/api/v2/leads/' + leadIdNum, { cache: 'no-store' });
            let lead = null;

            if (r.ok) {
                const d = await r.json();
                lead = (d && d.success) ? d.lead : null;
            }

            // Vérifier qu'on n'a pas changé de prospect entre temps
            if (_selectedLeadId != currentLeadId) return;

            if (!lead) {
                if (!leadFromCache) content.innerHTML = '<p style="color:var(--ink3);padding:1rem">Lead non trouvé</p>';
                return;
            }

            lead = _ulPanelComposeLead(lead);

            const titleEl = document.getElementById('panel-title');
            if (titleEl) titleEl.textContent = lead.nom || 'Détails';

            // Rendre le contenu final
if (tab === 'audit') {
                content.innerHTML = renderAuditPanel(lead);
                // Injecter la maquette réelle (async) pour le bloc Prospection IA
                if (_ulPanelIsWebLead(lead) && document.getElementById('ia-maq-' + leadIdNum)) {
                    _loadLeadMaquette(leadIdNum, 'ia-maq-' + leadIdNum);
                }
            } else if (tab === 'email') { renderEmailTab(lead, content, leadIdNum); }
            else if (tab === 'suivi') content.innerHTML = renderSuiviPanel(lead);
        } catch (e) {
            if (!leadFromCache) content.innerHTML = '<p style="color:var(--red);padding:1rem">Erreur: ' + e.message + '</p>';
        }
    }

    function _scoreBar(label, val, max, unit, inv) {
        if (val === null || val === undefined || val === 0 && unit === 's') return '';
        const pct = Math.min(100, Math.round((val / max) * 100));
        const good = inv ? pct < 50 : pct >= 70;
        const warn = inv ? pct < 70 : pct >= 40;
        const color = good ? '#10b981' : warn ? '#f59e0b' : '#ef4444';
        const display = unit === 's' ? parseFloat(val).toFixed(1) + 's' : val + unit;
        return '<div style="margin-bottom:14px">'
            + '<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:6px">'
            + '<span style="color:#64748b;font-weight:500">' + label + '</span><span style="font-weight:700;color:#0f172a">' + display + '</span></div>'
            + '<div style="height:6px;background:#f1f5f9;border-radius:4px;overflow:hidden">'
            + '<div style="width:' + pct + '%;height:100%;background:' + color + ';border-radius:4px;transition:width 0.5s ease"></div>'
            + '</div></div>';
    }

    function _renderScoreBars(lead) {
        return '<div style="margin-bottom:20px;padding:16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px">'
            + _scoreBar('Performance', parseInt(lead.score_perf) || 0, 100, '', false)
            + _scoreBar('SEO', parseInt(lead.score_seo) || 0, 100, '', false)
            + _scoreBar('Urgence', parseFloat(lead.score_urgence) || 0, 10, '/10', true)
            + (lead.lcp ? _scoreBar('LCP', parseFloat(lead.lcp) / 1000, 5, 's', true) : '')
            + '</div>';
    }

    function _pil(value, label) {
        if (value === null || value === undefined || value === '') return '';
        return `<div style="flex:1;min-width:110px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:10px 12px">
            <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.05em;color:#94a3b8;font-weight:700;margin-bottom:3px">${label}</div>
            <div style="font-size:18px;font-weight:800;color:#0f172a">${value}</div>
        </div>`;
    }

    function _iaActionBtn(leadId, op, label, primary) {
        const fn = {
            qualify: 'qualifyLead', maquette: 'maquetteLead', redact: 'redactLead'
        }[op];
        if (!fn || !(window.IaActions && window.IaActions[fn])) return '';
        const cls = primary ? 'btn bp1 sm' : 'btn bg1 sm';
        return `<button class="${cls}" style="font-size:13px;padding:9px 12px;flex:1" onclick="window.IaActions.${fn}(${leadId});if(window.panelToastBtn)panelToastBtn(this,'OK')">
            ${op === 'qualify' ? '<span style="margin-right:5px">✦</span>Qualifier' : ''}
            ${op === 'maquette' ? '<span style="margin-right:5px">🎨</span>Maquette' : ''}
            ${op === 'redact' ? '<span style="margin-right:5px">✎</span>Rédiger mail' : ''}
        </button>`;
    }

function _renderIAPanel(lead) {
        const hasIA = (lead.ia_opportunite || lead.ia_opportunite === 0) || (lead.ia_score || lead.ia_score === 0) || (lead.ia_signaux);
        const hasSite = !!(lead.site_web && lead.site_web.trim());
        const obj = (lead.objectif || ((_ulIsV2() && hasSite) ? 'web' : 'general'));
        const emailObj = lead.email_objet || '';
        const emailBody = lead.email_corps || '';
        if (!hasIA && !emailObj && !emailBody && obj !== 'web') return '';

        const id = lead.id;
        const opp = lead.ia_opportunite;
        const score = (lead.ia_score != null && lead.ia_score !== '') ? lead.ia_score : lead.score;

        const badge = obj === 'web'
            ? `<span style="background:rgba(99,102,241,0.12);color:#6366f1;padding:3px 9px;border-radius:6px;font-size:11px;font-weight:700">🌐 WEB · maquette + email</span>`
            : `<span style="background:rgba(16,185,129,0.12);color:#059669;padding:3px 9px;border-radius:6px;font-size:11px;font-weight:700">📋 GÉNÉRAL · qualification + email</span>`;
        const casBadge = obj === 'web'
            ? (hasSite
                ? `<span style="background:rgba(139,92,246,0.12);color:#7c3aed;padding:3px 9px;border-radius:6px;font-size:11px;font-weight:700">🏗️ Avec site · refonte</span>`
                : `<span style="background:rgba(16,185,129,0.12);color:#059669;padding:3px 9px;border-radius:6px;font-size:11px;font-weight:700">🆕 Sans site · création</span>`)
            : '';

        // Bloc maquette : conteneur rempli en async (fetch capture). Id stable pour injection.
        const maquetteBoxId = 'ia-maq-' + id;
const maquetteHtml = obj === 'web' ? `
            <div style="margin-top:14px;border-top:1px dashed #cbd5e1;padding-top:12px">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
                    <span style="font-size:11px;font-weight:800;color:#7c3aed;text-transform:uppercase;letter-spacing:0.04em">Maquette du site</span>
                </div>
                <div id="${maquetteBoxId}" style="background:#eef2ff;border:1px dashed #c7d2fe;border-radius:10px;padding:16px;text-align:center;color:#6366f1;font-size:12px">Chargement de la maquette…</div>
                <button class="btn bp1 sm" style="margin-top:10px;width:100%;font-size:13px;padding:10px;gap:6px" onclick="window.IaActions && IaActions.leadMaquette(${id}).then(d=>{if(d&&d.files&&d.files.length){ if(window.dialogOpenMaquette) dialogOpenMaquette(${id}); else window.open('/api/ia/maquettes/'+encodeURIComponent(d.liste)+'/'+encodeURIComponent(${id})+'/index.html','_blank'); } else _t ? _t('Aucune maquette générée. Lancez la génération via le bouton « Maquette » ci-dessous.','warning') : alert('Aucune maquette générée.')})">🖼 Voir la maquette générée</button>
            </div>` : '';

        const emailPreview = (emailObj || emailBody)
            ? `<div style="margin-top:14px;border-top:1px dashed #cbd5e1;padding-top:12px">
                ${emailObj ? `<div style="font-size:12px;color:#0f172a;font-weight:700;margin-bottom:6px">Objet : <span style="color:#059669">${escHtml(emailObj)}</span></div>` : ''}
                ${emailBody ? `<div style="font-size:12px;color:#475569;line-height:1.5;max-height:120px;overflow-y:auto;white-space:pre-wrap">${escHtml(emailBody)}</div>` : ''}
                <div style="font-size:11px;color:#10b981;margin-top:8px">✓ Email rédigé par l'IA — envoi NUL (validation manuelle requise)</div>
             </div>`
            : (obj === 'web' ? `<div style="margin-top:14px;border-top:1px dashed #cbd5e1;padding-top:10px;font-size:11px;color:#94a3b8">Email non encore rédigé — bouton « Rédiger mail » ci-dessous.</div>` : '');

        const actions = obj === 'web'
            ? `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:14px">
                ${_iaActionBtn(id, 'qualify', false)}
                ${_iaActionBtn(id, 'maquette', false)}
                ${_iaActionBtn(id, 'redact', false)}
             </div>`
            : `<div style="display:flex;gap:6px;margin-top:14px">
                ${_iaActionBtn(id, 'qualify', false)}
                ${_iaActionBtn(id, 'redact', false)}
             </div>`;

        return `
        <div class="panel-section" style="margin-bottom:32px">
            <h4 style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:12px;display:flex;align-items:center;gap:8px">
                <span style="color:#6366f1">✦</span> Prospection IA
            </h4>
            <div style="background:linear-gradient(to bottom,rgba(99,102,241,0.03),rgba(99,102,241,0.06));border:1px solid rgba(99,102,241,0.18);border-radius:14px;padding:16px">
                <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:12px">
                    <span style="font-size:12px;font-weight:700;color:#0f172a">Assistant</span>
                    <span style="display:flex;flex-wrap:wrap;gap:6px">${badge}${casBadge}</span>
                </div>
                <div style="display:flex;flex-wrap:wrap;gap:8px">
                    ${_pil(opp !== null && opp !== undefined && opp !== '' ? opp : null, 'Opportunité /100')}
                    ${_pil(score !== null && score !== undefined && score !== '' ? score : null, 'Score /100')}
                </div>
                ${lead.ia_signaux ? `<div style="margin-top:10px;font-size:12px;color:#475569;line-height:1.5;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:10px"><span style="color:#94a3b8;font-weight:700">Signaux :</span> ${escHtml(lead.ia_signaux)}</div>` : ''}
                ${maquetteHtml}
                ${emailPreview}
                ${actions}
            </div>
        </div>`;
    }

    function _loadLeadMaquette(leadId, containerId) {
        const box = document.getElementById(containerId);
        if (!box || !window.IaActions) return;
        window.IaActions.leadMaquette(leadId).then(d => {
            if (!d || !d.a_capture) {
                box.innerHTML = '<span style="color:#94a3b8">Aucune maquette générée pour ce lead.</span>';
                return;
            }
            const url = '/api/ia/maquettes/' + encodeURIComponent(d.liste) + '/' + encodeURIComponent(leadId) + '/capture.png';
            box.innerHTML = `<div style="cursor:pointer" onclick="window.open('${url}','_blank')">
                <img src="${url}" alt="Maquette" style="width:100%;border-radius:8px;border:1px solid #e2e8f0;box-shadow:0 2px 8px rgba(0,0,0,0.08)" onerror="this.parentElement.innerHTML='<span style=&quot;color:#ef4444;font-size:12px&quot;>Capture introuvable (${escHtml(d.liste)}/${leadId})</span>'">
                <div style="font-size:10px;color:#94a3b8;margin-top:4px">${escHtml(d.liste)} / PROMPT/${leadId} — clic pour agrandir</div>
            </div>`;
        });
    }

    function _srcBadge(source) {
        const cfg = {
            maps:   ['#64748b','Maps'],   ads:    ['#f97316','Ads'],
            fb_ads: ['#3b82f6','FB Ads'], tech:   ['#8b5cf6','Tech'],
            ecom:   ['#8b5cf6','E-com'],  jobs:   ['#06b6d4','Jobs'],
            bodacc: ['#10b981','BODACC'],
        };
        const [c,l] = cfg[source] || ['#94a3b8', source || '?'];
        return `<span style="background:${c}15;color:${c};padding:4px 8px;border-radius:6px;font-size:11px;font-weight:600">${l}</span>`;
    }

    function _prospBadge(s) {
        const cfg = {
            a_contacter:      ['#64748b','À contacter'],
            "contacte":       ['#60a5fa','Contacté'],
            email_genere:     ['#6366f1','Email prêt'],
            step1_envoye:     ['#3b82f6','Step 1 ✓'],
            repondu:          ['#f59e0b','Répondu'],
            lien_envoye:      ['#10b981','Rapport livré'],
            linkedin_envoye:  ['#0077b5','LinkedIn'],
            formulaire_envoye:['#6366f1','Formulaire'],
        };
        const [c,l] = cfg[s] || ['#94a3b8', s||'—'];
        return `<span class="prosp-badge" style="background:${c}15;color:${c};padding:4px 8px;border-radius:6px;font-size:11px;font-weight:600">${l}</span>`;
    }

    function _row(label, content) {
        if (!content) return '';
        return `<div style="display:flex;gap:16px;padding:12px 0;border-bottom:1px solid #f1f5f9;align-items:center">
            <dt style="color:#64748b;font-size:12px;width:90px;flex-shrink:0;font-weight:500;margin:0;text-transform:uppercase;letter-spacing:0.05em">${label}</dt>
            <dd style="color:#0f172a;font-size:13px;font-weight:500;margin:0;flex:1;word-break:break-word">${content}</dd>
        </div>`;
    }

    function _contactPill(lead, method, label) {
        const key = 'contact_' + method;
        const checked = lead[key] ? 1 : 0;
        const bg = checked ? '#10b981' : '#f1f5f9';
        const text = checked ? '#fff' : '#475569';
        return `<div onclick="toggleContactPill(${lead.id},'${method}',this)" style="cursor:pointer;display:flex;align-items:center;gap:6px;padding:8px 12px;border-radius:8px;font-size:12px;font-weight:600;background:${bg};color:${text};border:none;transition:all .15s">${checked ? '✓' : '○'} ${label}</div>`;
    }

    function renderAuditPanel(lead) {
        const hasAudit  = !!(lead.score_perf || lead.score_seo || lead.lcp || lead.lien_rapport);
        const isSniper  = lead.source && lead.source !== 'maps';
        const ceoName   = [lead.ceo_prenom, lead.ceo_nom].filter(Boolean).join(' ');
        const _isEmail = v => v && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
        const email     = _isEmail(lead.email_valide_audit) ? lead.email_valide_audit : (_isEmail(lead.email_valide) ? lead.email_valide : (lead.email || ''));
        const tel       = lead.telephone_sniper || lead.telephone || '';
        const lcp       = lead.lcp ? (parseFloat(lead.lcp)/1000).toFixed(1) + 's' : null;
        const mode      = lead.copywriting_mode;

        // Politique de contact (Migré de Sniper)
        let contactHtml = '';
        const hasEmailValide = !!lead.email_valide_audit;
        const catchAll = !!lead.is_catch_all;
        const hasPhone = !!(lead.telephone || lead.telephone_sniper);

        if (hasEmailValide && !catchAll) {
            contactHtml = `<div style="background:#dcfce7;color:#166534;padding:12px 16px;border-radius:12px;font-size:13px;font-weight:600;margin-bottom:20px;border:1px solid #bbf7d0;display:flex;align-items:center;gap:10px">
                <span style="font-size:18px">✅</span> <span>Email valide — Envoi step 1 recommandé</span>
            </div>`;
        } else if (catchAll) {
            contactHtml = `<div style="background:#fef3c7;color:#92400e;padding:12px 16px;border-radius:12px;font-size:13px;font-weight:600;margin-bottom:20px;border:1px solid #fde68a;display:flex;align-items:center;gap:10px">
                <span style="font-size:18px">⚠️</span> <span>Catch-all — Approche LinkedIn ou téléphone</span>
            </div>`;
        } else if (hasPhone) {
            contactHtml = `<div style="background:#dbeafe;color:#1e40af;padding:12px 16px;border-radius:12px;font-size:13px;font-weight:600;margin-bottom:20px;border:1px solid #bfdbfe;display:flex;align-items:center;gap:10px">
                <span style="font-size:18px">📞</span> <span>Pas d'email — Contacter par téléphone</span>
            </div>`;
        } else {
            contactHtml = `<div style="background:#fee2e2;color:#991b1b;padding:12px 16px;border-radius:12px;font-size:13px;font-weight:600;margin-bottom:20px;border:1px solid #fecaca;display:flex;align-items:center;gap:10px">
                <span style="font-size:18px">❌</span> <span>Aucun contact — Formulaire site ou LinkedIn manuel</span>
            </div>`;
        }

        return `
        ${contactHtml}
        <div class="panel-section" style="margin-bottom:24px">
            <div style="display:flex;align-items:center;gap:16px;background:#f8fafc;padding:20px;border-radius:12px;border:1px solid #e2e8f0">
                <div style="width:52px;height:52px;background:linear-gradient(135deg, #10b981, #059669);color:#fff;border-radius:12px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:20px;flex-shrink:0;box-shadow:0 4px 12px rgba(16,185,129,0.2)">${(lead.nom||'').charAt(0).toUpperCase()}</div>
                <div style="flex:1;min-width:0">
                    <div style="font-weight:800;font-size:18px;color:#0f172a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;letter-spacing:-0.3px">${escHtml(lead.nom||'—')}</div>
                    <div style="font-size:13px;color:#64748b;margin-top:2px;font-weight:500">${[lead.ville,lead.category||lead.secteur].filter(Boolean).map(escHtml).join(' · ')||'—'}</div>
                    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:10px">
                        ${_srcBadge(lead.source)}
                        ${lead.statut_prospection ? _prospBadge(lead.statut_prospection) : ''}
                        ${lead.tag_urgence ? `<span style="background:#f1f5f9;color:#475569;padding:4px 8px;border-radius:6px;font-size:11px;font-weight:600">${lead.tag_urgence}</span>` : ''}
                    </div>
                </div>
                <button class="leads-btn" onclick="openEditLeadFromPanel(${lead.id})" title="Modifier" style="padding:10px">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
                </button>
            </div>
        </div>

        <div class="panel-section" style="margin-bottom:32px">
            <h4 style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:12px">Coordonnées</h4>
            <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:0 20px">
                <dl style="margin:0">
                    ${_row('Décideur', ceoName ? `<strong>${escHtml(ceoName)}</strong>${lead.ceo_source?` <span style="color:#94a3b8;font-size:11px;font-weight:400">(${lead.ceo_source})</span>`:''}` : '')}
                    ${email ? `<div style="display:flex;gap:16px;padding:12px 0;border-bottom:1px solid #f1f5f9;align-items:center">
                        <dt style="color:#64748b;font-size:12px;width:90px;flex-shrink:0;font-weight:500;margin:0;text-transform:uppercase;letter-spacing:0.05em">Email</dt>
                        <dd style="margin:0;flex:1;min-width:0;font-weight:500"><a href="mailto:${escHtml(email)}" style="color:#10b981;text-decoration:none;font-size:13px;word-break:break-all">${escHtml(email)}</a>${lead.email_valide_audit?` <span style="color:#10b981;font-size:11px">✓ Validé</span>`:''}</dd>
                    </div>` : ''}
                    ${lead.email_2 ? `<div style="display:flex;gap:16px;padding:12px 0;border-bottom:1px solid #f1f5f9;align-items:center">
                        <dt style="color:#64748b;font-size:12px;width:90px;flex-shrink:0;font-weight:500;margin:0;text-transform:uppercase;letter-spacing:0.05em">Email 2</dt>
                        <dd style="margin:0;flex:1;min-width:0;font-weight:500"><a href="mailto:${escHtml(lead.email_2)}" style="color:#10b981;text-decoration:none;font-size:13px;word-break:break-all">${escHtml(lead.email_2)}</a></dd>
                    </div>` : ''}
                    ${_row('Téléphone', tel ? `<a href="tel:${escHtml(tel)}" style="color:#0f172a;text-decoration:none">${escHtml(tel)}</a>` : '')}
                    ${lead.phone_2 ? _row('Téléphone 2', `<a href="tel:${escHtml(lead.phone_2)}" style="color:#0f172a;text-decoration:none">${escHtml(lead.phone_2)}</a>`) : ''}
                    ${mode ? _row('Mode', `<span style="color:${mode==='direct'?'#10b981':'#f59e0b'};font-weight:600">${mode==='direct'?'🎯 Approche Directe':'📤 Approche Transfert'}</span>`) : ''}
                    ${lead.site_web ? `<div style="display:flex;gap:16px;padding:12px 0;align-items:center">
                        <dt style="color:#64748b;font-size:12px;width:90px;flex-shrink:0;font-weight:500;margin:0;text-transform:uppercase;letter-spacing:0.05em">Site web</dt>
                        <dd style="margin:0;flex:1;min-width:0;font-weight:500"><a href="${escHtml(lead.site_web)}" target="_blank" style="color:#10b981;text-decoration:none;font-size:13px;word-break:break-all">${escHtml(lead.site_web.replace(/^https?:\/\//,''))}</a></dd>
                    </div>` : ''}
                    ${lead.lien_maps ? `<div style="display:flex;gap:16px;padding:12px 0;border-bottom:1px solid #f1f5f9;align-items:center">
                        <dt style="color:#64748b;font-size:12px;width:90px;flex-shrink:0;font-weight:500;margin:0;text-transform:uppercase;letter-spacing:0.05em">Google Maps</dt>
                        <dd style="margin:0;flex:1;min-width:0;font-weight:500"><a href="${escHtml(lead.lien_maps)}" target="_blank" style="color:#10b981;text-decoration:none;font-size:13px;word-break:break-all">📍 Voir la fiche</a></dd>
                    </div>` : ''}
                    <div style="display:flex;gap:16px;padding:12px 0;border-top:1px solid #f1f5f9">
                        <dt style="color:#64748b;font-size:12px;width:90px;flex-shrink:0;font-weight:500;margin:0;text-transform:uppercase;letter-spacing:0.05em;padding-top:8px">Notes</dt>
                        <dd style="margin:0;flex:1;min-width:0;">
                            <textarea onblur="saveCoreNotes(${lead.id}, this.value)" style="width:100%;height:60px;resize:vertical;border:1px solid #e2e8f0;border-radius:6px;padding:8px;font-size:13px;font-family:inherit" placeholder="Ajouter une note (sauvegarde auto)...">${escHtml(lead.notes || '')}</textarea>
                        </dd>
                    </div>
                </dl>
            </div>
        </div>

        <div class="panel-section" style="margin-bottom:32px">
            <h4 style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:12px">Moyens de contact</h4>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
                ${_contactPill(lead, 'mail', 'Mail')}
                ${_contactPill(lead, 'appel', 'Appel')}
                ${_contactPill(lead, 'wp', 'WhatsApp')}
                ${_contactPill(lead, 'li', 'LinkedIn')}
                ${_contactPill(lead, 'fb', 'Facebook')}
                ${_contactPill(lead, 'autres', 'Autres')}
            </div>
        </div>

${!_ulIsV2() || hasAudit || lead.statut==='audit_echoue' ? `
<div class="panel-section" style="margin-bottom:32px">
    <h4 style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:12px">${hasAudit || lead.statut==='audit_echoue' ? 'Scores d\'audit' : 'Scores'}</h4>
            ${lead.cms_detected ? `<div style="display:inline-block;padding:6px 12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;font-size:12px;color:#475569;font-weight:600;margin-bottom:16px">Technologie : <span style="color:#0f172a">${escHtml(lead.cms_detected)}</span></div>` : ''}
            ${lead.statut==='audit_echoue'
                ? `<div style="background:#fef2f2;border:1px solid #fecaca;padding:16px;border-radius:12px;display:flex;align-items:flex-start;gap:12px"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2" style="flex-shrink:0;margin-top:2px"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg><div><p style="color:#ef4444;font-weight:700;margin:0 0 4px;font-size:14px">Échec de l'audit</p><p style="font-size:13px;color:#7f1d1d;margin:0">${escHtml(lead.probleme_principal||'Raison technique inconnue')}</p></div></div>`
                : hasAudit ? _renderScoreBars(lead)
                : ''}
        </div>` : ''}
        ${!hasAudit && _ulIsV2() ? `
        <div class="panel-section" style="margin-bottom:32px">
            <h4 style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:12px">Audit legacy</h4>
            <div style="padding:20px;text-align:center;background:#f8fafc;border:1px dashed #cbd5e1;border-radius:12px"><p style="font-size:13px;color:#64748b;font-weight:500;margin:0">Cet audit n'est pas applicable aux leads gérés par le pipeline IA v2.<br>La qualification est gérée par l'assistant (Prospection IA ci-dessus).</p></div>
        </div>` : ''}

        <!-- IA ⇄ Dashboard (assistant) -->
        ${_renderIAPanel(lead)}

        <!-- Section Plus d'infos -->
        ${(() => {
            try {
                // Données de base disponibles pour TOUS les leads
                let baseHtml = '';
                if (lead.rating) baseHtml += `<div style="margin-bottom:8px"><span style="color:#64748b">Note Google :</span> <span style="font-weight:600">${parseFloat(lead.rating).toFixed(1)} ⭐</span></div>`;
                if (lead.nb_avis) baseHtml += `<div style="margin-bottom:8px"><span style="color:#64748b">Avis Google :</span> <span style="font-weight:600">${lead.nb_avis} avis</span></div>`;
                if (lead.mot_cle) baseHtml += `<div style="margin-bottom:8px"><span style="color:#64748b">Mot-clé :</span> <span style="font-weight:600;background:#f1f5f9;padding:2px 7px;border-radius:6px">${escHtml(lead.mot_cle)}</span></div>`;
                if (lead.date_scraping) baseHtml += `<div style="margin-bottom:8px"><span style="color:#64748b">Détecté le :</span> <span style="font-weight:600">${new Date(lead.date_scraping).toLocaleDateString('fr-FR')}</span></div>`;

                // Données de donnees_audit (si présentes)
                let metaHtml = '';
                if (lead.donnees_audit) {
                    let audit = null;
                    try {
                        audit = typeof lead.donnees_audit === 'string' ? JSON.parse(lead.donnees_audit) : lead.donnees_audit;
                    } catch(e) {
                        try {
                            const cleaned = lead.donnees_audit.replace(/[\u0000-\u001F\u007F-\u009F]/g, "");
                            audit = JSON.parse(cleaned);
                        } catch(e2) { audit = null; }
                    }

                    if (audit && Object.keys(audit).length > 0) {
                        if (audit.tag && audit.tag !== 'score_ok') {
                            metaHtml += `<div style="margin-bottom:12px;padding:10px;background:#fff;border:1px solid #fee2e2;border-radius:8px">
                                <span style="color:#b91c1c;font-size:10px;text-transform:uppercase;display:block;margin-bottom:2px;font-weight:800">Analyse Technique :</span>
                                <span style="font-weight:700;color:#991b1b;font-size:13px">${escHtml(audit.tag)}</span>
                                ${audit.reason ? `<p style="margin:4px 0 0;font-size:12px;color:#7f1d1d;line-height:1.4">${escHtml(audit.reason)}</p>` : ''}
                            </div>`;
                        } else if (audit.reason) {
                            metaHtml += `<div style="margin-bottom:12px;font-size:12px;color:#475569;line-height:1.4">${escHtml(audit.reason)}</div>`;
                        }
                        if (audit.ad_start) metaHtml += `<div style="margin-bottom:8px"><span style="color:#64748b">Diffusion Ads :</span> <span style="font-weight:600">${escHtml(audit.ad_start)}</span></div>`;
                        if (audit.fan_count) metaHtml += `<div style="margin-bottom:8px"><span style="color:#64748b">Notoriété :</span> <span style="font-weight:600">${escHtml(String(audit.fan_count))} abonnés</span></div>`;
                        if (audit.cms || audit.cms_detected) metaHtml += `<div style="margin-bottom:8px"><span style="color:#64748b">Technologie :</span> <span style="font-weight:600">${escHtml(audit.cms || audit.cms_detected)}</span></div>`;
                        if (audit.ad_body) {
                            metaHtml += `<div style="margin-top:12px">
                                <span style="color:#64748b;display:block;margin-bottom:4px;font-size:11px;text-transform:uppercase;font-weight:700">Contenu de la publicité :</span>
                                <div style="font-style:italic;background:#f8fafc;padding:12px;border-radius:8px;border:1px solid #e2e8f0;font-size:12px;line-height:1.5;color:#475569;max-height:150px;overflow-y:auto">${escHtml(audit.ad_body)}</div>
                            </div>`;
                        }
                        const fbUrl = audit.page_url || (audit.page_id ? `https://www.facebook.com/${audit.page_id}` : null);
                        if (fbUrl) {
                            metaHtml += `<div style="margin-top:12px"><a href="${escHtml(fbUrl)}" target="_blank" style="color:#1877f2;text-decoration:none;font-size:12px;font-weight:700;display:flex;align-items:center;gap:6px">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M22 12c0-5.52-4.48-10-10-10S2 6.48 2 12c0 4.84 3.44 8.87 8 9.8V15H8v-3h2V9.5C10 7.57 11.57 6 13.5 6H16v3h-2c-.55 0-1 .45-1 1v2h3v3h-3v6.95c5.05-.5 9-4.76 9-9.95z"/></svg>
                                Voir la page Facebook →
                            </a></div>`;
                        }
                        if (audit.ad_id) {
                            metaHtml += `<div style="margin-top:8px"><a href="https://www.facebook.com/ads/library/?id=${audit.ad_id}" target="_blank" style="color:#64748b;text-decoration:none;font-size:12px;font-weight:700;display:flex;align-items:center;gap:6px">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
                                Voir dans l'Ad Library →
                            </a></div>`;
                        }
                        if (lead.source === 'fb_ads' || lead.source === 'ads') {
                            metaHtml += `<div style="margin-top:16px;padding-top:12px;border-top:1px dashed #cbd5e1">
                                <span style="color:#64748b;display:block;margin-bottom:6px;font-size:10px;text-transform:uppercase;font-weight:700">Capture d'écran :</span>
                                <div style="width:100%;aspect-ratio:16/9;background:#f1f5f9;border-radius:10px;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#94a3b8;font-size:11px;font-style:italic;text-align:center;padding:20px;border:1px solid #e2e8f0">
                                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-bottom:8px;opacity:0.5"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                                    Capture bientôt disponible
                                </div>
                            </div>`;
                        }

                        // Profil A : Mockup du futur site
                        if (lead.template_used === 'maquette' && lead.screenshot_desktop) {
                            const slug = lead.lien_rapport ? lead.lien_rapport.replace('local://', '').replace('https://audit.incidenx.com/', '').replace(/\/$/, '') : '';
                            const screenshotUrl = slug ? `/previews/${slug}/${lead.screenshot_desktop.split(/[/\\]/).pop()}` : '';
                            metaHtml += `<div style="margin-top:16px;padding-top:12px;border-top:1px dashed #10b981">
                                <span style="color:#059669;display:block;margin-bottom:6px;font-size:10px;text-transform:uppercase;font-weight:700">Mockup du futur site :</span>
                                ${screenshotUrl ? `<img src="${escHtml(screenshotUrl)}" style="width:100%;border-radius:8px;border:1px solid #e2e8f0;box-shadow:0 2px 8px rgba(0,0,0,0.08)" onerror="this.style.display='none'">` : ''}
                                ${lead.lien_rapport ? `<div style="margin-top:8px;font-size:11px;color:#64748b;word-break:break-all">Chemin : ${escHtml(lead.lien_rapport)}</div>` : ''}
                            </div>`;
                        }
                    }
                }

                const fullHtml = baseHtml + metaHtml;
                if (!fullHtml) return '';

                return `
                <div class="panel-section" id="section-meta-scraper" style="margin-bottom:32px;animation: fadeIn 0.3s ease">
                    <div style="background:linear-gradient(to bottom, rgba(16,185,129,0.03), rgba(16,185,129,0.07));border:1px solid rgba(16,185,129,0.2);border-radius:16px;padding:20px;box-shadow:0 4px 12px rgba(16,185,129,0.05)">
                        <h4 style="font-size:11px;font-weight:900;color:#059669;margin-bottom:14px;text-transform:uppercase;letter-spacing:0.1em;display:flex;align-items:center;gap:8px">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>
                            Plus d'infos
                        </h4>
                        <div style="font-size:13px;color:#1e293b;line-height:1.8">
                            ${fullHtml}
                        </div>
                    </div>
                </div>`;
            } catch(e) { console.error("Plus d'infos render error:", e); return ''; }
        })()}

<div class="panel-section" style="margin-top:auto;padding-top:24px;border-top:1px solid #e2e8f0">
            <div style="display:flex;gap:8px;flex-wrap:wrap">
                ${_ulPanelIsWebLead(lead) ? `<button class="btn bg2 sm" style="font-size:13px;padding:9px 12px;flex:0 1 auto" onclick="window.IaActions && IaActions.leadMaquette(${lead.id}).then(d=>{if(d&&d.files&&d.files.length){ if(window.dialogOpenMaquette) dialogOpenMaquette(${lead.id}); else window.open('/api/ia/maquettes/'+encodeURIComponent(d.liste)+'/'+encodeURIComponent(${lead.id})+'/index.html','_blank'); } else _t ? _t('Aucune maquette générée pour ce lead.','warning') : alert('Aucune maquette générée pour ce lead.');})">🖼 Voir la maquette</button>` : ''}
                ${_iaActionBtn(lead.id, 'qualify', 'Qualifier', true)}
                ${_ulPanelIsWebLead(lead) ? _iaActionBtn(lead.id, 'maquette', 'Maquette', false) : ''}
                ${_iaActionBtn(lead.id, 'redact', 'Rédiger mail', false)}
            </div>
            <div style="font-size:11px;color:#94a3b8;margin-top:10px">Actions IA — aucune action n'envoie de mail (validation manuelle requise).</div>
        </div>
        `;
    }

    function renderEmailPanel(lead) {
        const hasEmail = lead.email_corps && lead.email_corps.length > 0;
        // Extract subject from email HTML title tag
        let emailSubject = lead.email_objet || 'Objet non défini';
        if (!lead.email_objet && lead.email_corps) {
            const titleMatch = lead.email_corps.match(/<title>([^<]+)<\/title>/i);
            if (titleMatch) emailSubject = titleMatch[1];
        }
        // Use profile field from API, or extract from email_objet
        let profil = lead.profile || (lead._v2Email && lead._v2Email.profil) || '';
        if(!profil) {
            const profilMatch = lead.email_objet ? lead.email_objet.match(/^(Profil [A-D])/i) : null;
            profil = profilMatch ? profilMatch[1] : '';
        }
        const v2Step = (lead._v2Email && lead._v2Email.step > 0) ? lead._v2Email : null;
        const previewHtml = lead.email_corps ? lead.email_corps.replace(/"/g, '&quot;') : '';
        return `
        <div class="panel-section" style="background:var(--surface2);padding:20px;border-radius:12px;margin-bottom:16px">
            <div style="display:flex;align-items:center;gap:14px;margin-bottom:12px">
                <div style="width:48px;height:48px;background:var(--accent);color:white;border-radius:12px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:20px">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
                </div>
                <div style="flex:1">
                    ${profil ? `<div style="font-size:11px;color:var(--accent);font-weight:600;margin-bottom:4px">${escHtml(profil)}</div>` : ''}
                    <div style="font-weight:600;font-size:15px;color:var(--ink)">${escHtml(emailSubject)}</div>
                    <div style="font-size:12px;color:${hasEmail ? 'var(--accent)' : 'var(--ink3)'};margin-top:2px">${hasEmail ? 'Email généré' : 'Non généré'}</div>
                    ${v2Step ? `<div style="font-size:11px;color:#f59e0b;margin-top:2px;font-weight:600">Aperçu — ${escHtml(v2Step.step_label)}</div>` : ''}
                    ${(lead.lien_rapport && lead.lien_rapport.startsWith('http')) ? `<a href="${escHtml(lead.lien_rapport)}" target="_blank" style="font-size:11px;color:var(--blue);margin-top:3px;display:block">Rapport en ligne</a>` : ''}
                </div>
            </div>
        </div>
<div class="panel-section">
            <div style="display:flex;gap:8px;flex-wrap:wrap">
                ${hasEmail ? `
                    <button class="btn bg1 sm" style="font-size:14px;padding:10px 16px" onclick="previewEmail(${lead.id})">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
                        Prévisualiser
                    </button>
                    <button class="btn bg1 sm" style="font-size:14px;padding:10px 16px" onclick="openEmailEditor(${lead.id})">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        &#201;diter
                    </button>
                    <button class="btn bp1 sm" style="font-size:14px;padding:10px 16px" onclick="sendTestEmail(${lead.id})">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M22 2 11 13"/><path d="M22 2-9 19l-5-5"/></svg>
                        Envoyer test
                    </button>
                    <button class="btn bp1 sm" style="font-size:14px;padding:10px 16px;background:#059669;border-color:#059669" onclick="panelSendEmail(${lead.id})">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M22 2 11 13"/><path d="M22 2-9 19l-5-5"/></svg>
                        Envoyer le mail
                    </button>
                ` : ''}
                <button class="btn bp1 sm" style="font-size:14px;padding:10px 16px" onclick="generateEmailForLead(${lead.id})">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
                    ${hasEmail ? 'R&#233;g&#233;n&#233;rer' : 'G&#233;n&#233;rer'}
                </button>
            </div>
        </div>
${hasEmail ? `
        <div class="panel-section">
            <h4 style="font-size:11px;font-weight:700;color:var(--ink3);margin-bottom:10px;text-transform:uppercase;letter-spacing:0.5px">Preview</h4>
            <iframe id="email-preview-iframe" class="email-preview-frame" style="height:500px;width:100%;border:1px solid var(--border);border-radius:8px"></iframe>
        </div>
        ` : ''}
        ${_ulPanelIsWebLead(lead) ? `
        <div class="panel-section">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
                <h4 style="font-size:11px;font-weight:700;color:var(--ink3);margin:0;text-transform:uppercase;letter-spacing:0.5px">Capture du template inséré dans le mail</h4>
                <button class="btn bg2 sm" style="font-size:11px;padding:5px 10px" onclick="window.IaActions && IaActions.leadMaquette(${lead.id}).then(d=>{if(d&&d.files&&d.files.length){ if(window.dialogOpenMaquette) dialogOpenMaquette(${lead.id}); else window.open('/api/ia/maquettes/'+encodeURIComponent(d.liste)+'/'+encodeURIComponent(${lead.id})+'/index.html','_blank'); } else _t ? _t('Aucune maquette générée pour ce lead.','warning') : alert('Aucune maquette générée pour ce lead.');})">Voir la maquette</button>
            </div>
            <div id="email-maq-${lead.id}" style="background:#f8fafc;border:1px dashed #cbd5e1;border-radius:10px;padding:16px;text-align:center;color:var(--ink3);font-size:12px">Chargement de la capture…</div>
        </div>
        ` : ''}
        `;
    }

    async function _setEmailPreviewSrc(lead) {
        const iframe = document.getElementById('email-preview-iframe');
        if (!iframe) return;
        let html = (lead._v2Email && lead._v2Email.corps) || null;
        if (!html && lead.id) {
            try {
                const r = await fetch('/api/v2/leads/' + lead.id + '/email', { cache: 'no-store' });
                const d = await r.json();
                if (d && d.success && d.email && d.email.corps) html = d.email.corps;
            } catch (e) { html = null; }
            if (!iframe.isConnected) return;
        }
        if (!html && lead.email_corps) html = lead.email_corps;
        if (!html) return;
        const blob = new Blob([html], { type: 'text/html' });
        const url = URL.createObjectURL(blob);
        iframe.src = url;
        iframe.onload = () => URL.revokeObjectURL(url);
    }

    function _ulPanelTraitement(lead) {
        const labels = _ul.statutLabels || {};
        const transitions = _ul.transitions || {};
        const st = lead.statut || 'qualifie';
        const colorMap = {
            qualifie:'#3b82f6', en_sequence:'#06b6d4', relance_1:'#06b6d4', relance_2:'#f59e0b',
            relance_3:'#f97316', sans_reponse:'#64748b', a_traiter_humain:'#a855f7',
            rdv_obtenu:'#10b981', pas_interesse:'#ef4444', a_relancer_plus_tard:'#8b5cf6',
            ne_plus_contacter:'#6b7280', adresse_invalide:'#ef4444',
        };
        const col = colorMap[st] || '#64748b';
        const next = (transitions[st] || [])
            .filter(s => s !== st && s !== 'ne_plus_contacter' && s !== 'adresse_invalide');
        const opts = next.map(s => `<option value="${s}">${labels[s] || s}</option>`).join('');

        return `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid #f1f5f9">
            <span style="font-size:12px;color:var(--ink3)">Statut actuel</span>
            <span style="font-size:12px;font-weight:700;color:${col};background:${col}15;padding:4px 10px;border-radius:6px">${escHtml(labels[st] || st)}</span>
        </div>
        ${opts ? `
        <div style="display:flex;gap:8px;align-items:center;padding:10px 0">
            <span style="font-size:12px;color:var(--ink3);flex-shrink:0">Faire évoluer :</span>
            <select class="inp sm" style="flex:1;padding:6px 8px;font-size:12px"
                onchange="unifiedLeadsChangeStatut(${lead.id}, this.value); this.selectedIndex=0; setTimeout(()=>{ if(window.openLeadPanel) openLeadPanel(${lead.id}, 'suivi'); }, 600);">
                <option value="">→ Traitement suivant</option>${opts}
            </select>
        </div>` : `
        <div style="font-size:12px;color:var(--ink3);padding:10px 0">Aucune transition possible (état final).</div>`}
        ${lead.statut_prospection ? `<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0">
            <span style="font-size:12px;color:var(--ink3)">Prospection</span>
            <span style="font-size:12px;font-weight:600;color:#3b82f6">${escHtml(lead.statut_prospection)}</span>
        </div>` : ''}
        `;
    }

    function renderSuiviPanel(lead) {
        const thread = Array.isArray(lead.thread) ? lead.thread : [];
        const hasThread = thread.length > 0;
        const statutColor = { envoye:'#3b82f6', delivered:'#10b981', bounced:'#ef4444', spam:'#f97316', scheduled:'#6366f1', recu:'#10b981' };
        const defaultSubject = lead.email_objet ? (lead.email_objet.toLowerCase().startsWith('re:') ? lead.email_objet : `Re: ${lead.email_objet}`) : 'Re: Notre échange';

        function _cleanUiText(txt) {
            if (!txt) return { clean: '', quote: '' };
            const qPatterns = [
                /(?:\r?\n|^|\s+)(?:Le\s+[\s\S]+?\s+a\s+[eé]crit\s*:)/i,
                /(?:\r?\n|^|\s+)(?:On\s+[\s\S]+?\s+wrote\s*:)/i,
                /(?:\r?\n|^|\s+)[-]{2,}\s*(?:Original Message|Message d'origine|Forwarded message)\s*[-]{2,}/i,
                /(?:\r?\n|^|\s+)(?:De\s*:[^\n]+(?:\r?\n|\s+)Envoy[eé]\s*:[^\n]+)/i,
                /(?:\r?\n|^|\s+)(?:From\s*:[^\n]+(?:\r?\n|\s+)Sent\s*:[^\n]+)/i,
                /(?:\r?\n|^)\s*>[^\n]*/
            ];
            let pos = txt.length;
            for (const p of qPatterns) {
                const m = txt.match(p);
                if (m && m.index < pos) pos = m.index;
            }
            return {
                clean: txt.slice(0, pos).trim(),
                quote: txt.slice(pos).trim()
            };
        }

        const threadCards = thread.map((t, idx) => {
            const isInbound = t.direction === 'in' || t.event_type === 'reponse';
            const bg = isInbound ? 'rgba(16,185,129,0.06)' : 'var(--surface2)';
            const border = isInbound ? 'rgba(16,185,129,0.3)' : 'var(--border)';
            const tagColor = isInbound ? '#10b981' : '#3b82f6';
            const icon = isInbound ? '💬' : (idx === 0 ? '✉️' : '🔄');
            const dateStr = (t.sent_at || t.created_at || '').replace('T', ' ').slice(0, 16);
            
            const rawBody = (t.corps || t.snippet || '').trim();
            const uiCleaned = isInbound ? _cleanUiText(rawBody) : { clean: rawBody, quote: '' };
            const bodyClean = uiCleaned.clean || rawBody;
            const quoteText = t.quote || uiCleaned.quote;

            return `
            <div style="background:${bg};border:1px solid ${border};border-radius:10px;padding:12px;margin-bottom:10px;display:flex;flex-direction:column;gap:6px">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:4px">
                    <div style="display:flex;align-items:center;gap:6px">
                        <span style="font-size:13px">${icon}</span>
                        <span style="font-size:11px;font-weight:700;color:${tagColor};text-transform:uppercase;letter-spacing:.04em">${escHtml(t.step_label || 'Message')}</span>
                        ${isInbound ? '<span class="status-badge ok" style="font-size:10px;padding:1px 6px">Réponse prospect</span>' : ''}
                    </div>
                    <span style="font-size:11px;color:var(--ink3)">${escHtml(dateStr)}</span>
                </div>
                ${t.subject ? `<div style="font-size:12px;font-weight:600;color:var(--ink1)">« ${escHtml(t.subject)} »</div>` : ''}
                ${bodyClean ? `
                <div style="font-size:12px;line-height:1.55;color:var(--ink);white-space:pre-wrap;background:${isInbound ? 'rgba(255,255,255,0.7)' : 'rgba(0,0,0,0.02)'};padding:8px 10px;border-radius:6px;max-height:220px;overflow-y:auto;border:${isInbound ? '1px solid rgba(16,185,129,0.2)' : 'none'}">
                    ${escHtml(bodyClean)}
                </div>` : ''}
                ${quoteText ? `
                <details style="margin-top:2px;font-size:11px;color:var(--ink3)">
                    <summary style="cursor:pointer;opacity:0.75;padding:2px 0;user-select:none">💬 Afficher l'historique cité...</summary>
                    <div style="font-size:11px;line-height:1.45;color:var(--ink3);white-space:pre-wrap;background:rgba(0,0,0,0.03);padding:6px 8px;border-radius:6px;margin-top:4px;max-height:130px;overflow-y:auto">
                        ${escHtml(quoteText)}
                    </div>
                </details>` : ''}
                <div style="display:flex;align-items:center;justify-content:space-between;font-size:11px;color:var(--ink3);margin-top:2px">
                    <div>${t.from_addr ? `De : ${escHtml(t.from_addr)}` : ''}</div>
                    <div style="display:flex;align-items:center;gap:8px">
                        ${t.is_opened ? '<span style="color:#10b981;font-weight:600" title="Email ouvert">👁 Ouvert</span>' : ''}
                        ${t.is_clicked ? '<span style="color:#3b82f6;font-weight:600" title="Lien cliqué">🔗 Cliqué</span>' : ''}
                        <span style="color:${statutColor[t.email_status] || 'var(--ink3)'};font-weight:600">${escHtml(t.email_status || 'envoyé')}</span>
                    </div>
                </div>
            </div>`;
        }).join('');

        return `
        <div class="panel-section" style="margin-bottom:14px">
            <h4 style="font-size:10px;font-weight:700;color:var(--ink3);margin-bottom:12px;text-transform:uppercase;letter-spacing:.06em">Niveau de traitement & Statut</h4>
            ${_ulPanelTraitement(lead)}
        </div>

        <div class="panel-section" style="margin-bottom:14px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
                <h4 style="font-size:10px;font-weight:700;color:var(--ink3);margin:0;text-transform:uppercase;letter-spacing:.06em">
                    Fil de discussion (${thread.length} échange${thread.length > 1 ? 's' : ''})
                </h4>
                <button class="btn bg1 sm" style="font-size:11px;padding:3px 8px" onclick="loadPanelContent(${lead.id}, 'suivi')" title="Actualiser le fil">🔄 Actualiser</button>
            </div>
            ${hasThread ? `
            <div style="display:flex;flex-direction:column">
                ${threadCards}
            </div>` : `
            <div style="text-align:center;padding:16px;background:var(--surface2);border-radius:10px;color:var(--ink3);font-size:12px">
                Aucun email échangé pour l'instant avec ce prospect.
            </div>`}
        </div>

        <!-- Zone de réponse / Nouveau message -->
        <div class="panel-section" style="margin-bottom:14px;background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:14px">
            <h4 style="font-size:10px;font-weight:700;color:var(--accent);margin-bottom:10px;text-transform:uppercase;letter-spacing:.06em;display:flex;align-items:center;gap:6px">
                <span>✉️</span> Répondre / Nouveau message direct
            </h4>
            <div style="display:flex;flex-direction:column;gap:8px">
                <div>
                    <label style="font-size:11px;color:var(--ink3);font-weight:600;display:block;margin-bottom:3px">Objet du message</label>
                    <input id="suivi-reply-subject-${lead.id}" type="text" value="${escHtml(defaultSubject)}"
                           style="width:100%;font-size:12px;padding:6px 10px;background:var(--surface);border:1px solid var(--border);border-radius:6px;color:var(--ink);box-sizing:border-box">
                </div>
                <div>
                    <label style="font-size:11px;color:var(--ink3);font-weight:600;display:block;margin-bottom:3px">Corps de l'email</label>
                    <textarea id="suivi-reply-body-${lead.id}" rows="4" placeholder="Tapez votre message pour ce prospect..."
                              style="width:100%;font-size:12px;line-height:1.5;padding:8px 10px;background:var(--surface);border:1px solid var(--border);border-radius:6px;color:var(--ink);resize:vertical;box-sizing:border-box"></textarea>
                </div>
                <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:4px">
                    <button id="suivi-reply-btn-${lead.id}" class="btn bp1 sm" style="font-size:12px;padding:7px 14px;font-weight:600"
                            onclick="window.sendLeadDirectReply(${lead.id})">
                        ✈️ Envoyer le message
                    </button>
                </div>
            </div>
        </div>

        <div class="panel-section">
            <h4 style="font-size:10px;font-weight:700;color:var(--ink3);margin-bottom:12px;text-transform:uppercase;letter-spacing:.06em">Actions rapides de qualification</h4>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
                <button class="btn bp1 sm" style="font-size:12px;padding:8px" onclick="unifiedLeadsChangeStatut(${lead.id},'rdv_obtenu');loadPanelContent(${lead.id},'suivi')">
                    ✅ RDV obtenu
                </button>
                <button class="btn bg1 sm" style="font-size:12px;padding:8px" onclick="unifiedLeadsChangeStatut(${lead.id},'a_relancer_plus_tard');loadPanelContent(${lead.id},'suivi')">
                    ⏳ À relancer + tard
                </button>
                <button class="btn bg1 sm" style="font-size:12px;padding:8px" onclick="unifiedLeadsChangeStatut(${lead.id},'pas_interesse');loadPanelContent(${lead.id},'suivi')">
                    ✖ Pas intéressé
                </button>
                <button class="btn bd sm" style="font-size:12px;padding:8px" onclick="unifiedLeadsChangeStatut(${lead.id},'ne_plus_contacter');loadPanelContent(${lead.id},'suivi')">
                    🚫 Ne plus contacter
                </button>
            </div>
        </div>`;
    }

    // Helper global pour envoyer une réponse directe depuis le panneau suivi
    window.sendLeadDirectReply = async function sendLeadDirectReply(leadId) {
        const subEl = document.getElementById('suivi-reply-subject-' + leadId);
        const bodyEl = document.getElementById('suivi-reply-body-' + leadId);
        const btn = document.getElementById('suivi-reply-btn-' + leadId);

        const subject = subEl ? subEl.value.trim() : '';
        const body = bodyEl ? bodyEl.value.trim() : '';

        if (!body) {
            if (typeof _t === 'function') _t('Veuillez saisir un corps de message', 'warning');
            else alert('Veuillez saisir un corps de message');
            if (bodyEl) bodyEl.focus();
            return;
        }

        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Envoi en cours...';
        }

        try {
            const resp = await fetch('/api/v2/leads/' + leadId + '/reply', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ subject: subject, body: body }),
            });
            const data = await resp.json();
            if (data.success) {
                if (typeof _t === 'function') _t('Email envoyé avec succès !', 'success');
                if (bodyEl) bodyEl.value = '';
                // Recharger le panneau suivi pour voir le message apparaître immédiatement dans le fil
                loadPanelContent(leadId, 'suivi');
            } else {
                if (typeof _t === 'function') _t('Erreur : ' + (data.error || 'Échec envoi'), 'error');
                else alert('Erreur : ' + (data.error || 'Échec envoi'));
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = '✈️ Envoyer le message';
                }
            }
        } catch (e) {
            if (typeof _t === 'function') _t('Erreur réseau : ' + e.message, 'error');
            else alert('Erreur réseau : ' + e.message);
            if (btn) {
                btn.disabled = false;
                btn.textContent = '✈️ Envoyer le message';
            }
        }
    };

    window.openLeadPanel = openLeadPanel;
    window.closeSidePanel = closeSidePanel;
    window.switchPanelTab = switchPanelTab;
    window.loadPanelContent = loadPanelContent;
    window.renderSuiviPanel = renderSuiviPanel;
}

// ---------------------------------------------------------------------------

function _ulActions(l) {
    const b = [];
    // Clic sur la ligne = panneau détail (openLeadPanel) → pas de bouton « 👁 » redondant.
    b.push(`<button class="ul-act" onclick="unifiedLeadsOpenEdit(${l.id})" title="Modifier le prospect" aria-label="Modifier">✏️</button>`);
    // Actions IA par objectif : uniquement Web (général → pas de qualif/maquette IA).
    const isWeb = (l.objectif || ((l.campagne_id) ? 'general' : '')) === 'web';
    if (_ulIsV2() && isWeb) {
        b.push(`<button class="ul-act accent" onclick="window.IaActions && IaActions.qualifyLead(${l.id})" title="Qualification IA du lead" aria-label="Qualifier">✨</button>`);
        b.push(`<button class="ul-act accent" onclick="window.IaActions && IaActions.maquetteLead(${l.id})" title="Maquette web (PROMPT/<id>/)" aria-label="Maquette">🖼</button>`);
    }
    if (l.pipeline === 'sniper' && l.statut_prospection === 'repondu' && l.audit_id)
        b.push(`<button class="ul-act wide accent" onclick="sniperSendStep2(${l.audit_id})" title="Envoyer le rapport (Step 2)">Step 2</button>`);
    if (l.lien_rapport)
        b.push(`<a href="${_ulEsc(l.lien_rapport)}" target="_blank" class="ul-act wide" title="Ouvrir le rapport d'audit">Rapport</a>`);
    if (!_ulIsV2() && l.pipeline === 'maps') {
        const canAudit = !l.audit_id || l.statut === 'en_attente' || l.statut === 'scrape';
        b.push(`<button class="ul-act wide" onclick="auditLead(${l.id})" title="${canAudit ? "Lancer l'audit" : "Relancer l'audit"}">${canAudit ? 'Auditer' : '🔄'}</button>`);
    }
    b.push(`<button class="ul-act ${l.ecarte ? 'revert' : 'warn'}" onclick="ulToggleEcarte(${l.id})" title="${l.ecarte ? 'Réintégrer' : "Écarter des flux d'envoi"}" aria-label="Écarter">${l.ecarte ? '↩' : '🚫'}</button>`);
    b.push(`<button class="ul-act ${l.desinscrit ? 'revert' : 'danger'}" onclick="ulToggleDesinscrit(${l.id})" title="${l.desinscrit ? 'Réactiver' : "Désinscrire (opposition)"}" aria-label="Désinscrire">${l.desinscrit ? '✓' : '✋'}</button>`);
    return `<div class="row-actions">${b.join('')}</div>`;
}

// ─── Modal édition ──────────────────────────────────────────────────────────

function _ulPopulateEditForm(l) {
    _ul.editingId = l.id;
    const v2 = !!_ulIsV2();
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
        if (lbl) lbl.textContent = `Campagne · ${l.campagne_nom || _ul.v2CampagneNom || '—'}`;
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
            const url = _ulIsV2() ? `/api/v2/leads/${id}` : `/api/leads/${id}`;
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
    if (_ulIsV2()) {
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
            if (window.ListesModule && typeof window.ListesModule.onProspectsChanged === 'function') window.ListesModule.onProspectsChanged();
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
        if (_ulIsV2()) {
            await fetch(`/api/v2/leads/${id}`, { method: 'DELETE' });
            closeModal?.('modal-ul-edit'); showToast?.('Lead supprimé', 'success');
            unifiedLeadsLoad(_ul.page);
            if (window.ListesModule && typeof window.ListesModule.onProspectsChanged === 'function') window.ListesModule.onProspectsChanged();
            if (typeof window.CampagnesModule !== 'undefined') window.CampagnesModule.refreshStats();
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
        if (_ulIsV2()) {
            await Promise.all(ids.map(id => fetch(`/api/v2/leads/${id}`, { method: 'DELETE' })));
            showToast?.(`${ids.length} lead(s) supprimé(s)`, 'success');
            unifiedLeadsLoad(_ul.page);
            if (typeof window.CampagnesModule !== 'undefined') window.CampagnesModule.refreshStats();
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
    return `<span class="ul-src" style="--c:${c}" title="Source : ${l}">${l}</span>`;
}
function _ulSourceLabel(s) { return (_SOURCE_MAP[s] || ['', '?'])[1]; }
function _ulStatutBadge(d) {
    if (!d) return '<span class="score-mut">—</span>';
    return `<span class="ul-stat-badge" style="--c:${d.color}" title="${d.label}">${d.label}</span>`;
}
function _ulEsc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function _ulSetVal(id, v) { const el = document.getElementById(id); if (el) el.value = v ?? ''; }
function _ulGetVal(id) { return document.getElementById(id)?.value?.trim() ?? ''; }

// ─── KANBAN (Phase 4.1) ──────────────────────────────────────────────────────

function setLeadsView(view) {
    _ul.view = view;
    document.getElementById('leads-list-view').style.display = view === 'list' ? '' : 'none';
    document.getElementById('leads-kanban-view').style.display = view === 'kanban' ? '' : 'none';

    document.getElementById('view-list').classList.toggle('active', view === 'list');
    document.getElementById('view-kanban').classList.toggle('active', view === 'kanban');

    unifiedLeadsLoad(1);
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

// ─── KANBAN v2 partagé (onglets Leads ET Listes) ────────────────────────────
// Pipeline compact : les colonnes regroupent les statuts de la machine à états.
const _V2_KANBAN_COLUMNS = [
    { id: 'qualifie', label: 'Qualifiés', statuts: ['qualifie'] },
    { id: 'en_sequence', label: 'En séquence', statuts: ['en_sequence', 'relance_1', 'relance_2', 'relance_3'] },
    { id: 'a_traiter_humain', label: 'À traiter', statuts: ['a_traiter_humain'] },
    { id: 'a_relancer_plus_tard', label: 'À relancer', statuts: ['a_relancer_plus_tard'] },
    { id: 'sans_reponse', label: 'Sans réponse', statuts: ['sans_reponse'] },
    { id: 'rdv_obtenu', label: 'RDV', statuts: ['rdv_obtenu'] },
    { id: 'clos', label: 'Clos', statuts: ['pas_interesse', 'ne_plus_contacter', 'adresse_invalide'] },
];

// Progression de la chaîne séquence (pour la cible du drag&drop).
const _SEQ_ORDER = ['qualifie', 'en_sequence', 'relance_1', 'relance_2', 'relance_3'];

function _v2ColForStatut(statut) {
    const col = _V2_KANBAN_COLUMNS.find(c => c.statuts.includes(statut));
    return col ? col.id : 'qualifie';
}

// Statut cible légal pour un drop sur une colonne (via VALID_TRANSITIONS).
window._v2KanbanDropTarget = function (leadStatut, colId) {
    let transitions = (_ul.transitions && Object.keys(_ul.transitions).length) ? _ul.transitions : {};
    if (!Object.keys(transitions).length && window.ListesModule && typeof window.ListesModule.getTransitions === 'function') {
        transitions = window.ListesModule.getTransitions() || {};
    }
    const allowed = new Set(transitions[leadStatut] || []);
    if (colId === 'clos') return allowed.has('ne_plus_contacter') ? 'ne_plus_contacter' : null;
    const col = _V2_KANBAN_COLUMNS.find(c => c.id === colId);
    if (!col) return null;
    if (colId === 'en_sequence') {
        const idx = _SEQ_ORDER.indexOf(leadStatut);
        if (idx >= 0) {
            const next = _SEQ_ORDER[idx + 1];
            if (next && allowed.has(next)) return next;
        }
    }
    for (const s of col.statuts) {
        if (allowed.has(s)) return s;
    }
    return null;
};

// Point d'envoi de la transition Kanban v2.
window._v2KanbanDrop = async function (leadId, newStatus, opts) {
    opts = opts || {};
    try {
        const r = await fetch(`/api/v2/leads/${leadId}/statut`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ statut: newStatus, reason: 'kanban (UI)' }),
        });
        const d = await r.json();
        if (!d.success) throw new Error(d.error || 'transition refusée');
        showToast?.(`Statut → ${(_ul.statutLabels && _ul.statutLabels[newStatus]) || newStatus}`, 'success');
        if (typeof opts.onChanged === 'function') opts.onChanged(newStatus);
    } catch (e) {
        console.error('[Kanban Drop v2]', e);
        showToast?.('Erreur : ' + e.message, 'error');
        if (typeof opts.onFailed === 'function') opts.onFailed();
    }
};

// Carte Kanban v2 (fonctionne pour un prospect v2 ET un lead legacy enrichi).
window._ulKanbanV2Card = function (l) {
    const nom = l.nom || l.entreprise || '—';
    const isWeb = (l.objectif || 'general') === 'web';
    const score = (l.score != null && l.score !== '') ? l.score : (l.score_performance || l.mobile_score || 0);
    const scoreClass = score >= 80 ? 'hot' : score >= 50 ? 'warm' : 'cold';
    const email = (l.email_valide && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(l.email_valide)) ? l.email_valide : (l.email || '');
    const meta = [l.ville, l.secteur || l.category || l.categorie].filter(Boolean).join(' · ');
    const chips = [];
    chips.push(`<span class="kc-chip ${isWeb ? 'kc-chip-web' : 'kc-chip-general'}">${isWeb ? 'Web' : 'Gén.'}</span>`);
    if (l.campagne_nom) chips.push(`<span class="kc-chip">${_ulEsc(l.campagne_nom)}</span>`);
    if (l.liste_nom) chips.push(`<span class="kc-chip">${_ulEsc(l.liste_nom)}</span>`);
    if (l.ecarte) chips.push(`<span class="kc-chip kc-chip-ecarte">écarté</span>`);
    const footerScore = isWeb
        ? (score ? `<div class="kc-score ${scoreClass}">${score}%</div>` : '<div></div>')
        : (parseFloat(l.rating) ? `<div class="kc-score hot">${parseFloat(l.rating).toFixed(1)} ⭐</div>` : '<div></div>');
    return `
        <div class="kanban-card" data-id="${l.id}" onclick="window._ulKanbanCardClick(${l.id})">
            <div class="kc-name">${_ulEsc(nom)}</div>
            ${meta ? `<div class="kc-meta">${_ulEsc(meta)}</div>` : ''}
            ${email ? `<div style="font-size:11px;color:var(--ink2);margin-bottom:8px">${_ulEsc(email)}</div>` : ''}
            ${chips.length ? `<div style="margin-bottom:6px">${chips.join('')}</div>` : ''}
            <div class="kc-footer">
                ${footerScore}
                <div style="font-size:10px;color:var(--ink3)">${_ulEsc(l.source || '')}</div>
            </div>
        </div>`;
};

// Hook de clic sur une carte : chaque onglet pose son handler (Lead panel / détail liste).
window._ulKanbanCardClick = function (leadId) {
    if (typeof window._ulKanbanCardClickHandler === 'function') window._ulKanbanCardClickHandler(leadId);
};

// Board Kanban partagé (Leads + Listes). opts :
//   prefix    : préfixe d'id des colonnes (plusieurs boards possibles en DOM)
//   colOf     : (lead) => colonneId (par défaut mapping statut v2)
//   onChanged : (newStatus) => après une transition réussie
//   onFailed  : () => après un refus / une erreur (reload pour revert)
window.renderKanbanBoard = function (rootEl, leads, opts) {
    if (!rootEl) return;
    opts = opts || {};
    const prefix = opts.prefix || 'kb';

    rootEl.innerHTML = '<div class="kanban-board">' +
        _V2_KANBAN_COLUMNS.map((c, i) => `
            <div class="kanban-col" data-status="${c.id}">
                <div class="kanban-col-header">
                    <span class="kanban-col-title">${c.label}</span>
                    <span class="kanban-col-count">0</span>
                </div>
                <div class="kanban-cards" id="${prefix}-cards-${i}" data-col="${c.id}"></div>
            </div>`).join('') +
        '</div>';

    const containers = {};
    const htmls = {};
    const counts = {};
    _V2_KANBAN_COLUMNS.forEach(c => {
        containers[c.id] = null;
        htmls[c.id] = [];
        counts[c.id] = 0;
    });
    rootEl.querySelectorAll('.kanban-cards').forEach(el => {
        const colId = el.dataset.col;
        if (containers[colId] !== undefined) containers[colId] = el;
    });

    (leads || []).forEach(l => {
        const colId = (typeof opts.colOf === 'function') ? opts.colOf(l) : _v2ColForStatut(l.statut || 'qualifie');
        const key = containers[colId] ? colId : 'qualifie';
        htmls[key].push(_ulKanbanV2Card ? _ulKanbanV2Card(l) : '');
        counts[key]++;
    });
    Object.keys(htmls).forEach(colId => {
        const el = containers[colId];
        if (el) el.innerHTML = htmls[colId].join('');
    });

    rootEl.querySelectorAll('.kanban-col-count').forEach(el => {
        const colId = el.closest('.kanban-col').dataset.status;
        el.textContent = counts[colId] || 0;
    });

    if (typeof Sortable === 'undefined') return;
    rootEl.querySelectorAll('.kanban-cards').forEach(el => {
        Sortable.create(el, {
            group: 'kanban',
            animation: 150,
            ghostClass: 'sortable-ghost',
            dragClass: 'sortable-drag',
            onEnd: async function (evt) {
                if (evt.from === evt.to) return;
                const leadId = evt.item.dataset.id;
                const toColId = evt.to.dataset.col;
                const lead = (leads || []).find(x => String(x.id) === String(leadId));
                const target = window._v2KanbanDropTarget(lead ? lead.statut : 'qualifie', toColId);
                if (!target) {
                    showToast?.('Transition impossible vers cette colonne', 'error');
                    if (typeof opts.onFailed === 'function') opts.onFailed();
                    return;
                }
                await window._v2KanbanDrop(leadId, target, { onChanged: opts.onChanged, onFailed: opts.onFailed });
            }
        });
    });
};

// Rend le board v2 dans l'onglet Leads (conteneur #leads-kanban-view).
function _ulRenderBoardV2() {
    const root = document.getElementById('leads-kanban-view');
    if (!root) return;
    window._ulKanbanCardClickHandler = (id) => {
        if (typeof window.openLeadPanel === 'function') window.openLeadPanel(id);
    };
    window.renderKanbanBoard(root, _ul.leads, {
        prefix: 'ulkb',
        onChanged: () => unifiedLeadsLoad(_ul.page),
        onFailed: () => unifiedLeadsLoad(_ul.page),
    });
}

