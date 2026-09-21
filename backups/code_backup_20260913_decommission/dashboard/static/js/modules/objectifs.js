/**
 * dashboard/static/js/modules/objectifs.js
 * Modèle v2 « Objectif » : chaque objectif regroupe des leads ; la page Leads
 * n'affiche que les leads de l'objectif actuellement sélectionné.
 *
 * Couplage volontairement léger avec unified_leads.js :
 *   - `_ul.v2ObjectifId` (null = vue "Archive" legacy) pilote l'endpoint utilisé.
 */
(function () {
    'use strict';

    const LS_KEY = 'pm_objectif_id';

    function esc(s) {
        return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function toast(msg, type) {
        if (typeof window.showToast === 'function') window.showToast(msg, type || 'success');
    }

    function sel(id) { return document.getElementById(id); }

    const ObjectifsModule = {
        objectifs: [],

        get currentId() { return (window._ul && typeof window._ul.v2ObjectifId !== 'undefined') ? window._ul.v2ObjectifId : null; },

        async init() {
            this.objectifs = await this.load();
            this.render();
            try {
                const r = await fetch('/api/v2/auto-send');
                const d = await r.json();
                const el = sel('obj-auto-send');
                if (el) el.checked = !!(d && d.enabled);
            } catch (e) { /* header ou endpoint absent : on ignore */ }
            const saved = localStorage.getItem(LS_KEY);
            await this.doSelect(saved, { silent: true });
        },

        async load() {
            try {
                const r = await fetch('/api/v2/objectifs');
                const d = await r.json();
                return (d.objectifs || []).filter(o => !o.statut || o.statut !== 'archive');
            } catch (e) {
                console.error('[objectifs] load', e);
                return [];
            }
        },

        render() {
            const el = sel('obj-select');
            if (!el) return;
            const current = this.currentId;
            el.innerHTML = '<option value="">— Archive —</option>' +
                this.objectifs.map(o =>
                    `<option value="${o.id}" ${String(o.id) === String(current) ? 'selected' : ''}>${esc(o.nom)}${o.archived ? ' (archivé)' : ''}</option>`
                ).join('');
            const label = sel('obj-label-current');
            if (label) {
                const n = this.objectifs.find(o => o.id === current)?.nom;
                label.textContent = current ? `Objectif : ${n || current}` : 'Objectif : — Archive —';
            }
        },

        async onSelect() {
            const el = sel('obj-select');
            await this.doSelect(el && el.value);
        },

        async doSelect(rawId, { silent } = {}) {
            const id = rawId ? parseInt(rawId, 10) : null;
            if (window._ul) {
                window._ul.v2ObjectifId = id;
                window._ul.v2ObjectifNom = this.objectifs.find(o => o.id === id)?.nom || '';
            }
            if (id) localStorage.setItem(LS_KEY, String(id));
            else localStorage.removeItem(LS_KEY);

            this.render();
            this.refreshStats();
            const actionsEl = sel('obj-actions');
            if (actionsEl) actionsEl.style.display = id ? 'flex' : 'none';
            if (typeof window._ulSetStatutFilter === 'function') window._ulSetStatutFilter(!!id);

            if (typeof window.unifiedLeadsLoad === 'function' && !silent) {
                window.unifiedLeadsLoad(1);
            }
            if (!silent) toast(id ? `Objectif actif : ${this.objectifs.find(o => o.id === id)?.nom || ''}` : 'Vue Archive (tous les leads)', 'success');
            if (silent && typeof window.unifiedLeadsLoad === 'function') {
                window.unifiedLeadsLoad(1);
            }
            // Les stats du cockpit (accueil) suivent l'objectif sélectionné
            if (typeof window.StatsModule !== 'undefined' && typeof window.StatsModule.refresh === 'function') {
                window.StatsModule.refresh();
            }
        },

        async refreshStats() {
            const id = this.currentId;
            const el = sel('obj-stats');
            if (!id) {
                if (el) { el.style.display = 'none'; el.textContent = ''; }
                return;
            }
            if (!el) return;
            el.style.display = '';
            try {
                const r = await fetch(`/api/v2/objectifs/${id}/stats`);
                const d = await r.json();
                if (!d.success) throw new Error(d.error);
                const s = d.stats;
                el.textContent = `${s.total} lead${s.total > 1 ? 's' : ''} · ${s.repondu} réponse${s.repondu > 1 ? 's' : ''}`;
                el.style.color = s.repondu > 0 ? 'var(--success,#10b981)' : '';
            } catch (e) {
                console.error('[objectifs] stats', e);
                el.textContent = '';
            }
        },

        openCreate() {
            sel('obj-create-nom').value = '';
            sel('obj-create-desc').value = '';
            if (typeof window.openModal === 'function') window.openModal('modal-obj-create');
            else { const m = sel('modal-obj-create'); if (m) m.style.display = 'flex'; }
            const input = sel('obj-create-nom');
            if (input) setTimeout(() => input.focus(), 50);
        },

        async create() {
            const nom = (sel('obj-create-nom')?.value || '').trim();
            if (!nom) { toast("Le nom de l'objectif est requis", 'error'); return; }
            try {
                const r = await fetch('/api/v2/objectifs', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ nom, description: (sel('obj-create-desc')?.value || '').trim() }),
                });
                const d = await r.json();
                if (!d.success) throw new Error(d.error || 'Erreur création');
                if (typeof window.closeModal === 'function') window.closeModal('modal-obj-create');
                else { const m = sel('modal-obj-create'); if (m) m.style.display = 'none'; }
                toast(`Objectif « ${d.objectif.nom} » créé`, 'success');
                this.objectifs = await this.load();
                await this.doSelect(d.objectif.id);
            } catch (e) {
                console.error('[objectifs] create', e);
                toast(e.message || 'Erreur création', 'error');
            }
        },

        openManage() {
            const id = this.currentId;
            const o = this.objectifs.find(x => x.id === id);
            if (!o) return;
            sel('obj-manage-name').textContent = `id ${o.id} · ${o.nb_leads || 0} leads`;
            sel('obj-manage-nom').value = o.nom || '';
            sel('obj-manage-desc').value = o.description || '';
            const auto = sel('obj-manage-envoi-auto');
            if (auto) auto.checked = !!o.envoi_auto;
            if (typeof window.openModal === 'function') window.openModal('modal-obj-manage');
            else { const m = sel('modal-obj-manage'); if (m) m.style.display = 'flex'; }
        },

        async saveManage() {
            const id = this.currentId;
            const nom = (sel('obj-manage-nom')?.value || '').trim();
            if (!id || !nom) { toast('Nom requis', 'error'); return; }
            const auto = sel('obj-manage-envoi-auto');
            try {
                const r = await fetch(`/api/v2/objectifs/${id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        nom,
                        description: (sel('obj-manage-desc')?.value || '').trim(),
                        envoi_auto: auto ? auto.checked : true,
                    }),
                });
                const d = await r.json();
                if (!d.success) throw new Error(d.error || 'Erreur');
                if (typeof window.closeModal === 'function') window.closeModal('modal-obj-manage');
                toast('Objectif mis à jour', 'success');
                this.objectifs = await this.load();
                await this.doSelect(id);
            } catch (e) {
                console.error('[objectifs] manage', e);
                toast(e.message || 'Erreur', 'error');
            }
        },

        async toggleAutoSend(checked) {
            const el = sel('obj-auto-send');
            try {
                const r = await fetch('/api/v2/auto-send', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enabled: !!checked }),
                });
                const d = await r.json();
                if (!d.success) throw new Error(d.error || 'Erreur');
                if (el) el.checked = !!d.enabled;
                toast(d.enabled ? 'Auto-envoi global activé' : 'Auto-envoi global coupé', 'success');
            } catch (e) {
                console.error('[objectifs] auto-send', e);
                if (el) el.checked = !checked;
                toast(e.message || 'Erreur', 'error');
            }
        },

        async sendNow() {
            const id = this.currentId;
            if (!id) { toast('Sélectionnez un objectif', 'error'); return; }
            const o = this.objectifs.find(x => x.id === id);
            const ok = typeof window.UI !== 'undefined'
                ? await window.UI.confirm(`Déclencher l'envoi initial maintenant pour « ${o?.nom || id} » ?`)
                : typeof window.showConfirm === 'function'
                    ? await window.showConfirm(`Déclencher l'envoi initial maintenant pour « ${o?.nom || id} » ?`)
                    : window.confirm(`Déclencher l'envoi initial maintenant pour « ${o?.nom || id} » ?`);
            if (!ok) return;
            try {
                const r = await fetch(`/api/v2/objectifs/${id}/send`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ limit: 1000 }),
                });
                const d = await r.json();
                if (!d.success) throw new Error(d.error || 'Erreur');
                const total = (d.initials || 0) + (d.relances || 0);
                toast(`Lancement : ${total} candidat(s) (${d.initials || 0} initial, ${d.relances || 0} relance)`, 'success');
                await this.refreshStats();
                if (typeof window.unifiedLeadsLoad === 'function') window.unifiedLeadsLoad(1);
            } catch (e) {
                console.error('[objectifs] sendNow', e);
                toast(e.message || 'Erreur', 'error');
            }
        },

        // ── Séquence & relances (templates positions 0..N) ─────────────────────

        seqTemplates: [],

        seqLabel(pos) {
            return { 0: '0 — Envoi initial', 1: '1 — Relance 1', 2: '2 — Relance 2', 3: '3 — Relance 3' }[pos] ?? `pos ${pos}`;
        },

        async openSequence() {
            const id = this.currentId;
            const o = this.objectifs.find(x => x.id === id);
            if (!id || !o) { toast('Sélectionnez un objectif', 'error'); return; }
            if (typeof window.openModal === 'function') window.openModal('modal-obj-sequence');
            else { const m = sel('modal-obj-sequence'); if (m) m.style.display = 'flex'; }
            sel('obj-seq-name').textContent = `id ${o.id} · ${o.nom}`;
            await this.seqLoad();
        },

        async seqLoad() {
            const id = this.currentId;
            try {
                const r = await fetch(`/api/v2/objectifs/${id}/sequence`);
                const d = await r.json();
                if (!d.success) throw new Error(d.error || 'Erreur');
                this.seqTemplates = d.templates || [];
                this.seqRender();
            } catch (e) {
                console.error('[objectifs] seq', e);
                toast(e.message || 'Erreur', 'error');
            }
        },

        seqRender() {
            const el = sel('obj-sequence-list');
            if (!el) return;
            const list = [...this.seqTemplates].sort((a, b) => {
                const ga = a.objectif_id ? 1 : 0, gb = b.objectif_id ? 1 : 0;
                return (ga - gb) || (a.position - b.position);
            });
            if (!list.length) {
                el.innerHTML = '<div style="font-size:12px;color:var(--ink3);padding:6px 2px">Aucune étape : seul le template générique « Template par défaut » (position 0) est utilisé pour les initiaux.</div>';
                return;
            }
            el.innerHTML = list.map(t => `
                <div data-tid="${t.id}" style="border:1px solid var(--border);border-radius:10px;padding:10px;display:flex;flex-direction:column;gap:8px;opacity:${t.actif ? 1 : 0.55}">
                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                        <span style="font-size:12px;font-weight:700;color:var(--ink);width:120px;flex-shrink:0">${esc(this.seqLabel(t.position || 0))}</span>
                        ${t.objectif_id ? '' : '<span style="font-size:10px;color:var(--ink3)">générique (défaut)</span>'}
                        <input type="text" data-f="objet" value="${esc(t.objet)}" class="inp sm" style="flex:1;min-width:180px" placeholder="Objet">
                        <input type="number" data-f="delai_jours" value="${t.delai_jours || 0}" class="inp sm" style="width:74px" min="0" title="Délai en jours après la touche précédente">
                        <label style="display:flex;align-items:center;gap:4px;font-size:11px;color:var(--ink3);white-space:nowrap">
                            <input type="checkbox" data-f="actif" ${t.actif ? 'checked' : ''}> Actif
                        </label>
                        <button class="btn sm" onclick="ObjectifsModule.seqSave(${t.id})" title="Enregistrer">💾</button>
                        ${t.objectif_id ? `<button class="btn sm" onclick="ObjectifsModule.seqDel(${t.id})" title="Supprimer (dédié)">🗑</button>` : ''}
                    </div>
                    <textarea data-f="corps" class="inp" style="resize:vertical;height:58px" placeholder="Corps">${esc(t.corps)}</textarea>
                </div>`).join('');
        },

        async seqSave(tid) {
            const row = document.querySelector(`#obj-sequence-list [data-tid="${tid}"]`);
            if (!row) return;
            const get = (f) => row.querySelector(`[data-f="${f}"]`);
            try {
                const r = await fetch(`/api/v2/sequence-templates/${tid}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        objet: get('objet').value,
                        corps: get('corps').value,
                        delai_jours: parseInt(get('delai_jours').value || '0', 10),
                        actif: get('actif').checked,
                    }),
                });
                const d = await r.json();
                if (!d.success) throw new Error(d.error || 'Erreur');
                toast('Étape enregistrée', 'success');
                await this.seqLoad();
            } catch (e) {
                console.error('[objectifs] seqSave', e);
                toast(e.message || 'Erreur', 'error');
            }
        },

        async seqAdd() {
            const id = this.currentId;
            try {
                const r = await fetch(`/api/v2/objectifs/${id}/sequence`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        position: parseInt(sel('seq-add-pos')?.value || '1', 10),
                        delai_jours: parseInt(sel('seq-add-delai')?.value || '0', 10),
                        objet: sel('seq-add-objet')?.value || '',
                        corps: sel('seq-add-corps')?.value || '',
                    }),
                });
                const d = await r.json();
                if (!d.success) throw new Error(d.error || 'Erreur');
                if (sel('seq-add-objet')) sel('seq-add-objet').value = '';
                if (sel('seq-add-corps')) sel('seq-add-corps').value = '';
                toast('Étape ajoutée', 'success');
                await this.seqLoad();
            } catch (e) {
                console.error('[objectifs] seqAdd', e);
                toast(e.message || 'Erreur', 'error');
            }
        },

        async seqDel(tid) {
            const ok = window.confirm('Supprimer cette étape dédiée à l\'objectif ?');
            if (!ok) return;
            try {
                const r = await fetch(`/api/v2/sequence-templates/${tid}`, { method: 'DELETE' });
                const d = await r.json();
                if (!d.success) throw new Error(d.error || 'Erreur');
                toast('Étape supprimée', 'success');
                await this.seqLoad();
            } catch (e) {
                console.error('[objectifs] seqDel', e);
                toast(e.message || 'Erreur', 'error');
            }
        },

        async deleteCurrent() {
            const id = this.currentId;
            const o = this.objectifs.find(x => x.id === id);
            if (!id) return;
            const ok = typeof window.UI !== 'undefined'
                ? await window.UI.confirm(`Supprimer l'objectif « ${o?.nom || id} » et ses leads ? Irréversible.`, { danger: true })
                : typeof window.showConfirm === 'function'
                    ? await window.showConfirm(`Supprimer l'objectif « ${o?.nom || id} » et ses leads ? Irréversible.`, { danger: true })
                    : window.confirm(`Supprimer l'objectif « ${o?.nom || id} » et ses leads ?`);
            if (!ok) return;
            try {
                const r = await fetch(`/api/v2/objectifs/${id}`, { method: 'DELETE' });
                const d = await r.json();
                if (!d.success) throw new Error(d.error || 'Erreur');
                if (typeof window.closeModal === 'function') window.closeModal('modal-obj-manage');
                toast('Objectif supprimé', 'success');
                this.objectifs = await this.load();
                await this.doSelect(null);
            } catch (e) {
                console.error('[objectifs] delete', e);
                toast(e.message || 'Erreur', 'error');
            }
        },
    };

    window.ObjectifsModule = ObjectifsModule;
})();