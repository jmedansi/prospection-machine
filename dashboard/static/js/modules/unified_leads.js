/**
 * dashboard/static/js/modules/unified_leads.js
 * Table unifiée Maps + Sniper.
 */

const _ul = { leads: [], page: 1, totalPages: 1, total: 0, editingId: null, view: 'list' };

function unifiedLeadsInit() { unifiedLeadsLoad(); }

async function unifiedLeadsLoad(page = 1) {
    _ul.page = page;
    const tbody = document.getElementById('ul-tbody');
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:24px;color:var(--ink3)">Chargement…</td></tr>`;

    const limit = document.getElementById('ul-filter-limit')?.value || 50;
    const params = new URLSearchParams({ page, limit });
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

    try {
        const r = await fetch(`/api/leads/all?${params}`);
        const d = await r.json();
        if (d.error) {
            tbody.innerHTML = `<tr><td colspan="7" style="color:var(--error);text-align:center;padding:16px">${_ulEsc(d.error)}</td></tr>`;
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
                : `<tr><td colspan="7" style="text-align:center;padding:24px;color:var(--ink3)">Aucun lead</td></tr>`;
        }

        _ulUpdatePagination();
        _ulUpdateCount();
    } catch (e) {
        console.error('[unified_leads]', e);
        if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="color:var(--error);text-align:center;padding:16px">Erreur : ${e.message}</td></tr>`;
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

    const meta = `${srcBadge}${_ulEsc(l.category || l.secteur || 'Prospect')}`;

    return `<tr onclick="openLeadPanel(${l.id})" style="cursor:pointer" class="${_selectedLeadId === l.id ? 'selected' : ''}">
        <td class="col-check" onclick="event.stopPropagation()">
            <input type="checkbox" class="ul-cb lead-cb" data-id="${l.id}" data-nom="${_ulEsc(l.nom)}">
        </td>
        <td class="col-prospect">
            <div class="lead-cell-flex">
                <div class="lead-avatar">${initial}</div>
                <div class="lead-info">
                    ${nomCell}
                    <div class="lead-meta">${meta}</div>
                </div>
            </div>
        </td>
        <td class="col-source" style="font-size:11px;color:var(--ink3)">${_ulEsc(l.ville || '')}</td>
        <td class="col-contact">${_ulContactCell(l)}</td>
        <td class="col-score">${_ulScoreCell(l)}</td>
        <td class="col-statut">${_ulStatutBadge(l.statut_display)}</td>
        <td class="col-actions" style="text-align:right;white-space:nowrap" onclick="event.stopPropagation()">${_ulActions(l)}</td>
    </tr>`;
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

function _ulActions(l) {
    const b = [];
    b.push(`<button class="btn bg1 sm" onclick="unifiedLeadsOpenEdit(${l.id})" style="font-size:11px;padding:3px 8px">✏️</button>`);
    if (l.pipeline === 'sniper' && l.statut_prospection === 'repondu' && l.audit_id)
        b.push(`<button class="btn accent sm" onclick="sniperSendStep2(${l.audit_id})" style="font-size:11px;padding:3px 9px">Step 2</button>`);
    if (l.lien_rapport)
        b.push(`<a href="${_ulEsc(l.lien_rapport)}" target="_blank" class="btn bg2 sm" style="font-size:11px;padding:3px 8px">Rapport</a>`);
    if (l.pipeline === 'maps') {
        const canAudit = !l.audit_id || l.statut === 'en_attente' || l.statut === 'scrape';
        b.push(`<button class="btn bg1 sm" onclick="auditLead(${l.id})" style="font-size:11px;padding:3px 9px">${canAudit ? 'Auditer' : '🔄'}</button>`);
    }
    return b.join(' ');
}

// ─── Modal édition ──────────────────────────────────────────────────────────

function unifiedLeadsOpenEdit(id, fallbackCache) {
    let l = _ul.leads.find(x => x.id == id);
    // Fallback: si la vue Leads n'a pas encore été chargée, on pioche dans le cache du panneau latéral
    if (!l && fallbackCache) l = fallbackCache.find(x => x.id == id);
    if (!l) { showToast?.('Lead non trouvé dans le cache, veuillez recharger.', 'error'); return false; }
    _ul.editingId = id;
    _ulSetVal('ul-edit-id', l.id);
    _ulSetVal('ul-edit-nom', l.nom);
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

    const m = document.getElementById('modal-ul-edit');
    if (m) {
        if (typeof openModal === 'function') openModal('modal-ul-edit');
        m.classList.add('active');
        m.style.display = 'flex'; // Force override any inline 'none'
    }
}

async function unifiedLeadsSave() {
    const id = _ul.editingId; if (!id) return;
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
        unifiedLeadsLoad(_ul.page); // rafraîchissement immédiat du tableau
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
        await fetch(`/api/lead/delete?id=${id}`, { method: 'DELETE' });
        closeModal?.('modal-ul-edit'); showToast?.('Lead supprimé', 'success');
        unifiedLeadsLoad(_ul.page);
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
    _ul.view = view;
    document.getElementById('leads-list-view').style.display = view === 'list' ? '' : 'none';
    document.getElementById('leads-kanban-view').style.display = view === 'kanban' ? '' : 'none';

    document.getElementById('view-list').classList.toggle('active', view === 'list');
    document.getElementById('view-kanban').classList.toggle('active', view === 'kanban');

    if (view === 'kanban') renderKanban(_ul.leads);
    else unifiedLeadsLoad(_ul.page);
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

