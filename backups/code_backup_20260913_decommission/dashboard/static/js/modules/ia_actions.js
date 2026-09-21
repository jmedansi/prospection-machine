/**
 * dashboard/js/modules/ia_actions.js — Actions IA ⇄ Dashboard
 *
 * Boutons « Actions IA » (Qualifier / Maquette / Rédiger / Actualiser) dans les onglets
 * existants (Lead Station, Listes, Sources). Ciblent une liste (liste_id) ou une sélection
 * de leads (lead_ids). Backend : dashboard/routes/ia_echanges.py + services/ia_runner.py.
 *
 * SÉCURITÉ : aucune action n'envoie de mail. Le scan écrit approuve=0 ; l'envoi est déclenché
 * manuellement par l'utilisateur.
 */
window.IaActions = (function () {
    'use strict';

    function _payload(opts) {
        const p = { objectif: opts.objectif || 'tous', moteur: opts.moteur || 'file' };
        if (opts.liste_id) p.liste_id = opts.liste_id;
        else if (opts.liste_nom) p.liste_nom = opts.liste_nom;
        if (opts.lead_ids && opts.lead_ids.length) p.lead_ids = opts.lead_ids;
        return p;
    }

    function _cible(scope) {
        // scope: {liste_id} ou {liste_nom} ou {lead_ids}
        if (scope && scope.lead_ids && scope.lead_ids.length) return scope;
        return scope || {};
    }

    function _post(action, opts, msg) {
        const btnMsg = document.getElementById('ia-toast') || { };
        const label = msg || action;
        return fetch('/api/ia/' + action, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(_payload(_cible(opts)))
        })
            .then(r => r.json())
            .then(d => {
                const m = d.message || (d.ok ? `${action} OK (${d.leads ?? d.exportes ?? ''} lead(s))` : (d.error || 'Erreur'));
                window.showToast ? showToast(m, d.ok ? 'success' : 'error') : console.log(m);
                return d;
            })
            .catch(e => {
                window.showToast ? showToast('Erreur IA: ' + e, 'error') : console.error(e);
            });
    }

    function _selectedLeadIds() {
        // Récupère la sélection Lead Station (cases .ul-cb/.lead-cb cochées) — voir unified_leads.js
        if (typeof window.ulGetSelectedIds === 'function') {
            return window.ulGetSelectedIds();
        }
        return Array.from(document.querySelectorAll('.lead-cb:checked, .ul-cb:checked'))
            .map(c => parseInt(c.dataset.id)).filter(Boolean);
    }

    return {
        /** Qualifier : prépare les leads (liste ou sélection) pour la qualification IA. */
        qualify(scope) { return _post('qualify', scope, 'Qualification IA'); },

        /** Maquette : prépare les dossiers PROMPT/<IdLead>/ pour les leads 'web'. */
        maquette(scope) { return _post('maquette', scope, 'Génération maquettes'); },

        /** Rédiger : prépare la rédaction d'emails IA (colonnes EmailObjet/EmailCorps). */
        redact(scope) { return _post('redact', scope, 'Rédaction emails'); },

        /** Export des leads (selon scope) vers ia_echanges/<liste>/leads.csv. */
        export(scope) { return _post('export', scope, 'Export IA'); },

        /** Actualiser : relit le CSV complété et réintègre (qualification + emails, jamais d'envoi). */
        scan(scope) {
            return fetch('/api/ia/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(_payload(_cible(scope)))
            })
                .then(r => r.json())
                .then(d => {
                    let m = d.message || (d.ok ? `Scan OK (${d.qualifies ?? 0} qualifié(s), ${d.emails ?? 0} email(s))` : (d.error || 'Erreur'));
                    if (d.ok && Array.isArray(d.maquettes) && d.maquettes.length) {
                        const done = d.maquettes.filter(q => q.a_index && q.a_capture).length;
                        const partial = d.maquettes.filter(q => q.a_index !== q.a_capture).length;
                        m += ` · Maquettes: ${done} complète(s)${partial ? `, ${partial} partielle(s)` : ''}`;
                    }
                    window.showToast ? showToast(m, d.ok ? 'success' : 'error') : console.log(m);
                    return d;
                })
                .catch(e => {
                    window.showToast ? showToast('Erreur scan: ' + e, 'error') : console.error(e);
                });
        },

        /** Actions sur la sélection Lead Station courante. */
        qualifySelected() { return this.qualify({ lead_ids: _selectedLeadIds() }); },
        maquetteSelected() { return this.maquette({ lead_ids: _selectedLeadIds() }); },
        redactSelected() { return this.redact({ lead_ids: _selectedLeadIds() }); },
        scanSelected() { return this.scan({ lead_ids: _selectedLeadIds() }); },

        /** Actions sur une liste (depuis l'onglet Listes / Sources). */
        qualifyList(listeId, listeNom) { return this.qualify({ liste_id: listeId, liste_nom: listeNom }); },
        maquetteList(listeId, listeNom) { return this.maquette({ liste_id: listeId, liste_nom: listeNom }); },
        redactList(listeId, listeNom) { return this.redact({ liste_id: listeId, liste_nom: listeNom }); },

        /**
         * Actions sur UN lead (panneau latéral). Scope = { lead_ids:[id] }.
         * Backend resolve_target_leads accepte lead_ids (AdHoc) → dossier ia_echanges/<liste>/ad hoc.
         */
        qualifyLead(leadId) { return this.qualify({ lead_ids: [leadId] }); },
        maquetteLead(leadId) {
            // L'export prépare aussi le CSV + dossiers PROMPT pour ce lead. Maquette seule suffit
            // (maquette() crée les PROMPT + écrit le CSV ciblé objectif web).
            return this.maquette({ lead_ids: [leadId] });
        },
        redactLead(leadId) { return this.redact({ lead_ids: [leadId] }); },

        /** Localise la maquette d'un lead (toutes listes confondues). Lecture seule. */
        leadMaquette(leadId) {
            return fetch('/api/ia/lead/' + leadId + '/maquette', { cache: 'no-store' })
                .then(r => (r.ok ? r.json() : null))
                .catch(() => null);
        },
    };
})();