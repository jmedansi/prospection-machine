/**
 * dashboard/static/js/modules/listes.js
 * Modèle v2 « Campagne → Liste → Prospect » — interface « Listes » de la V6.
 * Ancienne vue restaurée : sidebar avec les listes à gauche (celles de la
 * campagne active choisie dans la topbar, ou toutes groupées par campagne
 * quand « Aucune campagne » est sélectionnée), panneau droit = prospects de
 * la liste sélectionnée (table v2, recherche + pagination, actions v2 :
 * éditer / statut rapide / écarter / désinscrire / retirer / supprimer).
 *
 * Restauré fidèlement au V5 :
 *   • Sidebar : icône et couleur par liste (border-left), bouton ✏️ par item.
 *   • Modal : objectif (général/web), grille d'icônes (emojis), grille de couleurs.
 *   • Header : icône + badge objectif.
 *   • Panneau d'actions repliable (⚡ toggleActions) + « plus d'actions » (▸ toggleToolbar).
 *   • Note de liste enregistrée au blur (textarea auto-resize).
 *   • Table : checkbox (sélection multiple), ID, score, copier email, retrait (→ Corbeille).
 *
 * Câblé sur le sélecteur de campagne (topbar) : `init()` (v6_shell) et
 * `onCampagneChange()` (campagnes.js) rechargent la sidebar quand la campagne
 * active change.
 *
 * DOM cible (sections/listes_v6.html) :
 *   #lists-sidebar-items · #liste-search · #liste-filter-statut
 *   #liste-lead-search · #liste-lead-tbody · #liste-prev/next/page-info
 *   #lists-section-actions · #lists-toolbar-extra · #liste-note
 */
(function () {
    'use strict';

    function esc(s) {
        return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function toast(msg, type) {
        if (typeof window.showToast === 'function') window.showToast(msg, type || 'success');
    }

    function sel(id) { return document.getElementById(id); }

    function emailCell(l) {
        if (!l.email) return '';
        return `<button class="ld-btn ld-ghost" title="Copier l'email" style="font-size:10px;padding:2px 6px;margin-left:2px"
                onclick="event.stopPropagation();event.preventDefault();ListesModule.copyEmail('${esc(l.email).replace(/'/g, "\\'")}')">📋</button>`;
    }

    // ── Helpers réutilisés de unified_leads.js (fallback local défensif) ──
    function statutBadge(d) {
        if (typeof window._ulStatutBadge === 'function') return window._ulStatutBadge(d);
        if (!d) return '<span style="color:var(--ink3)">—</span>';
        return `<span style="background:${d.color}20;color:${d.color};padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600">${d.label}</span>`;
    }

    function contactCell(l) {
        if (typeof window._ulContactCell === 'function') return window._ulContactCell(l);
        const parts = [];
        if (l.ceo_prenom) parts.push(`<span style="font-size:11px;font-weight:600">${esc(l.ceo_prenom)} ${esc(l.ceo_nom || '')}</span>`);
        if (l.email) parts.push(`<a href="mailto:${esc(l.email)}" style="font-size:10px;color:var(--accent);text-decoration:none">✉️ ${esc(l.email)}</a>`);
        return parts.join('<br>');
    }

    function scoreCell(l) {
        if (typeof window._ulScoreCell === 'function') return window._ulScoreCell(l);
        if ((l.objectif || '') === 'general') return '<span style="color:var(--ink3);font-size:10px">—</span>';
        const s = parseFloat(l.score);
        if (s === null || s === undefined || isNaN(s) || s <= 0) return '<span style="color:var(--ink3);font-size:10px">—</span>';
        return `<span style="font-size:12px">${Math.round(s)}<span style="font-size:10px;color:var(--ink3)">/100</span></span>`;
    }

    function avisCell(l) {
        if (typeof window._ulAvisCell === 'function') return window._ulAvisCell(l);
        const r = parseFloat(l.rating) || 0;
        const n = parseInt(l.nb_avis) || 0;
        if (!r && !n) return '<span style="color:var(--ink3)">—</span>';
        return `<span style="font-size:11px;white-space:nowrap">${r ? `${r.toFixed(1)} ⭐` : ''} <span style="color:var(--ink3)">(${n})</span></span>`;
    }

    // ─── Constantes V5 (grilles) ──────────────────────────────────────────
    const EMOJIS = ['📋', '🎯', '✅', '🚀', '✨', '📊', '🏆', '🧲', '🔥', '🌍', '💼', '🛒', '📬', '💡', '🗂'];
    const COLORES = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#3b82f6', '#84cc16', '#f97316', '#0ea5e9', '#64748b'];
    const PICKER_CLS = { icone: 'list-emoji-opt', couleur: 'list-color-opt' };
    const PICKER_ATTR = { icone: 'data-emoji', couleur: 'data-color' };

    // ─── État interne ──────────────────────────────────────────────────────
    const _state = {
        listes: [],
        activeListId: null,
        leads: [],
        page: 1,
        totalPages: 1,
        total: 0,
        leadsSearch: '',
        transitions: {},
        statutLabels: {},
        view: 'list',
        searchDebounce: null,
        editingListId: null,
        importWired: false,
        noteWired: false,
        emojiWired: false,
        colorWired: false,
        objectifWired: false,
        form: { icone: '📋', couleur: '#6366f1', objectif: 'general' },
    };

    const ListesModule = {

        // ─── Campagne active (topbar) ──────────────────────────────
        get campagneId() {
            return (window.CampagnesModule && typeof window.CampagnesModule.currentId !== 'undefined')
                ? window.CampagnesModule.currentId : null;
        },

        get activeList() {
            return _state.listes.find(l => l.id === _state.activeListId) || null;
        },

        get activeId() {
            return _state.activeListId;
        },

        // ─── INIT / chargements ────────────────────────────────────
        async init() {
            if (!sel('lists-sidebar-items')) return;
            await this._loadTransitions();
            await this.load();
            this.render();
            if (_state.activeListId && !_state.leads.length) {
                await this.loadLeads(1);
            }
        },

        async _loadTransitions() {
            try {
                const r = await fetch('/api/v2/statuts/transitions', { cache: 'no-store' });
                const d = await r.json();
                if (d.success) {
                    _state.transitions = d.transitions || {};
                    _state.statutLabels = d.labels || {};
                    this._populateStatutFilter();
                }
            } catch (e) {
                console.error('[listes] transitions', e);
            }
        },

        async load() {
            const params = new URLSearchParams();
            if (this.campagneId) params.set('campagne_id', this.campagneId);
            const statut = sel('liste-filter-statut')?.value || '';
            if (statut) params.set('statut', statut);
            const q = sel('liste-search')?.value?.trim() || '';
            if (q) params.set('search', q);
            try {
                const r = await fetch(`/api/v2/listes?${params.toString()}`);
                const d = await r.json();
                _state.listes = (d && d.listes) || [];
            } catch (e) {
                console.error('[listes] load', e);
                _state.listes = [];
            }
            // La liste active a disparu (filtre, campagne, suppression) → placeholder.
            if (_state.activeListId && !_state.listes.find(l => l.id === _state.activeListId)) {
                this.clearSelection();
            }
            return _state.listes;
        },

        async refresh() {
            if (!sel('lists-sidebar-items')) return;
            await this.load();
            this.render();
            if (_state.activeListId) await this.loadLeads(_state.page);
        },

        /** Rechargé quand la campagne active change (sélecteur topbar). */
        async onCampagneChange() {
            if (!sel('lists-sidebar-items')) return;
            await this.load();
            this.render();
            if (_state.activeListId) await this.loadLeads(_state.page);
        },

        // ─── Sidebar ───────────────────────────────────────────────
        render() {
            const items = sel('lists-sidebar-items');
            if (!items) return;

            if (!_state.listes.length) {
                items.innerHTML = `<div class="lists-empty-state">
                    <div class="lists-empty-icon">📋</div>
                    <div class="lists-empty-title">Aucune liste</div>
                    <div class="lists-empty-desc">Crée ta première liste${this.campagneId ? ' dans cette campagne' : ''}</div>
                </div>`;
                this._updateMobileCount(0);
                return;
            }

            // « Aucune campagne » → groupées par campagne ; sinon uniquement la sienne.
            const grp = new Map();
            for (const l of _state.listes) {
                const k = l.campagne_id ?? 0;
                if (!grp.has(k)) grp.set(k, { nom: l.campagne_nom || '—', listes: [] });
                grp.get(k).listes.push(l);
            }

            const multi = grp.size > 1;
            let html = '';
            for (const g of grp.values()) {
                if (multi) {
                    const t = g.listes.reduce((n, l) => n + (l.nb_leads || 0), 0);
                    html += `<div class="list-sidebar-section">${esc(g.nom)} · ${g.listes.length} · ${t}</div>`;
                }
                html += g.listes.map(lst => this._item(lst)).join('');
            }
            items.innerHTML = html;
            this._updateMobileCount(_state.listes.length);
        },

        _item(l) {
            const active = l.id === _state.activeListId;
            const archived = l.statut === 'archive';
            const color = l.couleur || '#6366f1';
            return `<div class="list-sidebar-item ${active ? 'active' : ''}"
                     style="border-left:3px solid ${color}"
                     onclick="ListesModule.selectList(${l.id})">
                <span class="list-sidebar-icone">${esc(l.icone || '📋')}</span>
                <div class="list-sidebar-info">
                    <div class="list-sidebar-nom" title="${esc(l.nom)}">${esc(l.nom)}</div>
                    <div class="list-sidebar-meta">
                        #${l.id} · ${l.nb_leads || 0} prospect${l.nb_leads !== 1 ? 's' : ''}
                        ${archived ? ' <span class="archived">· archivée</span>' : ''}
                    </div>
                </div>
                <button class="list-sidebar-edit" title="Modifier la liste"
                        onclick="event &amp;&amp; event.stopPropagation(); ListesModule.openEditList(${l.id})">✏️</button>
            </div>`;
        },

        _updateMobileCount(n) {
            const c = sel('lists-mobile-count');
            if (c) {
                c.textContent = n || 0;
                c.style.display = n > 0 ? '' : 'none';
            }
        },

        // ─── Sélection d'une liste ────────────────────────────────
        async selectList(listId) {
            _state.activeListId = listId;
            const lst = this.activeList;
            this.render();

            const ph = sel('lists-placeholder');
            if (ph) ph.style.display = 'none';
            const vw = sel('lists-view');
            if (vw) vw.style.display = '';

            const nom = sel('liste-active-nom');
            if (nom) nom.textContent = lst?.nom || '—';
            const icone = sel('liste-active-icone');
            if (icone) icone.textContent = lst?.icone || '📋';
            const id = sel('liste-active-id');
            if (id) id.textContent = lst ? `#${lst.id}` : '#—';
            const count = sel('liste-active-count');
            if (count) count.textContent = '—';

            const ob = sel('liste-active-objectif');
            if (ob) {
                const isWeb = lst?.objectif === 'web';
                ob.textContent = isWeb ? '🌐 Web' : '🎯 Général';
                ob.style.background = isWeb ? 'rgba(14,165,233,.12)' : 'rgba(99,102,241,.12)';
                ob.style.color = isWeb ? '#0ea5e9' : '#6366f1';
            }

            const cb = sel('liste-active-campagne');
            if (cb) {
                cb.textContent = `🎯 ${lst?.campagne_nom || (this.campagneId ? 'Campagne' : '—')}`;
                cb.style.display = 'inline-block';
            }
            const sb = sel('liste-active-statut');
            if (sb) {
                const archived = lst?.statut === 'archive';
                sb.textContent = archived ? '🗄 archivée' : '● active';
                sb.style.background = archived ? 'rgba(100,116,139,.15)' : 'rgba(16,185,129,.12)';
                sb.style.color = archived ? 'var(--ink3)' : '#10b981';
                sb.style.display = 'inline-block';
            }

            const ls = sel('liste-lead-search');
            if (ls) ls.value = '';
            _state.leadsSearch = '';
            this.loadListNote();
            this._wireImport();
            this._initNoteAutoSave();
            this.closeMobileSidebar();
            this._setSelection([]);
            await this.loadLeads(1);
        },

        clearSelection() {
            _state.activeListId = null;
            _state.leads = [];
            const ph = sel('lists-placeholder');
            if (ph) ph.style.display = '';
            const vw = sel('lists-view');
            if (vw) vw.style.display = 'none';
            const tbody = sel('liste-lead-tbody');
            if (tbody) tbody.innerHTML = `<tr><td colspan="9" class="lists-table-empty">Sélectionne une liste pour voir ses prospects.</td></tr>`;
        },

        // ─── Prospects de la liste active ─────────────────────────
        async loadLeads(page = 1) {
            if (!_state.activeListId) return;
            _state.page = page;

            const tbody = sel('liste-lead-tbody');
            if (tbody && _state.view !== 'kanban') tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:24px;color:var(--ink3)">Chargement…</td></tr>`;

            const params = new URLSearchParams({
                page,
                limit: _state.view === 'kanban' ? 10000 : 50,
            });
            if (_state.leadsSearch) params.set('search', _state.leadsSearch);
            const statut = sel('liste-filtre-statut')?.value || '';
            if (statut) params.set('statut', statut);
            const email = sel('liste-filtre-email')?.value || '';
            if (email === 'with' || email === 'without') params.set('email', email);
            const ecarte = sel('liste-filtre-ecarte')?.value || '';
            if (ecarte === '0') params.set('ecarte', '0');

            try {
                const r = await fetch(`/api/v2/listes/${_state.activeListId}/leads?${params}`);
                const d = await r.json();
                if (d.error) throw new Error(d.error);

                _state.leads = d.leads || [];
                _state.page = d.page;
                _state.totalPages = d.total_pages;
                _state.total = d.total;

                const countEl = sel('liste-active-count');
                if (countEl) countEl.textContent = `${d.total} prospect${d.total > 1 ? 's' : ''}`;

                // Sync du compteur dans la sidebar
                const lst = this.activeList;
                if (lst && typeof lst === 'object') lst.nb_leads = d.total;
                this.render();

                if (_state.view === 'kanban') {
                    this._renderKanban();
                } else if (tbody) {
                    tbody.innerHTML = this._rows(_state.leads);
                }
                this._setSelection([]);
                this._updatePagination();
            } catch (e) {
                console.error('[listes] loadLeads', e);
                if (tbody) tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:24px;color:var(--ink3)">Erreur de chargement.</td></tr>`;
            }
        },

        _rows(leads) {
            if (!leads.length) {
                return `<tr><td colspan="9" class="lists-table-empty">Aucun prospect dans cette liste.</td></tr>`;
            }
            return leads.map(l => this._row(l)).join('');
        },

        _row(l) {
            const nom = esc(l.nom || l.entreprise || '—');
            const initial = nom.charAt(0).toUpperCase();
            const siteUrl = l.site_web ? esc(l.site_web) : '';
            const nomCell = siteUrl
                ? `<a href="${siteUrl}" target="_blank" class="lead-name" style="color:var(--ink1);text-decoration:none">${nom}</a>`
                : `<strong class="lead-name">${nom}</strong>`;

            let avScale = '';
            if (typeof window._ulAvatarColor === 'function') {
                const c = window._ulAvatarColor(l.nom || '');
                avScale = ` style="background:${c.bg};color:${c.fg}"`;
            }

            // Exclusions : pastilles « hors flux », distinctes des statuts du cycle de vie.
            const flags = [];
            if (l.ecarte) flags.push('<span class="ul-xp" title="Exclu des flux d\'envoi">⛔ écarté</span>');
            if (l.desinscrit) flags.push('<span class="ul-xp ul-xp-opp" title="Opposition / désinscrit">✋ désinscrit</span>');
            const objChip = typeof window._ulObjectifChip === 'function'
                ? window._ulObjectifChip(l)
                : (l.objectif === 'web'
                    ? '<span class="ul-objchip web">Web</span>'
                    : '<span class="ul-objchip gen">Gén.</span>');
            const meta = `${objChip}${esc(l.secteur || l.categorie || l.category || '')}${flags.length ? ' ' + flags.join(' ') : ''}`;

            return `<tr onclick="ListesModule.openDetail(${l.id})" style="cursor:pointer" class="${(l.ecarte || l.desinscrit) ? 'ul-flagged' : ''}">
                <td class="col-check" onclick="event &amp;&amp; event.stopPropagation()">
                    <input type="checkbox" data-id="${l.id}" onchange="ListesModule._onCheckChange(this)">
                </td>
                <td class="col-id">#${l.id}</td>
                <td class="col-prospect">
                    <div class="lead-cell-flex">
                        <div class="lead-avatar"${avScale}>${initial}</div>
                        <div class="lead-info">
                            ${nomCell}
                            <div class="lead-meta">${meta || '—'}</div>
                        </div>
                    </div>
                </td>
                <td class="col-source">${esc(l.ville || '')}</td>
                <td class="col-contact">
                    <div>${contactCell(l)}${emailCell(l)}</div>
                </td>
                <td class="col-score">${scoreCell(l)}</td>
                <td class="col-avis">${avisCell(l)}</td>
                <td class="col-statut">
                    <div class="lead-statut-inline">${statutBadge(l.statut_display)}</div>
                </td>
                <td class="col-actions" onclick="event &amp;&amp; event.stopPropagation()">${this._rowActions(l)}</td>
            </tr>`;
        },

        // ─── Sélection multiple ───────────────────────────────────
        _checkedIds() {
            return Array.from(document.querySelectorAll('#liste-lead-tbody input[type=checkbox]:checked'))
                .map(cb => parseInt(cb.getAttribute('data-id'), 10))
                .filter(Boolean);
        },

        _setSelection(ids) {
            const set = new Set((ids || []).map(String));
            document.querySelectorAll('#liste-lead-tbody input[type=checkbox]').forEach(cb => {
                cb.checked = set.has(cb.getAttribute('data-id'));
            });
            this._updateRemoveBtn();
        },

        toggleAll(cb) {
            document.querySelectorAll('#liste-lead-tbody input[type=checkbox]').forEach(c => {
                c.checked = cb.checked;
            });
            this._updateRemoveBtn();
        },

        _onCheckChange(_cb) {
            this._updateRemoveBtn();
        },

        _updateRemoveBtn() {
            const btn = sel('liste-retirer-selection');
            if (!btn) return;
            const n = this._checkedIds().length;
            btn.disabled = n === 0;
            btn.textContent = n > 0 ? `🗑 Retirer (${n})` : '🗑 Retirer sélection';
        },

        async removeSelectedLeads() {
            const ids = this._checkedIds();
            if (!ids.length) return;
            const l = this.activeList;
            const ok = window.confirm(`Retirer ${ids.length} prospect(s) de « ${l?.nom || ''} » (déplacés vers la Corbeille, non destructif) ?`);
            if (!ok) return;
            await this._unlink(ids);
        },

        async removeLead(id) {
            const selIds = this._checkedIds();
            const single = !selIds.length;
            const ids = single ? [id] : selIds;
            const label = single ? (_state.leads.find(x => x.id === id)?.nom || '#' + id) : `${ids.length} prospect(s) sélectionné(s)`;
            const l = _state.leads.find(x => x.id === id);
            const ok = window.confirm(`Retirer « ${label} » de cette liste (→ Corbeille, non destructif) ?`);
            if (!ok) return;
            await this._unlink(ids);
        },

        async _unlink(ids) {
            if (!_state.activeListId || !ids.length) return;
            try {
                const r = await fetch(`/api/v2/listes/${_state.activeListId}/leads`, {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ lead_ids: ids }),
                });
                const d = await r.json();
                if (!d.success) throw new Error(d.error || 'Erreur');
                toast(`${d.moved ?? ids.length} prospect(s) retiré(s) → Corbeille`, 'success');
                await this.loadLeads(_state.page);
                await this.refresh();
                await this._refreshStats();
            } catch (e) {
                console.error('[listes] unlink', e);
                toast(e.message || 'Erreur', 'error');
            }
        },

        async copyEmail(email) {
            if (!email) return;
            try {
                await navigator.clipboard.writeText(email);
                toast('Email copié', 'success');
            } catch (e) {
                console.error('[listes] copy', e);
                toast('Copie impossible', 'error');
            }
        },

        // ─── Sélecteur rapide de statut (file humaine) ────────────
        _statutQuick(l) {
            if (!_state.transitions || !_state.transitions[l.statut]) return '';
            const next = (_state.transitions[l.statut] || []).filter(s => s !== l.statut);
            if (!next.length) return '';
            const opts = next
                .map(s => `<option value="${s}">${_state.statutLabels[s] || s}</option>`).join('');
            return `<select class="inp sm" style="max-width:150px;padding:3px 6px;font-size:11px;margin-top:4px"
                        onchange="ListesModule.changeStatut(${l.id}, this.value); this.selectedIndex = -1;"
                        onclick="event &amp;&amp; event.stopPropagation()">
                        <option value="" selected>→ Statut</option>${opts}</select>`;
        },

        _rowActions(l) {
            const b = [];
            b.push(`<button class="ul-act" onclick="ListesModule.openEdit(${l.id})" title="Modifier le prospect" aria-label="Modifier">✏️</button>`);
            // Actions IA : uniquement les prospects Web (général → pas de qualif/maquette IA).
            if ((l.objectif || ((l.campagne_id) ? 'general' : '')) === 'web') {
                b.push(`<button class="ul-act" onclick="ListesModule.runLeadIA('qualify', ${l.id})" title="Qualification IA du prospect" aria-label="Qualifier">✨</button>`);
                b.push(`<button class="ul-act" onclick="ListesModule.runLeadIA('maquette', ${l.id})" title="Maquette web (PROMPT/<id>/)">🖼</button>`);
            }
            b.push(`<button class="ul-act ${l.ecarte ? 'revert' : 'warn'}" onclick="ListesModule.toggleEcarte(${l.id})" title="${l.ecarte ? 'Réintégrer' : "Écarter des flux d'envoi"}" aria-label="Écarter">${l.ecarte ? '↩' : '🚫'}</button>`);
            b.push(`<button class="ul-act ${l.desinscrit ? 'revert' : 'danger'}" onclick="ListesModule.toggleDesinscrit(${l.id})" title="${l.desinscrit ? 'Réactiver' : "Désinscrire (opposition)"}" aria-label="Désinscrire">${l.desinscrit ? '✓' : '✋'}</button>`);
            b.push(`<button class="ul-act" onclick="ListesModule.removeLead(${l.id})" title="Retirer de la liste (→ Corbeille)" aria-label="Retirer">✕</button>`);
            b.push(`<button class="ul-act danger" onclick="ListesModule.deleteLead(${l.id})" title="Supprimer définitivement (irréversible)" aria-label="Supprimer">🗑</button>`);
            return `<div class="row-actions">${b.join('')}</div>`;
        },

        // ─── Actions v2 (prospect) ────────────────────────────────
        openDetail(id) {
            if (typeof window.openLeadPanel === 'function') {
                window.openLeadPanel(id);
            } else {
                toast('Détail indisponible pour le moment', 'error');
            }
        },

        async openEdit(id) {
            if (typeof window.unifiedLeadsOpenEdit === 'function') {
                await window.unifiedLeadsOpenEdit(id);
            } else {
                toast('Édition indisponible pour le moment', 'error');
            }
        },

        async changeStatut(id, statut) {
            if (!statut) return;
            const l = _state.leads.find(x => x.id == id);
            const ok = window.confirm(`Passer « ${l?.nom || id} » → ${_state.statutLabels[statut] || statut} ?`);
            if (!ok) return;
            try {
                const r = await fetch(`/api/v2/leads/${id}/statut`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ statut, reason: 'file humaine (UI listes)' }),
                });
                const d = await r.json();
                if (!d.success) { toast('Erreur : ' + (d.error || 'transition refusée'), 'error'); return; }
                toast(`${l?.nom || 'Prospect'} → ${_state.statutLabels[statut] || statut}`, 'success');
                await this.loadLeads(_state.page);
                await this._refreshStats();
            } catch (e) {
                console.error('[listes] changeStatut', e);
                toast('Erreur réseau', 'error');
            }
        },

        async toggleEcarte(id) {
            let ids = this._checkedIds();
            const single = !ids.length;
            if (single) ids = [id];
            const l = _state.leads.find(x => x.id === id);
            const next = !(l?.ecarte ?? false);
            const label = single ? (l?.nom || `#${id}`) : `${ids.length} prospect(s) sélectionné(s)`;
            const ok = window.confirm(next
                ? `Écarter « ${label} » des flux d'envoi ?`
                : `Réintégrer « ${label} » ?`);
            if (!ok) return;
            try {
                const r = await fetch(`/api/v2/leads/bulk/ecarter`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ lead_ids: ids, ecarte: next }),
                });
                const d = await r.json();
                if (!d.success) throw new Error(d.error);
                toast(next ? `${d.updated} lead(s) écarté(s) des flux d'envoi` : `${d.updated} lead(s) réintégré(s)`, 'success');
                await this.loadLeads(_state.page);
                await this._refreshStats();
            } catch (e) {
                console.error('[listes] ecarte', e);
                toast('Erreur', 'error');
            }
        },

        async toggleDesinscrit(id) {
            let ids = this._checkedIds();
            const single = !ids.length;
            if (single) ids = [id];
            const l = _state.leads.find(x => x.id === id);
            const next = !(l?.desinscrit ?? false);
            const label = single ? (l?.nom || `#${id}`) : `${ids.length} prospect(s) sélectionné(s)`;
            const ok = window.confirm(next
                ? `Désinscrire « ${label} » (opposition, toutes campagnes) ?`
                : `Réactiver « ${label} » ?`);
            if (!ok) return;
            try {
                const r = await fetch(`/api/v2/leads/bulk/desinscrire`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ lead_ids: ids, ne_plus_contacter: next }),
                });
                const d = await r.json();
                if (!d.success) throw new Error(d.error);
                toast(next ? `${d.updated} lead(s) désinscrit(s)` : `${d.updated} lead(s) réactivé(s)`, 'success');
                await this.loadLeads(_state.page);
                await this._refreshStats();
            } catch (e) {
                console.error('[listes] desinscrit', e);
                toast('Erreur', 'error');
            }
        },

        async deleteLead(id) {
            let ids = this._checkedIds();
            const single = !ids.length;
            if (single) ids = [id];
            const label = single ? (_state.leads.find(x => x.id === id)?.nom || `#${id}`) : `${ids.length} prospect(s) sélectionné(s)`;
            const ok = window.confirm(`Supprimer définitivement « ${label} » ? Irréversible.`);
            if (!ok) return;
            try {
                const r = await fetch(`/api/v2/leads/bulk`, {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ lead_ids: ids }),
                });
                const d = await r.json();
                if (!d.success) throw new Error(d.error);
                toast(`${d.deleted} prospect(s) supprimé(s)`, 'success');
                await this.loadLeads(_state.page);
                await this._refreshStats();
            } catch (e) {
                console.error('[listes] deleteLead', e);
                toast('Erreur', 'error');
            }
        },

        /** Refresh le panneau quand un prospect a été édité ailleurs (Leads). */
        async onProspectsChanged() {
            if (!sel('lists-sidebar-items')) return;
            if (_state.activeListId) await this.loadLeads(_state.page);
        },

        async _refreshStats() {
            if (window.CampagnesModule && typeof window.CampagnesModule.refreshStats === 'function') {
                await window.CampagnesModule.refreshStats();
            }
        },

        // ─── Panneau d'actions repliable / toolbar extra ──────────
        toggleActions() {
            const p = sel('lists-section-actions');
            if (p) p.classList.toggle('open');
            const btn = sel('liste-actions-btn');
            if (btn) btn.classList.toggle('active', p?.classList.contains('open'));
        },

        toggleToolbar() {
            const e = sel('lists-toolbar-extra');
            if (e) e.classList.toggle('open');
            const t = document.querySelector('.lists-toolbar-toggle');
            if (t) t.classList.toggle('open');
        },

        toggleFiltres() {
            const p = sel('lists-section-filtres');
            if (p) p.classList.toggle('open');
            const btn = sel('liste-filtres-btn');
            if (btn) btn.classList.toggle('active', p?.classList.contains('open'));
        },

        // ─── Filtres des prospects (panneau repliable) ─────────────
        _populateStatutFilter() {
            const el = sel('liste-filtre-statut');
            if (!el) return;
            el.innerHTML = '<option value="">Tous les statuts</option>' +
                Object.keys(_state.statutLabels)
                    .map(s => `<option value="${s}">${_state.statutLabels[s]}</option>`)
                    .join('');
        },

        getTransitions() {
            return _state.transitions;
        },

        // ─── Bascule Liste / Kanban ────────────────────────────────
        setView(view) {
            _state.view = view === 'kanban' ? 'kanban' : 'list';
            const listView = sel('liste-leads-list-view');
            const kbView = sel('liste-kanban-view');
            if (listView) listView.style.display = _state.view === 'list' ? '' : 'none';
            if (kbView) kbView.style.display = _state.view === 'kanban' ? '' : 'none';
            const bList = sel('liste-view-list');
            const bKanban = sel('liste-view-kanban');
            if (bList) bList.classList.toggle('active', _state.view === 'list');
            if (bKanban) bKanban.classList.toggle('active', _state.view === 'kanban');
            if (_state.activeListId) this.loadLeads(1);
        },

        _renderKanban() {
            const root = sel('liste-kanban-view');
            if (!root) return;
            window._ulKanbanCardClickHandler = (id) => {
                if (typeof window.openLeadPanel === 'function') window.openLeadPanel(id);
            };
            window.renderKanbanBoard(root, _state.leads, {
                prefix: 'lkb',
                onChanged: () => { this.loadLeads(_state.page); this._refreshStats(); },
                onFailed: () => { this.loadLeads(_state.page); },
            });
        },

        // ─── Pagination / recherche ───────────────────────────────
        _updatePagination() {
            const prev = sel('liste-prev'), next = sel('liste-next'), info = sel('liste-page-info');
            if (prev) prev.disabled = _state.page <= 1;
            if (next) next.disabled = _state.page >= _state.totalPages;
            if (info) info.textContent = `page ${_state.page} / ${_state.totalPages}`;
        },

        changePage(delta) {
            const p = Math.max(1, Math.min(_state.totalPages, _state.page + delta));
            if (p !== _state.page) this.loadLeads(p);
        },

        onSearch() {
            clearTimeout(_state.searchDebounce);
            _state.searchDebounce = setTimeout(() => {
                _state.leadsSearch = sel('liste-lead-search')?.value?.trim() || '';
                this.loadLeads(1);
            }, 300);
        },

        // ─── Navigation vers l'onglet Leads ───────────────────────
        async viewLeads() {
            const l = this.activeList;
            if (!l) return;
            this._goLeads(l.campagne_id);
        },

        async _goLeads(campagneId) {
            if (window.CampagnesModule && campagneId && campagneId != window.CampagnesModule.currentId) {
                await window.CampagnesModule.doSelect(campagneId, { silent: true });
            }
            if (typeof window.nav === 'function') {
                window.nav('leads', document.getElementById('nav-leads'));
            }
        },

        // ─── CRUD listes ──────────────────────────────────────────
        async openCreate() {
            return this.openCreateModal();
        },

        // ─── Modal création / modification de liste ────────────────
        _initEmojiGrid() {
            const grid = sel('liste-form-icone-grid');
            if (!grid || _state.emojiWired) return;
            _state.emojiWired = true;
            grid.innerHTML = EMOJIS.map(e => `<div class="list-emoji-opt" data-emoji="${e}">${e}</div>`).join('');
            grid.addEventListener('click', (ev) => {
                const opt = ev.target.closest('.list-emoji-opt');
                if (!opt) return;
                grid.querySelectorAll('.list-emoji-opt').forEach(o => o.classList.remove('selected'));
                opt.classList.add('selected');
                _state.form.icone = opt.getAttribute('data-emoji');
            });
        },

        _initColorGrid() {
            const grid = sel('liste-form-couleur-grid');
            if (!grid || _state.colorWired) return;
            _state.colorWired = true;
            grid.innerHTML = COLORES.map(c => `<div class="list-color-opt" data-color="${c}" style="background:${c}"></div>`).join('');
            grid.addEventListener('click', (ev) => {
                const opt = ev.target.closest('.list-color-opt');
                if (!opt) return;
                grid.querySelectorAll('.list-color-opt').forEach(o => o.classList.remove('selected'));
                opt.classList.add('selected');
                _state.form.couleur = opt.getAttribute('data-color');
            });
        },

        _initObjectifGrid() {
            const wrap = sel('liste-form-objectif');
            if (!wrap || _state.objectifWired) return;
            _state.objectifWired = true;
            wrap.addEventListener('click', (ev) => {
                const opt = ev.target.closest('.objectif-opt');
                if (!opt) return;
                wrap.querySelectorAll('.objectif-opt').forEach(o => o.classList.remove('active'));
                opt.classList.add('active');
                _state.form.objectif = opt.getAttribute('data-objectif');
            });
        },

        _setPicker(kind, value) {
            const grid = sel(kind === 'icone' ? 'liste-form-icone-grid' : 'liste-form-couleur-grid');
            if (!grid) return;
            grid.querySelectorAll(PICKER_CLS[kind]).forEach(o => {
                o.classList.toggle('selected', o.getAttribute(PICKER_ATTR[kind]) === String(value));
            });
            _state.form[kind] = String(value);
        },

        _setObjectif(v) {
            const wrap = sel('liste-form-objectif');
            if (wrap) {
                wrap.querySelectorAll('.objectif-opt').forEach(o => {
                    o.classList.toggle('active', o.getAttribute('data-objectif') === v);
                });
            }
            _state.form.objectif = v || 'general';
        },

        openCreateModal() {
            if (!this.campagneId) {
                toast('Sélectionnez d\'abord une campagne dans la barre du haut', 'error');
                return;
            }
            _state.editingListId = null;
            this._initEmojiGrid();
            this._initColorGrid();
            this._initObjectifGrid();
            this._setForm({ nom: '', description: '', secteur: '', source: 'manuel', icone: '📋', couleur: '#6366f1', objectif: 'general' });
            const t = sel('modal-list-form-title');
            if (t) t.textContent = 'Nouvelle liste';
            if (typeof window.openModal === 'function') window.openModal('modal-list-form');
            else { const m = sel('modal-list-form'); if (m) m.style.display = 'flex'; }
        },

        async openEditList(listeId) {
            if (!listeId) return;
            const l = _state.listes.find(x => x.id === listeId) || this.activeList;
            if (!l) return;
            this._initEmojiGrid();
            this._initColorGrid();
            this._initObjectifGrid();
            _state.editingListId = listeId;
            this._setForm({
                nom: l.nom || '',
                description: l.description || '',
                secteur: l.secteur || '',
                source: l.source || 'manuel',
                icone: l.icone || '📋',
                couleur: l.couleur || '#6366f1',
                objectif: l.objectif || 'general',
            });
            const t = sel('modal-list-form-title');
            if (t) t.textContent = `Modifier « ${l.nom} »`;
            if (typeof window.openModal === 'function') window.openModal('modal-list-form');
            else { const m = sel('modal-list-form'); if (m) m.style.display = 'flex'; }
        },

        _setForm(v) {
            ['nom', 'description', 'secteur', 'source'].forEach(k => {
                const el = sel(`liste-form-${k}`);
                if (el) el.value = (v && v[k]) || '';
            });
            this._setPicker('icone', (v && v.icone) || '📋');
            this._setPicker('couleur', (v && v.couleur) || '#6366f1');
            this._setObjectif((v && v.objectif) || 'general');
        },

        async saveListFromModal() {
            const nom = (sel('liste-form-nom')?.value || '').trim();
            if (!nom) {
                toast('Le nom de la liste est obligatoire', 'error');
                sel('liste-form-nom')?.focus();
                return;
            }
            const body = {
                nom,
                description: sel('liste-form-description')?.value?.trim() || '',
                secteur: sel('liste-form-secteur')?.value?.trim() || '',
                source: sel('liste-form-source')?.value || 'manuel',
                icone: _state.form.icone || '📋',
                couleur: _state.form.couleur || '#6366f1',
                objectif: _state.form.objectif || 'general',
            };
            const editing = _state.editingListId;
            try {
                let r;
                if (editing) {
                    r = await fetch(`/api/v2/listes/${editing}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body),
                    });
                } else {
                    r = await fetch('/api/v2/listes', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ campagne_id: this.campagneId, ...body }),
                    });
                }
                const d = await r.json();
                if (!d.success) throw new Error(d.error || 'Erreur enregistrement');
                toast(editing ? 'Liste modifiée' : `Liste « ${d.liste.nom} » créée`, 'success');
                if (typeof window.closeModal === 'function') window.closeModal('modal-list-form');
                else { const m = sel('modal-list-form'); if (m) m.style.display = 'none'; }
                await this.refresh();
                await this._refreshStats();
            } catch (e) {
                console.error('[listes] saveList', e);
                toast(e.message || 'Erreur', 'error');
            }
        },

        // ─── Note de liste (autosave au perte de focus) ────────────
        _initNoteAutoSave() {
            const ta = sel('liste-note');
            if (!ta || _state.noteWired) return;
            _state.noteWired = true;
            ta.addEventListener('input', () => this.autoResize(ta));
            ta.addEventListener('blur', () => this.saveNote());
        },

        autoResize(ta) {
            if (!ta) return;
            ta.style.height = 'auto';
            ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
        },

        async saveNote() {
            const listeId = _state.activeListId;
            const ta = sel('liste-note');
            if (!listeId || !ta) return;
            const note = ta.value;
            try {
                const r = await fetch(`/api/v2/listes/${listeId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ note }),
                });
                const d = await r.json();
                if (!d.success) throw new Error(d.error || 'Erreur note');
                const lst = this.activeList;
                if (lst) lst.note = note;
                toast('Note enregistrée', 'success');
            } catch (e) {
                console.error('[listes] note', e);
                toast('Erreur d\'enregistrement de la note', 'error');
            }
        },

        loadListNote() {
            const ta = sel('liste-note');
            if (ta) {
                ta.value = this.activeList?.note || '';
                this.autoResize(ta);
            }
        },

        // ─── Boutons IA / Envoi / Import (implémentations v2) ──────
        async runIA(action) {
            const l = this.activeList;
            if (!l) return;
            if (!window.IaActions || typeof window.IaActions.qualifyList !== 'function') {
                toast('Actions IA indisponibles', 'error');
                return;
            }
            const Ia = window.IaActions;
            const selIds = this._checkedIds();
            if (selIds.length) {
                // Sélection active → l'action IA ne cible que les prospects cochés.
                const scope = { lead_ids: selIds };
                const selMap = {
                    qualify: () => Ia.qualify(scope),
                    maquette: () => Ia.maquette(scope),
                    redact: () => Ia.redact(scope),
                    scan: () => Ia.scan(scope),
                };
                const fn = selMap[action];
                if (!fn) return;
                const d = await fn();
                if (action === 'scan' && d && d.ok) {
                    await this.refresh();
                    await this._refreshStats();
                }
                return;
            }
            const map = {
                qualify: () => Ia.qualifyList(l.id, l.nom),
                maquette: () => Ia.maquetteList(l.id, l.nom),
                redact: () => Ia.redactList(l.id, l.nom),
                scan: () => Ia.scan({ liste_id: l.id, liste_nom: l.nom }),
            };
            const fn = map[action];
            if (!fn) return;
            const d = await fn();
            if (action === 'scan' && d && d.ok) {
                await this.refresh();
                await this._refreshStats();
            }
        },

        async runLeadIA(action, id) {
            if (!window.IaActions || typeof window.IaActions.qualifyLead !== 'function') {
                toast('Actions IA indisponibles', 'error');
                return;
            }
            const Ia = window.IaActions;
            const selIds = this._checkedIds();
            const scope = selIds.length ? { lead_ids: selIds } : { lead_ids: [id] };
            const fn = action === 'maquette' ? Ia.maquette : Ia.qualify;
            await fn(scope);
        },

        // ─── Envoi ciblé par liste avec suivi temps réel & tracking ─────────
        async sendList() {
            const l = this.activeList;
            if (!l) {
                toast('Sélectionnez d\'abord une liste', 'warning');
                return;
            }

            const selected = this._checkedIds();
            const confirmMsg = selected.length
                ? `Envoyer ${selected.length} email(s) sélectionné(s) de la liste « ${l.nom} » uniquement ?\n\n` +
                  `• Uniquement les ${selected.length} prospects cochés (aucun autre prospect)\n` +
                  `• Initials + relances dues\n` +
                  `• Tracking d'ouverture et de clic activé systématiquement`
                : `Envoyer TOUS les emails de la liste « ${l.nom} » uniquement ?\n\n` +
                  `• Uniquement les prospects de cette liste (aucun autre prospect de la campagne)\n` +
                  `• Initials + relances dues\n` +
                  `• Tracking d'ouverture et de clic activé systématiquement`;

            const ok = window.UI?.confirm
                ? await window.UI.confirm(confirmMsg, { title: '📤 Envoi de la liste', confirmText: 'Envoyer maintenant' })
                : window.confirm(confirmMsg);
            if (!ok) return;

            const btn = sel('liste-btn-send');
            if (btn) {
                btn.disabled = true;
                btn.textContent = '⏳ Lancement…';
            }

            try {
                const r = await fetch(`/api/v2/listes/${l.id}/send`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ lead_ids: selected.length ? selected : undefined }),
                });
                const d = await r.json();

                if (!d.success) {
                    throw new Error(d.error || 'Erreur lors du lancement de l\'envoi');
                }

                if (d.total === 0) {
                    toast(d.message || `Aucun email en attente d'envoi dans « ${l.nom} »`, 'info');
                    if (btn) { btn.disabled = false; btn.textContent = '📤 Envoyer la liste'; }
                    return;
                }

                toast(`🚀 Envoi lancé : ${d.total} prospect(s) ciblé(s)`, 'info');
                this._startProgressTracking(l.id, d.job_id, d.total);
            } catch (e) {
                console.error('[listes] sendList', e);
                toast(e.message || 'Erreur envoi', 'error');
                if (btn) { btn.disabled = false; btn.textContent = '📤 Envoyer la liste'; }
            }
        },

        // Alias de compatibilité
        async sendCampaign() {
            return this.sendList();
        },

        async cancelSend() {
            const l = this.activeList;
            if (!l) return;
            try {
                const r = await fetch(`/api/v2/listes/${l.id}/send/cancel`, { method: 'POST' });
                const d = await r.json();
                if (d.success) {
                    toast('Envoi en cours d\'annulation…', 'info');
                    const leadEl = sel('liste-send-current-lead');
                    if (leadEl) leadEl.textContent = 'Arrêt demandé par l\'utilisateur…';
                }
            } catch (e) {
                console.error('[listes] cancelSend', e);
            }
        },

        _startProgressTracking(listeId, jobId, totalInitial) {
            const banner = sel('liste-send-progress-banner');
            const fill = sel('liste-send-progress-bar-fill');
            const counter = sel('liste-send-progress-counter');
            const pctEl = sel('liste-send-progress-pct');
            const titleEl = sel('liste-send-progress-title');
            const leadEl = sel('liste-send-current-lead');
            const cancelBtn = sel('liste-send-cancel-btn');
            const sendBtn = sel('liste-btn-send');

            if (banner) banner.style.display = 'flex';
            if (cancelBtn) cancelBtn.style.display = 'inline-block';
            if (sendBtn) {
                sendBtn.disabled = true;
                sendBtn.textContent = '📤 Envoi en cours…';
            }
            if (titleEl) titleEl.textContent = 'Envoi de la liste en cours…';
            if (counter) counter.innerHTML = `<strong>0</strong> / ${totalInitial || 0} emails`;
            if (pctEl) pctEl.textContent = '0%';
            if (fill) fill.style.width = '0%';
            if (leadEl) leadEl.textContent = 'Démarrage du tunnel d\'envoi avec tracking…';

            // Nettoyer un éventuel intervalle précédent
            if (_state.pollInterval) {
                clearInterval(_state.pollInterval);
                _state.pollInterval = null;
            }

            const updateUIFromJob = (job) => {
                if (!job) return;
                const cur = job.current || 0;
                const tot = job.total || totalInitial || 0;
                const pct = job.percentage || (tot > 0 ? Math.round((cur / tot) * 100) : 0);

                if (counter) counter.innerHTML = `<strong>${cur}</strong> / ${tot} emails`;
                if (pctEl) pctEl.textContent = `${pct}%`;
                if (fill) fill.style.width = `${pct}%`;

                if (job.current_lead) {
                    const l = job.current_lead;
                    const statusIcon = l.success ? '✅' : '⚠️';
                    if (leadEl) {
                        leadEl.textContent = `${statusIcon} ${l.nom || 'Prospect'} (${l.email || ''}) — ${l.statut || ''}`;
                    }
                }

                if (!job.running) {
                    // Job terminé ou annulé
                    if (_state.pollInterval) {
                        clearInterval(_state.pollInterval);
                        _state.pollInterval = null;
                    }
                    if (cancelBtn) cancelBtn.style.display = 'none';
                    if (sendBtn) {
                        sendBtn.disabled = false;
                        sendBtn.textContent = '📤 Envoyer la liste';
                    }

                    if (job.status === 'termine') {
                        if (titleEl) titleEl.textContent = '✅ Envoi terminé avec succès';
                        if (leadEl) leadEl.textContent = `Bilan : ${job.sent || 0} envoyé(s), ${job.failed || 0} erreur(s) — Tracking actif`;
                        toast(`✅ Envoi terminé : ${job.sent || 0} email(s) envoyé(s) sur ${tot}`, 'success');
                    } else if (job.status === 'annule') {
                        if (titleEl) titleEl.textContent = '⏹️ Envoi interrompu';
                        if (leadEl) leadEl.textContent = `Interrompu à ${cur}/${tot} emails (${job.sent || 0} envoyés)`;
                        toast('Envoi de la liste interrompu', 'warning');
                    } else if (job.status === 'erreur') {
                        if (titleEl) titleEl.textContent = '❌ Erreur lors de l\'envoi';
                        if (leadEl) leadEl.textContent = job.error || 'Erreur inattendue';
                        toast(job.error || 'Erreur lors de l\'envoi', 'error');
                    }

                    // Rafraîchir les leads et stats
                    this.loadLeads(_state.page);
                    this._refreshStats();

                    // Masquer la bannière après 8 secondes
                    setTimeout(() => {
                        if (banner && !_state.pollInterval) {
                            banner.style.display = 'none';
                        }
                    }, 8000);
                }
            };

            // Polling régulier de secours (toutes les 500ms)
            _state.pollInterval = setInterval(async () => {
                try {
                    const res = await fetch(`/api/v2/listes/${listeId}/send/status`);
                    const data = await res.json();
                    if (data.success && data.job) {
                        updateUIFromJob(data.job);
                    }
                } catch (e) {
                    console.error('[listes] poll status error', e);
                }
            }, 500);

            // Écoute des événements WebSocket si socketio est connecté
            const sock = window.socket || (typeof io !== 'undefined' ? window.socketio : null);
            if (sock && typeof sock.on === 'function' && !_state.socketWired) {
                _state.socketWired = true;
                sock.on('list_send_progress', (payload) => {
                    if (payload && payload.liste_id === listeId) {
                        if (counter) counter.innerHTML = `<strong>${payload.current}</strong> / ${payload.total} emails`;
                        if (pctEl) pctEl.textContent = `${payload.percentage}%`;
                        if (fill) fill.style.width = `${payload.percentage}%`;
                        if (payload.lead && leadEl) {
                            const icon = payload.lead.success ? '✅' : '⚠️';
                            leadEl.textContent = `${icon} ${payload.lead.nom || 'Prospect'} (${payload.lead.email || ''}) — ${payload.lead.statut || ''}`;
                        }
                    }
                });
                sock.on('list_send_done', (payload) => {
                    if (payload && payload.liste_id === listeId) {
                        updateUIFromJob({ running: false, status: payload.status || 'termine', sent: payload.sent, failed: payload.failed, total: payload.total, current: payload.total });
                    }
                });
            }
        },

        openImport() {
            const input = sel('liste-import-input');
            if (input) input.click();
        },

        _wireImport() {
            const input = sel('liste-import-input');
            if (!input || _state.importWired) return;
            _state.importWired = true;
            input.addEventListener('change', () => {
                const f = input.files && input.files[0];
                if (f) {
                    this.importFile(f);
                    input.value = '';
                }
            });
        },

        async importFile(file) {
            const listeId = _state.activeListId;
            if (!listeId || !file) return;
            toast(`Import de « ${file.name || 'fichier'} » en cours…`, 'info');
            try {
                const text = await file.text();
                const trimmed = text.replace(/^\uFEFF/, '').trim();
                let headers = { 'Content-Type': 'text/plain' };
                let body = text;
                if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
                    try {
                        const parsed = JSON.parse(trimmed);
                        body = JSON.stringify(Array.isArray(parsed) ? { rows: parsed } : parsed);
                        headers = { 'Content-Type': 'application/json' };
                    } catch (e) {
                        // JSON invalide → laissé tel quel (texte CSV)
                    }
                }
                const r = await fetch(`/api/v2/listes/${listeId}/leads/import`, {
                    method: 'POST',
                    headers,
                    body,
                });
                const d = await r.json();
                if (!d.success) throw new Error(d.error || 'Erreur import');
                toast(`Import : ${d.importes ?? d.total ?? 0} prospect(s)`, 'success');
                await this.loadLeads(1);
                await this.refresh();
                await this._refreshStats();
            } catch (e) {
                console.error('[listes] import', e);
                toast(e.message || 'Erreur import', 'error');
            }
        },

        async openRename(listeId) {
            if (!listeId) return;
            const l = _state.listes.find(x => x.id === listeId);
            if (!l) return;
            const nom = window.prompt('Nouveau nom de la liste :', l.nom || '');
            if (!nom || nom === l.nom) return;
            try {
                const r = await fetch(`/api/v2/listes/${listeId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ nom }),
                });
                const d = await r.json();
                if (!d.success) throw new Error(d.error || 'Erreur');
                toast('Liste renommée', 'success');
                await this.refresh();
            } catch (e) {
                console.error('[listes] rename', e);
                toast(e.message || 'Erreur', 'error');
            }
        },

        async toggleArchiveActive() {
            return this.toggleArchive(this.activeId);
        },

        async toggleArchive(listeId) {
            if (!listeId) return;
            const l = _state.listes.find(x => x.id === listeId);
            if (!l) return;
            const archiver = l.statut !== 'archive';
            try {
                const r = await fetch(`/api/v2/listes/${listeId}/archive`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ archiver }),
                });
                const d = await r.json();
                if (!d.success) throw new Error(d.error || 'Erreur');
                toast(archiver ? 'Liste archivée' : 'Liste restaurée', 'success');
                if (archiver && listeId === _state.activeListId) this.clearSelection();
                await this.refresh();
            } catch (e) {
                console.error('[listes] archive', e);
                toast(e.message || 'Erreur', 'error');
            }
        },

        async removeActive() {
            return this.remove(this.activeId);
        },

        async remove(listeId) {
            if (!listeId) return;
            const l = _state.listes.find(x => x.id === listeId);
            if (!l) return;
            const ok = window.confirm(`Supprimer la liste « ${l.nom} » et ses ${l.nb_leads || 0} prospect(s) ? Irréversible.`);
            if (!ok) return;
            try {
                const r = await fetch(`/api/v2/listes/${listeId}`, { method: 'DELETE' });
                const d = await r.json();
                if (!d.success) throw new Error(d.error || 'Erreur');
                toast('Liste supprimée', 'success');
                if (listeId === _state.activeListId) this.clearSelection();
                await this.refresh();
                await this._refreshStats();
            } catch (e) {
                console.error('[listes] delete', e);
                toast(e.message || 'Erreur', 'error');
            }
        },

        // ─── Mobile ───────────────────────────────────────────────
        toggleMobileSidebar() {
            const s = sel('lists-sidebar');
            if (s) s.classList.add('mobile-open');
            const o = sel('lists-sidebar-overlay');
            if (o) o.classList.add('open');
        },

        closeMobileSidebar() {
            const s = sel('lists-sidebar');
            if (s) s.classList.remove('mobile-open');
            const o = sel('lists-sidebar-overlay');
            if (o) o.classList.remove('open');
        },
    };

    window.ListesModule = ListesModule;
})();