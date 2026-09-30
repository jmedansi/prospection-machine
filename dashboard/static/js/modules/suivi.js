/**
 * dashboard/static/js/modules/suivi.js
 * Onglet « Suivi » V6 — stats de la campagne active + historique des échanges v2.
 *
 * Deux sources, comme le Cockpit :
 *   - GET /api/stats?objectif_id=<campagne> (alias campagne-aware) → cards
 *     (envoyés, taux de réponse, réponses, RDV). Sans objectif_id → vue v2 GLOBALE.
 *   - GET /api/v2/suivi/echanges?campagne_id= → journal complet prospect_events
 *     (initial, relance_k, reponse, ndr, auto_reply, validation_requete,
 *     désinscription, creation, import, status_change).
 *
 * DOM cible (views/sections/suivi_v6.html) :
 *   #suivi-stat-*    cards
 *   #suivi-bounce-block / #suivi-bounce-list  récap des bounces à statuer
 *   #suivi-filter-type  filtre par type d'événement
 *   #tbody-suivi     timeline
 *   #suivi-count     compteur
 *   #suivi-contexte  contexte (campagne active / toutes)
 *
 * Auto-refresh : toutes les 30 s quand l'onglet Suivi est visible.
 */
(function () {
    'use strict';

    const EVENT_LABELS = {
        'creation':        ['Création', '#10b981'],
        'import':          ['Import', '#10b981'],
        'initial':         ['Email initial', '#3b82f6'],
        'relance_1':       ['Relance 1', '#6366f1'],
        'relance_2':       ['Relance 2', '#7c3aed'],
        'relance_3':       ['Relance 3', '#8b5cf6'],
        'reponse':         ['Réponse reçue', '#0ea5e9'],
        'ndr':             ['NDR / Invalide', '#ef4444'],
        'auto_reply':      ['Réponse auto (OOO)', '#f59e0b'],
        'validation_requete': ['Validation Telegram', '#f59e0b'],
        'desinscription':  ['Désinscription', '#ef4444'],
        'status_change':   ['Changement de statut', '#64748b'],
    };

    const FILTERS = {
        '': null,
        'envois': ['initial', 'relance_1', 'relance_2', 'relance_3'],
        'reponse': ['reponse'],
        'ndr': ['ndr'],
        'auto_reply': ['auto_reply'],
        'validation': ['validation_requete'],
        'desinscription': ['desinscription'],
        'creation': ['creation', 'import'],
    };

    const BOUNCE_MOTIF = {
        'bounce_dur': ['Bounce', '#ef4444'],
        'plainte': ['Plainte spam', '#f59e0b'],
    };

    function esc(s) {
        return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function sel(id) { return document.getElementById(id); }

    function fmtDateTime(v) {
        if (!v) return '—';
        const dt = new Date(String(v).replace(' ', 'T'));
        if (isNaN(dt.getTime())) return '—';
        const d = dt.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' });
        const t = dt.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
        return `${d} ${t}`;
    }

    function labelFor(ev) {
        const [label, color] = EVENT_LABELS[ev.event_type] || [ev.event_type, '#64748b'];
        return { label, color };
    }

    function relanceNum(t) {
        const m = /^relance_(\d+)$/.exec(t || '');
        return m ? parseInt(m[1], 10) : null;
    }

    function detailFor(ev) {
        const p = ev.payload || {};
        const t = ev.event_type;
        if (t === 'reponse') {
            const bits = [];
            if (p.sujet) bits.push(`« ${p.sujet} »`);
            if (p.from_addr) bits.push(`de ${p.from_addr}`);
            if (p.snippet) bits.push(String(p.snippet).slice(0, 120));
            return bits.length ? bits.join(' — ') : 'Réponse humaine détectée';
        }
        if (t === 'ndr') return p.sujet ? `« ${p.sujet} »` : 'Message non délivrable (mailer-daemon / NDR)';
        if (t === 'auto_reply') return p.sujet ? `« ${p.sujet} »` : 'Réponse automatique (absence, noreply…)';
        if (t === 'initial' || relanceNum(t) !== null) {
            const bits = ['envoyé via ' + (p.mailbox_email || p.mailbox_id || '?')];
            if (p.message_id) bits.push(`msg ${String(p.message_id).slice(0, 18)}…`);
            return bits.join(' · ');
        }
        if (t === 'validation_requete') {
            if (p.step) return `étape ${p.step} (${p.from_statut || '?'} → ${p.to_statut || '?'})`;
            return 'En attente d\'approbation Telegram';
        }
        if (t === 'desinscription') return p.en === false ? 'Réactivation du contact' : (p.raison || 'opposition au contact');
        if (t === 'status_change') return `${p.from_statut || '?'} → ${p.to_statut || '?'}${p.reason ? ' (' + p.reason + ')' : ''}`;
        if (t === 'creation' || t === 'import') return 'Prospect ajouté à une liste' + (p.source ? ` (${p.source})` : '');
        return '';
    }

    const SuiviModule = {
        events: [],
        stats: {},
        bounces: [],

        get campagneId() {
            return (window.CampagnesModule && typeof window.CampagnesModule.currentId !== 'undefined')
                ? window.CampagnesModule.currentId : null;
        },

        async loadStats() {
            const id = this.campagneId;
            // v2=1 : vue v2 GLOBALE quand aucune campagne n'est choisie (la
            // timeline de l'onglet est 100 % prospect_events — les chiffres
            // legacy renverraient bounces=0).
            const url = id ? `/api/stats?objectif_id=${id}` : '/api/stats?v2=1';
            try {
                const r = await fetch(url);
                const d = await r.json();
                this.stats = d && typeof d === 'object' ? d : {};
            } catch (e) {
                console.error('[suivi] stats', e);
                this.stats = {};
            }
        },

        async loadEvents() {
            const params = new URLSearchParams();
            if (this.campagneId) params.set('campagne_id', this.campagneId);
            try {
                const r = await fetch(`/api/v2/suivi/echanges?${params.toString()}`);
                const d = await r.json();
                this.events = (d && d.events) || [];
            } catch (e) {
                console.error('[suivi] events', e);
                this.events = [];
            }
        },

        async loadBounces() {
            const params = new URLSearchParams();
            if (this.campagneId) params.set('campagne_id', this.campagneId);
            try {
                const r = await fetch(`/api/v2/suivi/bounces?${params.toString()}`);
                const d = await r.json();
                this.bounces = (d && d.bounces) || [];
            } catch (e) {
                console.error('[suivi] bounces', e);
                this.bounces = [];
            }
        },

        async init() {
            if (!sel('tbody-suivi')) return;
            await Promise.all([this.loadStats(), this.loadEvents(), this.loadBounces()]);
            this.render();
            this._startAutoRefresh();
        },

        /** Rechargé quand la campagne active change (sélecteur topbar). */
        async onCampagneChange() {
            await this.init();
        },

        /** Rafraîchissement auto (30 s) — seulement si l'onglet est réellement affiché. */
        _startAutoRefresh() {
            if (this._timer) return;
            this._timer = setInterval(() => {
                const el = sel('tbody-suivi');
                // 0 rectangle = masqué (autre section ou sous-onglet « Calendrier »)
                if (!el || !el.getClientRects().length) return;
                this.refresh();
            }, 30000);
        },

        renderCards() {
            const s = this.stats || {};
            const evs = this.events || [];
            const envoye = s.envoyes || 0;
            const taux = typeof s.taux_reponse === 'number' ? `${s.taux_reponse} %` : '—';
            const reponses = s.emails_repondus || 0;
            const rdv = s.rdv_obtenus || 0;
            let relances = 0, ndr = 0, desinsc = 0;
            evs.forEach(ev => {
                if (relanceNum(ev.event_type) !== null) relances++;
                else if (ev.event_type === 'ndr') ndr++;
                else if (ev.event_type === 'desinscription' && !(ev.payload && ev.payload.en === false)) desinsc++;
            });
            const set = (id, v) => { const el = sel(id); if (el) el.textContent = v; };
            set('suivi-stat-envoyes', envoye);
            set('suivi-stat-taux', taux);
            set('suivi-stat-reponses', reponses);
            set('suivi-stat-rdv', rdv);
            set('suivi-stat-relances', relances);
            set('suivi-stat-ndr', ndr);
            set('suivi-stat-desinsc', desinsc);
            set('suivi-stat-bounces', s.bounces || 0);
        },

        /** Bloc « Bounces à traiter » — même décisions que les boutons Telegram. */
        renderBounces() {
            const block = sel('suivi-bounce-block');
            const list = sel('suivi-bounce-list');
            if (!block || !list) return;
            const rows = this.bounces || [];
            if (!rows.length) {
                block.style.display = 'none';
                list.innerHTML = '';
                return;
            }
            block.style.display = '';
            const cnt = sel('suivi-bounce-count');
            if (cnt) cnt.textContent = `— ${rows.length} en attente`;
            list.innerHTML = rows.map(b => {
                const [motif, color] = BOUNCE_MOTIF[b.raison] || [b.raison || 'Bounce', '#ef4444'];
                const nom = esc(b.nom_complet || b.email);
                const sub = [b.email, b.entreprise, b.campagne_nom].filter(Boolean).map(esc);
                const date = b.created_at ? fmtDateTime(b.created_at) : '—';
                const nolink = b.prospect_id
                    ? `onclick="if(window.openLeadPanel) window.openLeadPanel(${b.prospect_id}, 'suivi')" style="cursor:pointer"`
                    : '';
                return `<div data-bounce="${b.id}" style="display:flex;gap:12px;align-items:center;padding:10px 14px;border-bottom:1px solid var(--border)">
                    <div style="min-width:0;flex:1" ${nolink}>
                        <div style="font-size:13px;font-weight:600;color:var(--ink)">${nom}</div>
                        <div style="font-size:11px;color:var(--ink3);overflow:hidden;text-overflow:ellipsis">${sub.join(' · ')}</div>
                    </div>
                    <span style="display:inline-flex;align-items:center;gap:5px;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600;background:${color}18;color:${color};white-space:nowrap">
                        <span style="width:6px;height:6px;border-radius:50%;background:${color}"></span>${esc(motif)}
                    </span>
                    <span style="font-size:11px;color:var(--ink3);white-space:nowrap;min-width:104px;text-align:right">${date}</span>
                    <span style="display:flex;gap:6px;white-space:nowrap">
                        <button class="btn sm" data-act="archive" title="Corbeille : ne plus contacter + déplacement 🗑"
                            style="border:1px solid #ef444455;color:#ef4444">🗑 Corbeille</button>
                        <button class="btn sm" data-act="ignore" title="Ignorer : l'adresse reste dans la liste noire"
                            style="border:1px solid var(--border);color:var(--ink3)">Ignorer</button>
                    </span>
                </div>`;
            }).join('');
        },

        /** Clic sur 🗑 Corbeille / Ignorer d'une ligne du bloc. */
        async actOnBounce(id, act) {
            const url = `/api/v2/bounces/${encodeURIComponent(id)}/${act}`;
            try {
                const r = await fetch(url, { method: 'POST' });
                const d = await r.json();
                if (!d.success) {
                    window.toast ? window.toast(d.error || 'Action impossible', 'error')
                        : alert(d.error || 'Action impossible');
                    return;
                }
                if (window.toast) window.toast(act === 'archive'
                    ? 'Prospect envoyé en 🗑 Corbeille (ne plus contacter)'
                    : 'Bounce ignoré — adresse toujours bloquée', 'success');
                await Promise.all([this.loadBounces(), this.loadEvents()]);
                this.renderBounces();
                this.render();
            } catch (e) {
                console.error('[suivi] bounce action', e);
            }
        },

        render() {
            const tbody = sel('tbody-suivi');
            if (!tbody) return;
            this.renderCards();
            this.renderBounces();

            const ctx = sel('suivi-contexte');
            if (ctx) {
                const cid = this.campagneId;
                let nom = 'toutes les campagnes';
                if (cid && window.CampagnesModule) {
                    nom = window.CampagnesModule.campagnes.find(o => o.id === cid)?.nom || `id ${cid}`;
                }
                ctx.textContent = `Statistiques et historique filtrés par ${cid ? `la campagne « ${nom} »` : 'toutes les campagnes'}.`;
            }

            const filter = sel('suivi-filter-type')?.value || '';
            const allowed = FILTERS[filter] || null;
            const rows = allowed
                ? this.events.filter(ev => allowed.indexOf(ev.event_type) !== -1)
                : this.events;

            const count = sel('suivi-count');
            if (count) count.textContent = `— ${rows.length} événement${rows.length > 1 ? 's' : ''}`;

            if (!rows.length) {
                tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:28px;color:var(--ink3);font-size:13px">
                    Aucun échange. Créez une campagne, importez une liste puis lancez un envoi : chaque touche (initial, relance, réponse, NDR…) est journalisée ici.</td></tr>`;
                return;
            }

            tbody.innerHTML = rows.map(ev => {
                const { label, color } = labelFor(ev);
                const nom = [ev.prospect_nom, ev.prenom].filter(Boolean).join(' ') || 'Prospect #' + ev.prospect_id;
                const detail = detailFor(ev);
                const clickAttr = ev.prospect_id ? `onclick="if(window.openLeadPanel) window.openLeadPanel(${ev.prospect_id}, 'suivi')" style="cursor:pointer;vertical-align:middle"` : 'style="vertical-align:middle"';
                return `<tr ${clickAttr} title="Cliquer pour voir l'historique et répondre">
                    <td style="padding:10px 12px;font-size:12px;color:var(--ink3);white-space:nowrap">${fmtDateTime(ev.created_at)}</td>
                    <td style="padding:10px 12px">
                        <div style="font-weight:600;color:var(--ink);font-size:13px">${esc(nom)}</div>
                        <div style="font-size:11px;color:var(--ink3)">${esc(ev.prospect_email || '')}</div>
                    </td>
                    <td style="padding:10px 12px;white-space:nowrap">
                        <span style="display:inline-flex;align-items:center;gap:5px;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600;background:${color}18;color:${color}">
                            <span style="width:6px;height:6px;border-radius:50%;background:${color}"></span>${label}
                        </span>
                    </td>
                    <td style="padding:10px 12px;font-size:12px;color:var(--ink2)">${esc(detail)}</td>
                    <td style="padding:10px 12px;font-size:12px;color:var(--ink3)">${esc(ev.campagne_nom || '—')}</td>
                </tr>`;
            }).join('');
        },

        /** Toutes les lignes du bloc, d'un coup (retour en masse). */
        async actOnAllBounces(act) {
            const rows = this.bounces || [];
            if (!rows.length) return;
            const label = act === 'archive' ? 'archiver en 🗑 Corbeille' : 'ignorer';
            if (!window.confirm(`Confirmer : ${label} pour ${rows.length} bounce(s) ?`)) return;
            let ok = 0, ko = 0;
            for (const b of rows) {
                try {
                    const r = await fetch(`/api/v2/bounces/${encodeURIComponent(b.id)}/${act}`,
                        { method: 'POST' });
                    const d = await r.json();
                    if (d.success) ok++; else ko++;
                } catch (e) { ko++; }
            }
            if (window.toast) window.toast(`${ok} bounce(s) ${label}${ko ? `, ${ko} en échec` : ''}`,
                ko ? 'warning' : 'success');
            await Promise.all([this.loadBounces(), this.loadEvents(), this.loadStats()]);
            this.render();
        },

        async refresh() {
            if (!sel('tbody-suivi')) return;
            await Promise.all([this.loadStats(), this.loadEvents(), this.loadBounces()]);
            this.render();
        },
    };

    window.SuiviModule = SuiviModule;

    // Délégation des boutons du bloc « Bounces à traiter » (le HTML est régénéré
    // à chaque render, donc on écoute sur le conteneur).
    document.addEventListener('click', function (ev) {
        if (!window.SuiviModule) return;
        const t = ev.target;
        if (!t || !t.closest) return;
        const bulk = t.closest('[data-act-bulk]');
        if (bulk) {
            ev.preventDefault();
            window.SuiviModule.actOnAllBounces(bulk.getAttribute('data-act-bulk'));
            return;
        }
        const btn = t.closest('#suivi-bounce-list [data-act]');
        if (!btn) return;
        const row = btn.closest('[data-bounce]');
        if (!row) return;
        ev.preventDefault();
        window.SuiviModule.actOnBounce(row.getAttribute('data-bounce'), btn.getAttribute('data-act'));
    });
})();