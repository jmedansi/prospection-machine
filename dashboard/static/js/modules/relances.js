/**
 * dashboard/static/js/modules/relances.js
 * Module de gestion des relances (pending approval + historique)
 */

const RelancesModule = (() => {
    let _currentFilter = 'tous';
    let _historyPage = 1;
    let _selectedIds = new Set();
    let _previewSeqId = null;

    // ── Utilitaires ──────────────────────────────────────────────

    function _fmt(dateStr) {
        if (!dateStr) return '—';
        const d = new Date(dateStr);
        if (isNaN(d)) return dateStr;
        return d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' })
             + ' ' + d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
    }

    function _statusBadge(statut) {
        const map = {
            pending_approval: { bg: 'rgba(245,158,11,0.15)', color: '#f59e0b', label: 'En attente' },
            sent:             { bg: 'rgba(16,185,129,0.15)', color: '#10b981', label: 'Envoyée' },
            planned:          { bg: 'rgba(99,102,241,0.15)', color: '#6366f1', label: 'Planifiée' },
            cancelled:        { bg: 'rgba(107,114,128,0.15)', color: '#6b7280', label: 'Annulée' },
        };
        const s = map[statut] || { bg: 'rgba(107,114,128,0.1)', color: '#6b7280', label: statut };
        return `<span style="font-size:11px;font-weight:600;padding:2px 8px;border-radius:999px;background:${s.bg};color:${s.color}">${s.label}</span>`;
    }

    function _typeLabel(t) {
        return { relance_1: 'Relance 1 (J+3)', relance_2: 'Relance 2 (J+7)', relance_special: 'Spéciale (J+14)' }[t] || t;
    }

    // ── API Calls ────────────────────────────────────────────────

    async function _fetchPending() {
        const r = await fetch('/api/sequences/pending');
        if (!r.ok) throw new Error('API error');
        return r.json();
    }

    async function _fetchHistory(filter, page) {
        const params = new URLSearchParams({ page, limit: 30 });
        if (filter && filter !== 'tous') params.append('statut', filter);
        const r = await fetch(`/api/sequences/history?${params}`);
        if (!r.ok) throw new Error('API error');
        return r.json();
    }

    async function _approveSingle(seq_id) {
        const r = await fetch('/api/sequences/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ seq_id })
        });
        return r.json();
    }

    async function _approveMany(seq_ids) {
        const r = await fetch('/api/sequences/approve-bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ seq_ids })
        });
        return r.json();
    }

    async function _cancelSingle(seq_id) {
        const r = await fetch('/api/sequences/cancel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ seq_id })
        });
        return r.json();
    }

    // ── Rendu Tableau Pending ────────────────────────────────────

    async function _renderPending() {
        const tbody = document.getElementById('tbody-relances-pending');
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:1.5rem;color:var(--muted)">Chargement...</td></tr>';
        try {
            const data = await _fetchPending();
            const rows = data.sequences || [];
            const count = rows.length;

            // Stats
            document.getElementById('relances-stat-pending').textContent = count;
            document.getElementById('relances-pending-badge').textContent = count;
            document.getElementById('btn-approve-all-count').textContent = count;

            if (!rows.length) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--muted)">Aucune relance en attente ✓</td></tr>';
                return;
            }

            tbody.innerHTML = rows.map(seq => `
                <tr id="row-pending-${seq.id}">
                    <td>
                        <input type="checkbox" class="relance-cb" value="${seq.id}"
                            onchange="RelancesModule.onCheck(${seq.id}, this.checked)">
                    </td>
                    <td style="font-weight:600">${seq.nom || '—'}</td>
                    <td style="font-size:12px;color:var(--muted)">${seq.email || '—'}</td>
                    <td>${_typeLabel(seq.email_type)}</td>
                    <td style="font-size:12px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${(seq.email_objet||'').replace(/"/g,'&quot;')}">${seq.email_objet || '—'}</td>
                    <td style="font-size:12px;color:var(--muted)">${_fmt(seq.date_planifiee)}</td>
                    <td>
                        <div style="display:flex;gap:6px">
                            <button class="btn sm" style="font-size:11px;background:rgba(99,102,241,0.15);color:#6366f1;padding:3px 8px"
                                onclick="RelancesModule.preview(${seq.id})">
                                Voir
                            </button>
                            <button class="btn sm" style="font-size:11px;background:rgba(16,185,129,0.15);color:#10b981;padding:3px 8px"
                                onclick="RelancesModule.approveSingle(${seq.id})">
                                ✓ Approuver
                            </button>
                            <button class="btn sm" style="font-size:11px;background:rgba(239,68,68,0.1);color:#ef4444;padding:3px 8px"
                                onclick="RelancesModule.cancelSingle(${seq.id})">
                                ✕
                            </button>
                        </div>
                    </td>
                </tr>
            `).join('');

        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:1.5rem;color:#ef4444">Erreur: ${e.message}</td></tr>`;
        }
    }

    // ── Rendu Historique ─────────────────────────────────────────

    async function _renderHistory() {
        const tbody = document.getElementById('tbody-relances-history');
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:1.5rem;color:var(--muted)">Chargement...</td></tr>';
        try {
            const data = await _fetchHistory(_currentFilter, _historyPage);
            const rows = data.sequences || [];

            // Update global stats
            if (data.stats) {
                document.getElementById('relances-stat-sent').textContent      = data.stats.sent || 0;
                document.getElementById('relances-stat-r1').textContent        = data.stats.relance_1 || 0;
                document.getElementById('relances-stat-r2').textContent        = data.stats.relance_2 || 0;
                document.getElementById('relances-stat-rs').textContent        = data.stats.relance_special || 0;
                document.getElementById('relances-stat-cancelled').textContent = data.stats.cancelled || 0;
            }

            if (!rows.length) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--muted)">Aucune séquence</td></tr>';
                return;
            }

            tbody.innerHTML = rows.map(seq => `
                <tr>
                    <td style="font-weight:600">${seq.nom || '—'}</td>
                    <td style="font-size:12px;color:var(--muted)">${seq.email || '—'}</td>
                    <td style="font-size:12px">${_typeLabel(seq.email_type)}</td>
                    <td>${_statusBadge(seq.statut)}</td>
                    <td style="font-size:12px;color:var(--muted)">${_fmt(seq.date_email_initial)}</td>
                    <td style="font-size:12px">${_fmt(seq.date_planifiee)}</td>
                    <td style="font-size:12px;color:var(--muted)">${_fmt(seq.date_envoi)}</td>
                </tr>
            `).join('');

            // Pagination
            _renderPagination(data.total, data.page, data.total_pages);

        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:1.5rem;color:#ef4444">Erreur: ${e.message}</td></tr>`;
        }
    }

    function _renderPagination(total, current, totalPages) {
        const el = document.getElementById('relances-history-pagination');
        if (!el || totalPages <= 1) { if (el) el.innerHTML = ''; return; }
        let html = '';
        for (let i = 1; i <= totalPages; i++) {
            html += `<button class="btn sm" style="${i===current?'background:var(--accent);color:#fff':''}" onclick="RelancesModule.goPage(${i})">${i}</button>`;
        }
        el.innerHTML = `<span style="font-size:12px;color:var(--muted)">${total} séquences</span> &nbsp; ${html}`;
    }

    // ── Actions ──────────────────────────────────────────────────

    function toggleSelectAll(checked) {
        document.querySelectorAll('.relance-cb').forEach(cb => {
            cb.checked = checked;
            const id = parseInt(cb.value);
            checked ? _selectedIds.add(id) : _selectedIds.delete(id);
        });
        _updateBtnSelected();
    }

    function onCheck(id, checked) {
        checked ? _selectedIds.add(id) : _selectedIds.delete(id);
        _updateBtnSelected();
    }

    function _updateBtnSelected() {
        const btn = document.getElementById('btn-approve-selected');
        if (btn) btn.style.display = _selectedIds.size > 0 ? '' : 'none';
        if (btn) btn.textContent = `✓ Approuver (${_selectedIds.size})`;
    }

    async function approveSingle(seq_id) {
        const row = document.getElementById(`row-pending-${seq_id}`);
        if (row) row.style.opacity = '0.5';
        try {
            const data = await _approveSingle(seq_id);
            if (data.success) {
                _showToast(`✓ Relance approuvée et envoyée`, 'success');
                await reload();
            } else {
                _showToast(`Erreur: ${data.error || 'Envoi échoué'}`, 'error');
                if (row) row.style.opacity = '1';
            }
        } catch (e) {
            _showToast(`Erreur réseau: ${e.message}`, 'error');
            if (row) row.style.opacity = '1';
        }
    }

    async function approveSelected() {
        if (!_selectedIds.size) return;
        const ids = [..._selectedIds];
        const btn = document.getElementById('btn-approve-selected');
        if (btn) { btn.disabled = true; btn.textContent = 'Envoi...'; }
        try {
            const data = await _approveMany(ids);
            _showToast(`✓ ${data.sent || 0} relances envoyées`, 'success');
            _selectedIds.clear();
            await reload();
        } catch (e) {
            _showToast(`Erreur: ${e.message}`, 'error');
        } finally {
            if (btn) { btn.disabled = false; _updateBtnSelected(); }
        }
    }

    async function approveAll() {
        const btn = document.getElementById('btn-approve-all');
        if (btn) { btn.disabled = true; btn.textContent = 'Envoi en cours...'; }
        try {
            const data = await _approveMany(null); // null = toutes
            _showToast(`✓ ${data.sent || 0} relances envoyées`, 'success');
            _selectedIds.clear();
            await reload();
        } catch (e) {
            _showToast(`Erreur: ${e.message}`, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.innerHTML = `<svg viewBox="0 0 16 16" fill="none" width="13" height="13"><path d="M2 8l4 4 8-8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg> Tout approuver (<span id="btn-approve-all-count">0</span>)`; }
        }
    }

    async function cancelSingle(seq_id) {
        if (!confirm('Annuler cette relance ?')) return;
        try {
            const data = await _cancelSingle(seq_id);
            if (data.success) {
                _showToast('Relance annulée', 'info');
                await reload();
            } else {
                _showToast(`Erreur: ${data.error}`, 'error');
            }
        } catch (e) {
            _showToast(`Erreur réseau: ${e.message}`, 'error');
        }
    }

    // ── Prévisualisation ─────────────────────────────────────────

    async function preview(seq_id) {
        _previewSeqId = seq_id;
        try {
            const data = await _fetchPending();
            const seq = (data.sequences || []).find(s => s.id === seq_id);
            if (!seq) return;
            document.getElementById('prev-nom').textContent   = seq.nom || '—';
            document.getElementById('prev-email').textContent = seq.email || '—';
            document.getElementById('prev-type').textContent  = _typeLabel(seq.email_type);
            document.getElementById('prev-objet').textContent = seq.email_objet || '—';
            document.getElementById('prev-corps').textContent = seq.email_corps || '(contenu vide)';
            document.getElementById('modal-relance-preview').style.display = 'flex';
        } catch (e) {
            _showToast('Impossible de charger l\'aperçu', 'error');
        }
    }

    function closePreview() {
        document.getElementById('modal-relance-preview').style.display = 'none';
        _previewSeqId = null;
    }

    async function approveFromPreview() {
        if (!_previewSeqId) return;
        closePreview();
        await approveSingle(_previewSeqId);
    }

    async function cancelFromPreview() {
        if (!_previewSeqId) return;
        closePreview();
        await cancelSingle(_previewSeqId);
    }

    // ── Filtres & Navigation ─────────────────────────────────────

    function setFilter(filter, btn) {
        _currentFilter = filter;
        _historyPage = 1;
        document.querySelectorAll('#tbl-relances-history').forEach(() => {});
        document.querySelectorAll('[id^="rf-"]').forEach(b => b.classList.remove('active'));
        if (btn) btn.classList.add('active');
        _renderHistory();
    }

    function goPage(page) {
        _historyPage = page;
        _renderHistory();
    }

    async function reload() {
        await Promise.all([_renderPending(), _renderHistory()]);
    }

    // ── Toast ────────────────────────────────────────────────────

    function _showToast(msg, type = 'info') {
        if (typeof showToast === 'function') { showToast(msg, type); return; }
        const container = document.getElementById('toast-container');
        if (!container) return;
        const colors = { success: '#10b981', error: '#ef4444', info: '#6366f1' };
        const t = document.createElement('div');
        t.style.cssText = `background:${colors[type]||colors.info};color:#fff;padding:10px 16px;border-radius:8px;margin-bottom:8px;font-size:13px;font-weight:500;box-shadow:0 4px 12px rgba(0,0,0,0.3)`;
        t.textContent = msg;
        container.appendChild(t);
        setTimeout(() => t.remove(), 3500);
    }

    // ── Init ─────────────────────────────────────────────────────

    function init() {
        reload();
    }

    return {
        init, reload, setFilter, goPage,
        toggleSelectAll, onCheck,
        approveSingle, approveSelected, approveAll,
        cancelSingle, cancelFromPreview,
        preview, closePreview, approveFromPreview
    };
})();
