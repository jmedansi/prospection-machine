/**
 * dashboard/static/js/modules/lists.js
 * Module de gestion des listes de leads.
 *
 * API: window.ListsModule
 * Dépendances : showToast (ui.js), showConfirm (ui.js), ulGetSelectedIds (unified_leads.js)
 */

window.ListsModule = (function () {

    // ─── État interne ──────────────────────────────────────────────────────
    const _state = {
        lists:          [],     // toutes les listes
        activeListId:   null,   // liste affichée dans le panneau principal
        activeListNom:  '',
        leads:          [],     // leads de la liste active
        page:           1,
        totalPages:     1,
        total:          0,
        // Pour le modal "Ajouter leads" :
        searchResults:  [],
        selectedToAdd:  new Set(),
        // Pour le dropdown "Ajouter à liste" depuis la vue Leads :
        dropdownOpen:   false,
        // Création/édition de liste
        editingListId:  null,
    };

    // ─── Emojis et couleurs disponibles dans les modals ───────────────────
    const EMOJIS  = ['📋','📌','🎯','🔥','⭐','📅','🏷','🗂','📂','✅','🚀','💼','📞','✉️','🔍'];
    const COLORS  = ['#6366f1','#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6',
                     '#ec4899','#06b6d4','#84cc16','#f97316','#64748b','#0f172a'];

    // ─── INIT ──────────────────────────────────────────────────────────────

    async function init() {
        await loadLists();
        _renderDropdownStyles();
    }

    // ─── CRUD Listes ───────────────────────────────────────────────────────

    async function loadLists() {
        try {
            const r = await fetch('/api/lists');
            const d = await r.json();
            if (d.error) throw new Error(d.error);
            _state.lists = d.lists || [];
            _renderSidebarLists();
            _updateBadge();
        } catch (e) {
            console.error('[Lists] loadLists:', e);
        }
    }

    function _renderSidebarLists() {
        const el = document.getElementById('lists-sidebar-items');
        if (!el) return;

        if (!_state.lists.length) {
            el.innerHTML = `<div class="lists-empty-state" style="text-align:center;padding:32px 16px;color:var(--ink3)">
                <div style="font-size:32px;margin-bottom:8px">📋</div>
                <div style="font-size:12px">Aucune liste</div>
                <div style="font-size:11px;margin-top:4px">Crée ta première liste<br>pour organiser tes leads</div>
            </div>`;
            return;
        }

        el.innerHTML = _state.lists.map(lst => `
            <div class="list-sidebar-item ${lst.id === _state.activeListId ? 'active' : ''}"
                 onclick="ListsModule.selectList(${lst.id})"
                 style="border-left: 3px solid ${lst.couleur || '#6366f1'}">
                <span class="list-sidebar-icone">${_esc(lst.icone || '📋')}</span>
                <div class="list-sidebar-info">
                    <div class="list-sidebar-nom" title="${_esc(lst.nom)}">${_esc(lst.nom)}</div>
                    <div class="list-sidebar-meta">
                        ${lst.nb_leads || 0} lead${lst.nb_leads !== 1 ? 's' : ''}
                    </div>
                </div>
                <button class="btn bg0" style="font-size:10px;padding:2px 5px;flex-shrink:0"
                        onclick="event.stopPropagation();ListsModule.openEditModal(${lst.id})"
                        title="Modifier cette liste">✏️</button>
            </div>
        `).join('');
    }

    function _updateBadge() {
        const badge = document.getElementById('badge-lists-count');
        if (!badge) return;
        const total = _state.lists.length;
        badge.textContent = total;
        badge.style.display = total > 0 ? '' : 'none';
    }

    // ─── Sélection d'une liste ─────────────────────────────────────────────

    function selectList(listId) {
        _state.activeListId = listId;
        const lst = _state.lists.find(l => l.id === listId);
        if (lst) _state.activeListNom = lst.nom;

        // Mettre à jour l'UI sidebar
        _renderSidebarLists();

        // Afficher le panneau principal
        const placeholder = document.getElementById('lists-placeholder');
        const view = document.getElementById('lists-view');
        if (placeholder) placeholder.style.display = 'none';
        if (view) view.style.display = '';

        // Mettre à jour l'en-tête
        const nom = document.getElementById('list-active-nom');
        const icone = document.getElementById('list-active-icone');
        if (nom) nom.textContent = lst?.nom || '—';
        if (icone) icone.textContent = lst?.icone || '📋';

        // Note
        const note = document.getElementById('list-active-note');
        if (note) {
            note.value = lst?.note || '';
            note.style.height = 'auto';
            note.style.height = Math.min(note.scrollHeight, 80) + 'px';
        }
        _initNoteAutoSave();

        // Mettre à jour les boutons relance/contactée
        _updateRelanceButtons();

        // Badge campagne
        const badge = document.getElementById('list-active-campaign-badge');
        if (badge) badge.style.display = lst?.campaign_id ? '' : 'none';

        // Bouton archiver
        const archiveBtn = document.getElementById('list-btn-archive');
        if (archiveBtn) archiveBtn.style.display = lst?.archived ? 'none' : '';

        // Mobile title
        const mobileTitle = document.getElementById('lists-mobile-title');
        if (mobileTitle) mobileTitle.textContent = lst?.nom || 'Mes listes';

        // Fermer sidebar mobile si ouverte
        closeMobileSidebar();

        // Réinitialiser toolbar
        const extra = document.getElementById('lists-toolbar-extra');
        const toggle = document.getElementById('lists-toolbar-toggle');
        if (extra) extra.style.display = 'none';
        if (toggle) toggle.classList.remove('open');

        loadListLeads(1);
    }

    // ─── Leads d'une liste ─────────────────────────────────────────────────

    async function loadListLeads(page = 1) {
        if (!_state.activeListId) return;
        _state.page = page;

        const tbody = document.getElementById('list-tbody');
        if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:24px;color:var(--ink3)">Chargement…</td></tr>`;

        const search = document.getElementById('list-search')?.value?.trim() || '';
        const params = new URLSearchParams({ page, limit: 50 });
        if (search) params.set('search', search);

        try {
            const r = await fetch(`/api/lists/${_state.activeListId}/leads?${params}`);
            const d = await r.json();
            if (d.error) throw new Error(d.error);

            _state.leads = d.leads || [];
            _state.page = d.page;
            _state.totalPages = d.total_pages;
            _state.total = d.total;

            // Mise à jour du badge de count
            const countEl = document.getElementById('list-active-count');
            if (countEl) countEl.textContent = `${d.total} lead${d.total !== 1 ? 's' : ''}`;

            // Mise à jour du nb_leads dans le sidebar
            const lst = _state.lists.find(l => l.id === _state.activeListId);
            if (lst) lst.nb_leads = d.total;
            _renderSidebarLists();
            _updateBadge();

            // Rendu de la table
            if (tbody) {
                tbody.innerHTML = _state.leads.length
                    ? _state.leads.map(_renderLeadRow).join('')
                    : `<tr><td colspan="7" style="text-align:center;padding:24px;color:var(--ink3)">Aucun lead dans cette liste.</td></tr>`;
            }

            _updatePagination();
            _updateRemoveBtn();

        } catch (e) {
            console.error('[Lists] loadListLeads:', e);
            if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="color:var(--red);text-align:center;padding:16px">${_esc(e.message)}</td></tr>`;
        }
    }

    function _renderLeadRow(l) {
        const nom = _esc(l.nom || '—');
        const initial = nom.charAt(0).toUpperCase();
        const siteUrl = _esc(l.site_web || '');
        const nomCell = siteUrl
            ? `<a href="${siteUrl}" target="_blank" class="lead-name" style="color:var(--ink1);text-decoration:none">${nom}</a>`
            : `<strong class="lead-name">${nom}</strong>`;

        const srcMap = { maps:'#6b7280',ads:'#f97316',fb_ads:'#1877f2',tech:'#8b5cf6',ecom:'#8b5cf6',jobs:'#06b6d4',bodacc:'#10b981' };
        const srcCol = srcMap[l.source] || '#9ca3af';
        const srcBadge = `<span style="background:${srcCol}15;color:${srcCol};padding:1px 5px;border-radius:4px;font-size:9px;font-weight:700;text-transform:uppercase;margin-right:5px">${l.source||'?'}</span>`;
        const meta = `${srcBadge}${_esc(l.category || l.secteur || 'Prospect')}`;

        // Score
        let scoreHtml = '<span style="color:var(--ink3)">—</span>';
        if (l.mobile_score && l.mobile_score > 0) {
            const c = l.mobile_score >= 70 ? '#10b981' : l.mobile_score >= 50 ? '#f59e0b' : '#ef4444';
            scoreHtml = `<span style="font-weight:700;color:${c}">${l.mobile_score}<span style="font-size:10px;color:var(--ink3)">/100</span></span>`;
        } else if (l.rating && l.rating > 0) {
            scoreHtml = `<span style="font-size:12px">${parseFloat(l.rating).toFixed(1)} ⭐</span>`;
        }

        // Statut badge (simplifié)
        const statut = l.statut_prospection || l.statut || '—';
        const statutColors = { envoye:'#3b82f6',email_genere:'#10b981',audite:'#8b5cf6',repondu:'#f59e0b' };
        const sc = statutColors[statut] || '#64748b';
        const statutHtml = `<span style="background:${sc}20;color:${sc};padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600">${_esc(statut.replace(/_/g,' '))}</span>`;

        // Contact
        const hasEmail = l.email_valide || l.email;
        const email = (l.email_valide && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(l.email_valide)) ? l.email_valide : l.email;

        return `<tr onclick="openLeadPanel(${l.id})" style="cursor:pointer">
            <td class="col-check" onclick="event.stopPropagation()">
                <input type="checkbox" class="list-lead-cb" data-id="${l.id}">
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
            <td class="col-source" style="font-size:11px;color:var(--ink3)">${_esc(l.ville||'')}</td>
            <td class="col-contact" style="font-size:11px">
                ${email ? `<span style="display:inline-flex;align-items:center;gap:4px"><a href="mailto:${_esc(email)}" style="color:var(--accent);text-decoration:none">${_esc(email)}</a><button class="btn-copy-email" onclick="event.stopPropagation();ListsModule.copyEmail('${_esc(email)}')" title="Copier l'email pour WhatsApp" style="background:none;border:none;cursor:pointer;padding:2px;color:var(--ink3);font-size:11px;line-height:1" onmouseenter="this.style.color='var(--accent)'" onmouseleave="this.style.color='var(--ink3)'">📋</button></span>` : '<span style="color:var(--ink3)">—</span>'}
            </td>
            <td class="col-score">${scoreHtml}</td>
            <td class="col-statut">${statutHtml}</td>
            <td class="col-actions" style="text-align:right;white-space:nowrap" onclick="event.stopPropagation()">
                <button class="btn bg1 sm" style="font-size:11px;padding:3px 8px"
                    onclick="ListsModule.removeLead(${l.id})" title="Retirer de la liste">✕</button>
            </td>
        </tr>`;
    }

    // ─── Sélection et suppression dans la liste ────────────────────────────

    function toggleAll(cb) {
        document.querySelectorAll('.list-lead-cb').forEach(c => c.checked = cb.checked);
        _updateRemoveBtn();
    }

    function _getSelectedIds() {
        return [...document.querySelectorAll('.list-lead-cb:checked')].map(c => parseInt(c.dataset.id)).filter(Boolean);
    }

    function _updateRemoveBtn() {
        const ids = _getSelectedIds();
        const btn = document.getElementById('btn-list-remove-selected');
        if (btn) {
            btn.style.display = ids.length > 0 ? '' : 'none';
            btn.textContent = `Retirer les ${ids.length} sélectionnés`;
        }
    }

    document.addEventListener('change', function(e) {
        if (e.target && e.target.classList.contains('list-lead-cb')) _updateRemoveBtn();
    });

    async function removeLead(leadId) {
        if (!_state.activeListId) return;
        try {
            const r = await fetch(`/api/lists/${_state.activeListId}/leads`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lead_ids: [leadId] })
            });
            const d = await r.json();
            if (!d.success) throw new Error(d.error || 'Erreur');
            showToast?.('Lead retiré de la liste', 'success');
            loadListLeads(_state.page);
        } catch (e) {
            console.error('[Lists] removeLead:', e);
            showToast?.('Erreur : ' + e.message, 'error');
        }
    }

    async function removeSelectedLeads() {
        const ids = _getSelectedIds();
        if (!ids.length) return;
        const ok = await (window.UI?.confirm || showConfirm)(
            `Retirer ${ids.length} lead(s) de la liste « ${_state.activeListNom} » ?`,
            { danger: false, confirmText: 'Retirer', title: 'Retirer de la liste' }
        );
        if (!ok) return;
        try {
            const r = await fetch(`/api/lists/${_state.activeListId}/leads`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lead_ids: ids })
            });
            const d = await r.json();
            if (!d.success) throw new Error(d.error || 'Erreur');
            showToast?.(`${d.removed} lead(s) retirés`, 'success');
            loadListLeads(_state.page);
        } catch (e) {
            showToast?.('Erreur : ' + e.message, 'error');
        }
    }

    // ─── Actions groupées ──────────────────────────────────────────────────

    async function dispatchAction(action) {
        if (!_state.activeListId) return;
        if (_state.total === 0) {
            showToast?.('La liste est vide', 'warning');
            return;
        }

        const labels = {
            audit:          `Auditer ${_state.total} lead(s) de « ${_state.activeListNom} » ?`,
            find_emails:    `Rechercher les emails pour ${_state.total} lead(s) ?`,
            generate_emails:`Générer les emails pour ${_state.total} lead(s) ?`,
            send_emails:    `Envoyer les emails approuvés pour ${_state.total} lead(s) ?`,
            export_csv:     null, // pas de confirmation pour CSV
        };

        if (action === 'export_csv') {
            // Téléchargement direct
            const a = document.createElement('a');
            a.href = `/api/lists/${_state.activeListId}/actions`;
            // On passe par un POST + form trick ou on appelle directement
            _downloadCsv();
            return;
        }

        const confirmMsg = labels[action];
        if (confirmMsg) {
            const ok = await (window.UI?.confirm || showConfirm)(
                confirmMsg,
                { confirmText: 'Confirmer', title: 'Action groupée' }
            );
            if (!ok) return;
        }

        try {
            showToast?.('Lancement de l\'action…', 'info');
            const r = await fetch(`/api/lists/${_state.activeListId}/actions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action })
            });
            const d = await r.json();
            if (d.error) throw new Error(d.error);
            showToast?.(d.message || `Action « ${action} » lancée pour ${d.lead_count} lead(s)`, 'success');
        } catch (e) {
            console.error('[Lists] dispatchAction:', e);
            showToast?.('Erreur : ' + e.message, 'error');
        }
    }

    async function _confirm(text, options = {}) {
        if (window.UI?.confirm) {
            return await window.UI.confirm(text, options);
        }
        return Promise.resolve(window.confirm(text));
    }

    async function resetAllLists() {
        const ok = await _confirm(
            'Supprimer toutes les listes existantes et recréer la liste par défaut des leads non assignés ?\nCette action est irréversible.',
            { danger: true, confirmText: 'Réinitialiser', title: 'Réinitialiser les listes' }
        );
        if (!ok) return;
        try {
            const r = await fetch('/api/lists/reset', { method: 'POST' });
            const d = await r.json();
            if (!d.success) throw new Error(d.error || 'Erreur');
            showToast?.('Toutes les listes ont été réinitialisées', 'success');
            _state.activeListId = null;
            _state.activeListNom = '';
            const placeholder = document.getElementById('lists-placeholder');
            const view = document.getElementById('lists-view');
            if (placeholder) placeholder.style.display = '';
            if (view) view.style.display = 'none';
            await loadLists();
            if (d.default_list?.list_id) {
                selectList(d.default_list.list_id);
            }
        } catch (e) {
            console.error('[Lists] resetAllLists:', e);
            showToast?.('Erreur : ' + e.message, 'error');
        }
    }

    async function refreshDefaultList() {
        const ok = await _confirm(
            'Mettre à jour la liste par défaut des leads sans liste ?',
            { confirmText: 'Rafraîchir', title: 'Liste par défaut' }
        );
        if (!ok) return;
        try {
            const r = await fetch('/api/lists/default/refresh', { method: 'POST' });
            const d = await r.json();
            if (!d.success) throw new Error(d.error || 'Erreur');
            showToast?.(`Liste par défaut rafraîchie (${d.default_list.count} leads)`, 'success');
            await loadLists();
            if (d.default_list?.list_id) {
                selectList(d.default_list.list_id);
            }
        } catch (e) {
            console.error('[Lists] refreshDefaultList:', e);
            showToast?.('Erreur : ' + e.message, 'error');
        }
    }

    async function createSectorLists() {
        const ok = await _confirm(
            'Créer des listes sectorielles avec des batches de 25 leads non contactés ?\nCela va ajouter de nouvelles listes pour chaque secteur.',
            { confirmText: 'Créer', title: 'Listes sectorielles' }
        );
        if (!ok) return;
        try {
            const r = await fetch('/api/lists/sector-batches', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ batch_size: 25 })
            });
            const d = await r.json();
            if (!d.success) throw new Error(d.error || 'Erreur');
            const created = d.created?.length || 0;
            const skipped = d.skipped?.length || 0;
            showToast?.(`Création terminée : ${created} listes créées${skipped ? `, ${skipped} secteurs ignorés` : ''}`,'success');
            await loadLists();
        } catch (e) {
            console.error('[Lists] createSectorLists:', e);
            showToast?.('Erreur : ' + e.message, 'error');
        }
    }

    async function _downloadCsv() {
        try {
            const r = await fetch(`/api/lists/${_state.activeListId}/actions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'export_csv' })
            });
            if (!r.ok) throw new Error('Erreur export');
            const blob = await r.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const nom = _state.activeListNom.replace(/[^a-z0-9]/gi, '_').toLowerCase();
            a.download = `liste_${nom}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            showToast?.('Export CSV téléchargé', 'success');
        } catch (e) {
            showToast?.('Erreur export : ' + e.message, 'error');
        }
    }

    // ─── Suppression d'une liste ───────────────────────────────────────────

    async function deleteActiveList() {
        if (!_state.activeListId) return;
        const ok = await (window.UI?.confirm || showConfirm)(
            `Supprimer la liste « ${_state.activeListNom} » ?\nLes leads ne seront pas supprimés.`,
            { danger: true, confirmText: 'Supprimer', title: 'Supprimer la liste' }
        );
        if (!ok) return;
        try {
            const r = await fetch(`/api/lists/${_state.activeListId}`, { method: 'DELETE' });
            const d = await r.json();
            if (!d.success) throw new Error(d.error || 'Erreur');
            showToast?.(`Liste « ${_state.activeListNom} » supprimée`, 'success');
            _state.activeListId = null;
            _state.activeListNom = '';
            // Masquer la vue active, montrer placeholder
            const placeholder = document.getElementById('lists-placeholder');
            const view = document.getElementById('lists-view');
            if (placeholder) placeholder.style.display = '';
            if (view) view.style.display = 'none';
            await loadLists();
        } catch (e) {
            showToast?.('Erreur : ' + e.message, 'error');
        }
    }

    // ─── Modal : Créer / Modifier une liste ───────────────────────────────

    function _initPickerGrids() {
        const emojiGrid = document.getElementById('list-emoji-grid');
        if (emojiGrid && !emojiGrid.dataset.init) {
            emojiGrid.dataset.init = '1';
            emojiGrid.innerHTML = EMOJIS.map(e =>
                `<span class="list-emoji-opt" onclick="ListsModule._pickEmoji(this,'${e}')">${e}</span>`
            ).join('');
        }
        const colorGrid = document.getElementById('list-color-grid');
        if (colorGrid && !colorGrid.dataset.init) {
            colorGrid.dataset.init = '1';
            colorGrid.innerHTML = COLORS.map(c =>
                `<span class="list-color-opt" style="background:${c}" onclick="ListsModule._pickColor(this,'${c}')"></span>`
            ).join('');
        }
    }

    function _ensureModalInContainer(modalId) {
        const modal = document.getElementById(modalId);
        if (!modal) return;
        const container = document.getElementById('modal-container');
        if (container && modal.parentElement !== container) {
            container.appendChild(modal);
        }
    }

    function openCreateModal() {
        _state.editingListId = null;
        _ensureModalInContainer('modal-list-create');
        _renderDropdownStyles(); // s'assurer que les styles sont injectés
        const title = document.getElementById('modal-list-create-title');
        if (title) title.textContent = 'Nouvelle liste';
        const nom = document.getElementById('list-create-nom');
        const desc = document.getElementById('list-create-desc');
        const id = document.getElementById('list-edit-id');
        if (nom) nom.value = '';
        if (desc) desc.value = '';
        if (id) id.value = '';
        // Reset picker selections
        document.getElementById('list-create-icone').value = '📋';
        document.getElementById('list-create-couleur').value = '#6366f1';
        _initPickerGrids();
        _highlightPicker('emoji', '📋');
        _highlightPicker('color', '#6366f1');
        if (typeof openModal === 'function') openModal('modal-list-create');
        setTimeout(() => document.getElementById('list-create-nom')?.focus(), 100);
    }

    function openEditModal(listId) {
        const lst = _state.lists.find(l => l.id === listId);
        if (!lst) return;
        _state.editingListId = listId;
        _ensureModalInContainer('modal-list-create');
        const title = document.getElementById('modal-list-create-title');
        if (title) title.textContent = 'Modifier la liste';
        const nom = document.getElementById('list-create-nom');
        const desc = document.getElementById('list-create-desc');
        const id = document.getElementById('list-edit-id');
        if (nom) nom.value = lst.nom || '';
        if (desc) desc.value = lst.description || '';
        if (id) id.value = lst.id;
        document.getElementById('list-create-icone').value = lst.icone || '📋';
        document.getElementById('list-create-couleur').value = lst.couleur || '#6366f1';
        _initPickerGrids();
        _highlightPicker('emoji', lst.icone || '📋');
        _highlightPicker('color', lst.couleur || '#6366f1');
        if (typeof openModal === 'function') openModal('modal-list-create');
        setTimeout(() => document.getElementById('list-create-nom')?.focus(), 100);
    }

    function _pickEmoji(el, emoji) {
        document.getElementById('list-create-icone').value = emoji;
        _highlightPicker('emoji', emoji);
    }

    function _pickColor(el, color) {
        document.getElementById('list-create-couleur').value = color;
        _highlightPicker('color', color);
    }

    function _highlightPicker(type, value) {
        if (type === 'emoji') {
            document.querySelectorAll('.list-emoji-opt').forEach(el => {
                el.classList.toggle('active', el.textContent === value);
            });
        } else {
            document.querySelectorAll('.list-color-opt').forEach(el => {
                el.classList.toggle('active', el.style.background === value || el.style.backgroundColor === value);
            });
        }
    }

    async function saveList() {
        const nom = document.getElementById('list-create-nom')?.value?.trim();
        if (!nom) {
            showToast?.('Le nom de la liste est requis', 'error');
            document.getElementById('list-create-nom')?.focus();
            return;
        }
        const payload = {
            nom,
            description: document.getElementById('list-create-desc')?.value?.trim() || '',
            icone: document.getElementById('list-create-icone')?.value || '📋',
            couleur: document.getElementById('list-create-couleur')?.value || '#6366f1',
        };

        try {
            let r, d;
            if (_state.editingListId) {
                r = await fetch(`/api/lists/${_state.editingListId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
            } else {
                r = await fetch('/api/lists', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
            }
            d = await r.json();
            if (d.error) throw new Error(d.error);
            if (typeof closeModal === 'function') closeModal('modal-list-create');
            showToast?.(_state.editingListId ? 'Liste mise à jour' : 'Liste créée', 'success');
            await loadLists();
            // Si on vient de créer une liste et qu'on était en mode "créer + ajouter"
            if (!_state.editingListId && _pendingAddToNew) {
                _pendingAddToNew = false;
                await addLeadsToList(d.list.id, [..._pendingLeadIds]);
                _pendingLeadIds = [];
            }
        } catch (e) {
            console.error('[Lists] saveList:', e);
            showToast?.('Erreur : ' + e.message, 'error');
        }
    }

    // ─── Ajout de leads depuis le dropdown de la vue Leads ────────────────

    let _pendingAddToNew = false;
    let _pendingLeadIds  = [];

    async function toggleAddDropdown() {
        const menu = document.getElementById('lists-add-dropdown-menu');
        if (!menu) return;
        _state.dropdownOpen = !_state.dropdownOpen;
        menu.style.display = _state.dropdownOpen ? '' : 'none';
        if (_state.dropdownOpen) {
            _renderDropdownStyles(); // s'assurer que les styles sont injectés
            // Charger les listes si pas encore en mémoire (ex: onglet Listes jamais visité)
            if (!_state.lists.length) {
                await loadLists();
            }
            _renderDropdownItems();
            // Fermer en cliquant ailleurs
            setTimeout(() => {
                document.addEventListener('click', _closeDropdownOnOutside, { once: true });
            }, 0);
        }
    }

    function _closeDropdownOnOutside(e) {
        const wrapper = document.getElementById('lists-add-dropdown');
        if (!wrapper || !wrapper.contains(e.target)) {
            const menu = document.getElementById('lists-add-dropdown-menu');
            if (menu) menu.style.display = 'none';
            _state.dropdownOpen = false;
        }
    }

    function _renderDropdownItems() {
        const container = document.getElementById('lists-dropdown-items');
        if (!container) return;
        if (!_state.lists.length) {
            container.innerHTML = `<div style="padding:12px;text-align:center;color:var(--ink3);font-size:11px">Aucune liste — crée-en une ci-dessous</div>`;
            return;
        }
        container.innerHTML = _state.lists.map(lst => `
            <div class="lists-dropdown-item" onclick="ListsModule.addSelectedToList(${lst.id})">
                <span style="font-size:14px">${_esc(lst.icone||'📋')}</span>
                <span style="flex:1;font-size:12px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${_esc(lst.nom)}</span>
                <span style="font-size:10px;color:var(--ink3)">${lst.nb_leads||0}</span>
            </div>
        `).join('');
    }

    async function addSelectedToList(listId) {
        // Fermer le dropdown
        const menu = document.getElementById('lists-add-dropdown-menu');
        if (menu) menu.style.display = 'none';
        _state.dropdownOpen = false;

        // Récupérer les IDs sélectionnés dans la vue Leads
        const ids = typeof ulGetSelectedIds === 'function' ? ulGetSelectedIds() : [];
        if (!ids.length) {
            showToast?.('Sélectionne au moins un lead', 'warning');
            return;
        }
        await addLeadsToList(listId, ids);
    }

    async function addLeadsToList(listId, leadIds) {
        if (!leadIds || !leadIds.length) return;
        try {
            const r = await fetch(`/api/lists/${listId}/leads`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lead_ids: leadIds })
            });
            const d = await r.json();
            if (!d.success) throw new Error(d.error || 'Erreur');
            const lst = _state.lists.find(l => l.id === listId);
            const nomListe = lst?.nom || `Liste #${listId}`;
            const msg = d.added > 0
                ? `${d.added} lead(s) ajouté(s) à « ${nomListe} »${d.already > 0 ? ` (${d.already} déjà présents)` : ''}`
                : `Leads déjà dans « ${nomListe} »`;
            showToast?.(msg, d.added > 0 ? 'success' : 'info');
            await loadLists(); // refresh counts
            // Si la liste active est celle qu'on vient de modifier, recharger les leads
            if (_state.activeListId === listId) loadListLeads(_state.page);
        } catch (e) {
            showToast?.('Erreur : ' + e.message, 'error');
        }
    }

    // Créer une nouvelle liste ET y ajouter la sélection courante
    function openCreateAndAdd() {
        const menu = document.getElementById('lists-add-dropdown-menu');
        if (menu) menu.style.display = 'none';
        _state.dropdownOpen = false;

        const ids = typeof ulGetSelectedIds === 'function' ? ulGetSelectedIds() : [];
        _pendingLeadIds = ids;
        _pendingAddToNew = ids.length > 0;
        openCreateModal();
    }

    // ─── Modal : Recherche de leads à ajouter depuis la vue Listes ────────

    function openAddLeadsModal() {
        if (!_state.activeListId) return;
        _ensureModalInContainer('modal-list-add-leads');
        const tbody = document.getElementById('modal-lead-search-tbody');
        if (tbody) tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:24px;color:var(--ink3)">Recherchez des leads ci-dessus.</td></tr>`;
        const searchEl = document.getElementById('modal-lead-search');
        if (searchEl) searchEl.value = '';
        const countInfo = document.getElementById('modal-lead-count-info');
        if (countInfo) countInfo.textContent = 'Saisissez un nom pour rechercher des leads existants.';
        _state.selectedToAdd.clear();
        _updateAddModalCount();
        if (typeof openModal === 'function') openModal('modal-list-add-leads');
        setTimeout(() => document.getElementById('modal-lead-search')?.focus(), 100);
    }

    let _searchTimeout = null;
    async function searchLeadsForAdd() {
        clearTimeout(_searchTimeout);
        _searchTimeout = setTimeout(_doSearchLeadsForAdd, 300);
    }

    async function _doSearchLeadsForAdd() {
        const query = document.getElementById('modal-lead-search')?.value?.trim() || '';
        const tbody = document.getElementById('modal-lead-search-tbody');
        if (!query || query.length < 2) {
            if (tbody) tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:24px;color:var(--ink3)">Saisissez au moins 2 caractères.</td></tr>`;
            return;
        }
        if (tbody) tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:16px;color:var(--ink3)">Recherche…</td></tr>`;

        try {
            const r = await fetch(`/api/leads/all?search=${encodeURIComponent(query)}&limit=30`);
            const d = await r.json();
            _state.searchResults = d.leads || [];
            const countInfo = document.getElementById('modal-lead-count-info');
            if (countInfo) countInfo.textContent = `${_state.searchResults.length} résultat(s)`;

            if (!_state.searchResults.length) {
                if (tbody) tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:24px;color:var(--ink3)">Aucun lead trouvé.</td></tr>`;
                return;
            }
            if (tbody) {
                tbody.innerHTML = _state.searchResults.map(l => `
                    <tr>
                        <td style="width:30px">
                            <input type="checkbox" class="modal-add-cb" data-id="${l.id}"
                                ${_state.selectedToAdd.has(l.id) ? 'checked' : ''}
                                onchange="ListsModule._toggleAddLead(${l.id}, this.checked)">
                        </td>
                        <td><strong style="font-size:12px">${_esc(l.nom||'—')}</strong>
                            <div style="font-size:10px;color:var(--ink3)">${_esc(l.category||l.secteur||'')}</div>
                        </td>
                        <td style="font-size:11px;color:var(--ink3)">${_esc(l.ville||'—')}</td>
                        <td><span style="font-size:10px;color:var(--ink3)">${_esc(l.statut||'—')}</span></td>
                    </tr>
                `).join('');
            }
        } catch (e) {
            console.error('[Lists] searchLeadsForAdd:', e);
        }
    }

    function _toggleAddLead(leadId, checked) {
        if (checked) _state.selectedToAdd.add(leadId);
        else _state.selectedToAdd.delete(leadId);
        _updateAddModalCount();
    }

    function toggleAllAddLeads(cb) {
        _state.searchResults.forEach(l => {
            if (cb.checked) _state.selectedToAdd.add(l.id);
            else _state.selectedToAdd.delete(l.id);
        });
        document.querySelectorAll('.modal-add-cb').forEach(el => el.checked = cb.checked);
        _updateAddModalCount();
    }

    function _updateAddModalCount() {
        const el = document.getElementById('modal-add-selected-count');
        if (el) el.textContent = `${_state.selectedToAdd.size} lead(s) sélectionné(s)`;
    }

    async function confirmAddLeads() {
        if (!_state.selectedToAdd.size) {
            showToast?.('Sélectionne au moins un lead', 'warning');
            return;
        }
        if (typeof closeModal === 'function') closeModal('modal-list-add-leads');
        await addLeadsToList(_state.activeListId, [..._state.selectedToAdd]);
        _state.selectedToAdd.clear();
    }

    // ─── Pagination ────────────────────────────────────────────────────────

    function changePage(delta) {
        const p = Math.max(1, Math.min(_state.totalPages, _state.page + delta));
        if (p !== _state.page) loadListLeads(p);
    }

    function _updatePagination() {
        const prev = document.getElementById('list-prev');
        const next = document.getElementById('list-next');
        const info = document.getElementById('list-page-info');
        if (prev) prev.disabled = _state.page <= 1;
        if (next) next.disabled = _state.page >= _state.totalPages;
        if (info) info.textContent = `page ${_state.page} / ${_state.totalPages}`;
    }

    // ─── Styles du dropdown ────────────────────────────────────────────────

    function _renderDropdownStyles() {
        if (document.getElementById('_lists-dropdown-style')) return;
        const style = document.createElement('style');
        style.id = '_lists-dropdown-style';
        style.textContent = `
            .lists-dropdown-menu {
                position: absolute;
                top: calc(100% + 6px);
                right: 0;
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: 10px;
                box-shadow: 0 8px 24px rgba(0,0,0,0.12);
                z-index: 999;
                min-width: 220px;
                max-width: 300px;
                overflow: hidden;
                animation: _cfade .12s ease;
            }
            .lists-dropdown-header {
                padding: 10px 14px;
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: .05em;
                color: var(--ink3);
                border-bottom: 1px solid var(--border);
            }
            .lists-dropdown-item {
                display: flex;
                align-items: center;
                gap: 10px;
                padding: 9px 14px;
                cursor: pointer;
                transition: background .1s;
            }
            .lists-dropdown-item:hover { background: var(--surface2); }
            .lists-dropdown-footer {
                padding: 8px;
                border-top: 1px solid var(--border);
            }
        `;
        document.head.appendChild(style);
    }

    // ─── Note, Relances, Archivage ────────────────────────────────────────

    async function saveNote(value) {
        if (!_state.activeListId) return;
        try {
            await fetch(`/api/lists/${_state.activeListId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ note: value })
            });
            const lst = _state.lists.find(l => l.id === _state.activeListId);
            if (lst) lst.note = value;
        } catch (e) {
            console.error('[Lists] saveNote:', e);
        }
    }

    function _initNoteAutoSave() {
        const ta = document.getElementById('list-active-note');
        if (!ta || ta.dataset.bound) return;
        ta.dataset.bound = '1';
        ta.addEventListener('blur', () => saveNote(ta.value));
        ta.addEventListener('input', () => {
            ta.style.height = 'auto';
            ta.style.height = Math.min(ta.scrollHeight, 80) + 'px';
        });
    }

    // ─── Modales de confirmation ──────────────────────────────────────────

    const _RELANCE_LABELS = {
        j3: 'Relance J+3',
        j7: 'Relance J+7',
        j14: 'Relance J+14',
    };

    function _openConfirmModal(title, msg, onConfirm) {
        document.getElementById('modal-confirm-title').textContent = title;
        document.getElementById('modal-confirm-msg').textContent = msg;
        const btn = document.getElementById('modal-confirm-btn');
        // Cloner pour retirer les anciens listeners
        const newBtn = btn.cloneNode(true);
        btn.parentNode.replaceChild(newBtn, btn);
        newBtn.addEventListener('click', () => {
            closeModal('modal-list-confirm');
            onConfirm();
        });
        if (typeof openModal === 'function') openModal('modal-list-confirm');
        else document.getElementById('modal-list-confirm').style.display = '';
    }

    function confirmContactee() {
        if (!_state.activeListId) return;
        const lst = _state.lists.find(l => l.id === _state.activeListId);
        if (lst?.contactee) return; // deja fait

        _openConfirmModal(
            'Marquer comme contactee',
            'Confirmer que cette liste a ete contactee entierement ?',
            () => _applyContactee(true)
        );
    }

    async function _applyContactee(value) {
        if (!_state.activeListId) return;
        try {
            await fetch(`/api/lists/${_state.activeListId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ contactee: value ? 1 : 0 })
            });
            const lst = _state.lists.find(l => l.id === _state.activeListId);
            if (lst) lst.contactee = value ? 1 : 0;
            _updateRelanceButtons();
            showToast?.('Liste marquee comme contactee', 'success');
        } catch (e) {
            console.error('[Lists] _applyContactee:', e);
        }
    }

    function confirmRelance(step) {
        if (!_state.activeListId) return;
        const lst = _state.lists.find(l => l.id === _state.activeListId);
        const field = `relance_${step}`;
        if (lst?.[field]) return; // deja fait

        _openConfirmModal(
            `Confirmer ${_RELANCE_LABELS[step]}`,
            `Marquer la ${_RELANCE_LABELS[step]} comme effectuee pour cette liste ?`,
            () => _applyRelance(step)
        );
    }

    async function _applyRelance(step) {
        if (!_state.activeListId) return;
        const field = `relance_${step}`;
        try {
            await fetch(`/api/lists/${_state.activeListId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ [field]: 1 })
            });
            const lst = _state.lists.find(l => l.id === _state.activeListId);
            if (lst) lst[field] = 1;
            _updateRelanceButtons();
            showToast?.(`${_RELANCE_LABELS[step]} confirmee`, 'success');
        } catch (e) {
            console.error('[Lists] _applyRelance:', e);
        }
    }

    function _updateRelanceButtons() {
        const lst = _state.lists.find(l => l.id === _state.activeListId);
        if (!lst) return;

        // Bouton contactee
        const btnContactee = document.getElementById('list-btn-contactee');
        if (btnContactee) {
            if (lst.contactee) {
                btnContactee.textContent = 'Contactee ✓';
                btnContactee.classList.add('btn-done');
                btnContactee.onclick = null;
            } else {
                btnContactee.textContent = '📞 Marquer contactee';
                btnContactee.classList.remove('btn-done');
                btnContactee.onclick = confirmContactee;
            }
        }

        // Boutons relance
        const steps = ['j3', 'j7', 'j14'];
        const prevDone = { j3: true, j7: !!lst.relance_j3, j14: !!lst.relance_j7 };
        steps.forEach(step => {
            const btn = document.getElementById(`list-btn-relance-${step}`);
            if (!btn) return;
            const field = `relance_${step}`;
            const canShow = prevDone[step];
            if (!canShow) {
                btn.style.display = 'none';
                return;
            }
            btn.style.display = '';
            if (lst[field]) {
                btn.textContent = `${_RELANCE_LABELS[step]} ✓`;
                btn.classList.add('btn-done');
                btn.onclick = null;
            } else {
                btn.textContent = `✉️ ${_RELANCE_LABELS[step]}`;
                btn.classList.remove('btn-done');
                btn.onclick = () => confirmRelance(step);
            }
        });
    }

    async function archiveList() {
        if (!_state.activeListId) return;
        if (!confirm('Archiver cette liste ? Les leads restent accessibles dans les autres vues.')) return;
        try {
            await fetch(`/api/lists/${_state.activeListId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ archived: 1 })
            });
            showToast?.('Liste archivée', 'success');
            await loadLists();
            // Retour à la vue placeholder
            const placeholder = document.getElementById('lists-placeholder');
            const view = document.getElementById('lists-view');
            if (placeholder) placeholder.style.display = '';
            if (view) view.style.display = 'none';
            _state.activeListId = null;
        } catch (e) {
            console.error('[Lists] archiveList:', e);
            showToast?.('Erreur : ' + e.message, 'error');
        }
    }

    async function toggleArchives(showArchived) {
        try {
            const url = showArchived ? '/api/lists?archived=1' : '/api/lists';
            const r = await fetch(url);
            const d = await r.json();
            if (d.error) throw new Error(d.error);
            _state.lists = d.lists || [];
            _renderSidebarLists();
        } catch (e) {
            console.error('[Lists] toggleArchives:', e);
        }
    }

    // ─── Mobile sidebar ───────────────────────────────────────────────────

    function toggleMobileSidebar() {
        const sidebar = document.getElementById('lists-sidebar');
        const overlay = document.getElementById('lists-sidebar-overlay');
        if (sidebar) sidebar.classList.toggle('mobile-open');
        if (overlay) overlay.classList.toggle('open');
    }

    function closeMobileSidebar() {
        const sidebar = document.getElementById('lists-sidebar');
        const overlay = document.getElementById('lists-sidebar-overlay');
        if (sidebar) sidebar.classList.remove('mobile-open');
        if (overlay) overlay.classList.remove('open');
    }

    // ─── Toolbar expand/collapse ──────────────────────────────────────────

    function toggleToolbar() {
        const extra = document.getElementById('lists-toolbar-extra');
        const toggle = document.getElementById('lists-toolbar-toggle');
        if (!extra || !toggle) return;
        const isOpen = extra.style.display !== 'none';
        extra.style.display = isOpen ? 'none' : 'flex';
        toggle.classList.toggle('open', !isOpen);
    }

    // ─── Copier email ─────────────────────────────────────────────────────

    async function copyEmail(email) {
        if (!email) return;
        try {
            await navigator.clipboard.writeText(email);
            showToast?.('Email copié !', 'success');
        } catch (e) {
            // Fallback pour les navigateurs plus anciens
            const ta = document.createElement('textarea');
            ta.value = email;
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
            showToast?.('Email copié !', 'success');
        }
    }

    // ─── Utilitaires ───────────────────────────────────────────────────────

    function _esc(s) {
        return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    // ─── API publique ──────────────────────────────────────────────────────

    return {
        init,
        loadLists,
        selectList,
        loadListLeads,
        toggleAll,
        removeLead,
        removeSelectedLeads,
        deleteActiveList,
        dispatchAction,
        openCreateModal,
        openEditModal,
        openAddLeadsModal,
        searchLeadsForAdd,
        toggleAllAddLeads,
        confirmAddLeads,
        saveList,
        changePage,
        toggleAddDropdown,
        addSelectedToList,
        addLeadsToList,
        resetAllLists,
        refreshDefaultList,
        createSectorLists,
        openCreateAndAdd,
        saveNote,
        confirmContactee,
        confirmRelance,
        copyEmail,
        archiveList,
        toggleArchives,
        toggleMobileSidebar,
        closeMobileSidebar,
        toggleToolbar,
        // exposes pour les event listeners inline HTML
        _pickEmoji,
        _pickColor,
        _toggleAddLead,
    };

})();
