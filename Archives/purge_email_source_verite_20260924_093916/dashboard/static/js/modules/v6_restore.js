/**
 * dashboard/static/js/modules/v6_restore.js
 *
 * Réintroduction des actions du panneau latéral V5 (portées dans unified_leads.js)
 * qui avaient perdu leurs gestionnaires lors du passage au shell V6.
 *
 * Principe : chaque fonction n'est redéfinie que si elle n'existe pas déjà
 * (fi: feuille V5 archive), et tout est branché sur le modèle v2 (prospects)
 * via /api/v2/leads/<id> — les champs libres (notes, moyens de contact,
 * objet/corps email) sont stockés dans data_extra (fusion, jamais d'écrasement).
 * Aucune dépendance à dashboard_core.js. Ne jamais intervenir dans le flux
 * d'envoi legacy (AGENTS.md) : la génération d'email v2 passe par IaActions.
 */
(function () {
    'use strict';

    /* ─── Helpers ─────────────────────────────────────────────────────────── */

    const _t = (m, t) => { if (typeof showToast === 'function') showToast(m, t); };

    const _compose = (l) => Object.assign({}, l || {}, (l && l.data_extra && typeof l.data_extra === 'object') ? l.data_extra : {});

    const _panelReload = (id) => {
        if (typeof openLeadPanel === 'function' && window._selectedLeadId && Number(window._selectedLeadId) === Number(id)) {
            const tab = (document.querySelector('.side-panel-tab.active') || {}).dataset?.tab || 'audit';
            openLeadPanel(id, tab);
        }
    };

    const _cachedLead = (id) => {
        const pools = [];
        if (window._ul && Array.isArray(window._ul.leads)) pools.push(window._ul.leads);
        if (window.ListesModule && window.ListesModule._state && Array.isArray(window.ListesModule._state.leads)) pools.push(window.ListesModule._state.leads);
        for (const p of pools) {
            const l = p.find(x => Number(x.id) === Number(id));
            if (l) return l;
        }
        return null;
    };

    const _getLead = async (id) => {
        try {
            const r = await fetch('/api/v2/leads/' + id, { cache: 'no-store' });
            if (!r.ok) return null;
            const d = await r.json();
            return (d && d.success) ? d.lead : null;
        } catch (e) {
            return null;
        }
    };

    /** Fusionne `patch` dans data_extra du prospect puis PUT v2. */
    const _saveExtra = async (id, patch) => {
        try {
            const lead = await _getLead(id);
            const base = (lead && lead.data_extra && typeof lead.data_extra === 'object') ? lead.data_extra : {};
            const merged = Object.assign({}, base, patch);
            const r = await fetch('/api/v2/leads/' + id, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ data_extra: merged }),
            });
            const d = await r.json().catch(() => ({}));
            return !!(d && d.success);
        } catch (e) {
            console.error('[v6_restore] _saveExtra', e);
            return false;
        }
    };

    const _silentRefresh = () => {
        if (typeof unifiedLeadsLoad === 'function') unifiedLeadsLoad((window._ul && window._ul.page) || 1);
        if (window.ListesModule && typeof window.ListesModule.onProspectsChanged === 'function') window.ListesModule.onProspectsChanged();
    };

    /* ─── Panneau latéral : canal de contact ─────────────────────────────── */

    if (typeof window.toggleContactPill !== 'function') {
        window.toggleContactPill = async function toggleContactPill(leadId, method, el) {
            const key = 'contact_' + method;
            const current = (el && el.textContent.trim().startsWith('✓')) ? 1 : 0;
            const newVal = current ? 0 : 1;
            let ok = await _saveExtra(leadId, { [key]: newVal });
            if (!ok) {
                // Repli legacy (leads_audites) si le prospect est aussi auditlé
                try {
                    const r = await fetch('/api/leads/' + leadId + '/contact', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ [key]: newVal }),
                    });
                    const d = await r.json();
                    if (!d.success) throw new Error(d.error || 'echec');
                    ok = true;
                } catch (e) {
                    _t('Erreur: ' + e.message, 'error');
                    return;
                }
            }
            if (el) {
                el.style.background = newVal ? '#10b981' : '#f1f5f9';
                el.style.color = newVal ? '#fff' : '#475569';
                el.textContent = (newVal ? '✓' : '○') + ' ' + el.textContent.slice(el.textContent.indexOf(' ') + 1);
            }
            _t(newVal ? 'Canal activé' : 'Canal désactivé', 'success');
            _panelReload(leadId);
        };
    }

    /* ─── Panneau latéral : notes (autosave) ─────────────────────────────── */

    if (typeof window.saveCoreNotes !== 'function') {
        window.saveCoreNotes = async function saveCoreNotes(id, notes) {
            try {
                // v2 : la note est une vraie colonne (prospects.note)
                let ok = false;
                try {
                    const r = await fetch('/api/v2/leads/' + id, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ note: notes || '' }),
                    });
                    const d = await r.json();
                    ok = !!(d && d.success);
                } catch (e) { ok = false; }
                if (!ok) {
                    const r = await fetch('/api/leads/' + id + '/edit', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ notes: notes || '' }),
                    });
                    const d = await r.json();
                    ok = !!(d && d.success);
                }
                if (ok) _t('Notes sauvegardées', 'success');
            } catch (e) {
                console.error('[v6_restore] saveCoreNotes', e);
            }
        };
    }

    /* ─── Panneau latéral : bouton Modifier ──────────────────────────────── */

    if (typeof window.openEditLeadFromPanel !== 'function') {
        window.openEditLeadFromPanel = async function openEditLeadFromPanel(leadId) {
            if (typeof unifiedLeadsOpenEdit === 'function') {
                const opened = await unifiedLeadsOpenEdit(leadId);
                if (opened !== false && typeof closeSidePanel === 'function') closeSidePanel();
                return;
            }
            _t('Modification indisponible', 'error');
        };
    }

    /* ─── Panneau latéral : génération / aperçu / édition d'email ────────── */

    if (typeof window.generateEmailForLead !== 'function') {
        window.generateEmailForLead = async function generateEmailForLead(leadId) {
            // v2 : la rédaction d'email passe par l'assistant IA (never l'envoi)
            if (window.IaActions && typeof window.IaActions.redactLead === 'function') {
                _t('Génération de l\u2019email (IA)...', 'info');
                const d = await window.IaActions.redactLead(leadId);
                if (d && d.ok === false) { _t(d.error || 'Erreur IA', 'error'); return; }
                _t('Rédaction IA lancée — le panneau sera rechargé', 'info');
                setTimeout(() => _panelReload(leadId), 2500);
                return;
            }
            // Repli legacy (pipe ancien)
            try {
                const r = await fetch('/api/email/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ lead_ids: [leadId] }),
                });
                const d = await r.json();
                if (d.error) { _t('Erreur: ' + d.error, 'error'); return; }
                _t('Email généré', 'success');
                _panelReload(leadId);
            } catch (e) { _t('Erreur: ' + e, 'error'); }
        };
    }

    if (typeof window.previewEmail !== 'function') {
        window.previewEmail = async function previewEmail(leadId) {
            // v2 : l'aperçu = email rendu tel que le prospect le verra
            if (typeof _ulIsV2 === 'function' && _ulIsV2()) {
                try {
                    const r = await fetch('/api/v2/leads/' + leadId + '/email', { cache: 'no-store' });
                    const d = await r.json();
                    if (d && d.success && d.email && d.email.corps) {
                        const win = window.open('', '_blank');
                        if (win) { win.document.write(d.email.corps); win.document.close(); }
                        return;
                    }
                } catch (e) { /* repli legacy */ }
            }
            let lead = _compose(_cachedLead(leadId));
            if (!lead || !lead.email_corps) {
                const fresh = await _getLead(leadId);
                if (fresh) lead = _compose(fresh);
            }
            if (!lead || !lead.email_corps) { _t('Aucun email généré', 'warning'); return; }
            const win = window.open('', '_blank');
            if (win) { win.document.write(lead.email_corps); win.document.close(); }
        };
    }

    if (typeof window.openEmailEditor !== 'function') {
        window.openEmailEditor = async function openEmailEditor(leadId) {
            let lead = _compose(_cachedLead(leadId));
            if (!lead || lead.error) {
                const fresh = await _getLead(leadId);
                if (fresh) lead = _compose(fresh);
            }
            if (!lead || lead.error) { _t('Lead non trouvé', 'error'); return; }

            // v2 : pré-remplir avec le rendu réel (template campagne) si vide
            let subjectVal0 = lead.email_objet || '';
            let bodyVal0 = lead.email_corps || '';
            if (typeof _ulIsV2 === 'function' && _ulIsV2() && !subjectVal0) {
                try {
                    const r = await fetch('/api/v2/leads/' + leadId + '/email', { cache: 'no-store' });
                    const d = await r.json();
                    if (d && d.success && d.email) {
                        if (!subjectVal0 && d.email.objet) subjectVal0 = d.email.objet;
                        if (!bodyVal0 && d.email.corps_texte) bodyVal0 = d.email.corps_texte;
                    }
                } catch (e) { /* éditeur vide si l'appel échoue */ }
            }

            const existing = document.getElementById('email-editor-modal');
            if (existing) existing.remove();

            const esc = s => (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
            const subjectVal = subjectVal0;
            const bodyVal = bodyVal0;

            const modal = document.createElement('div');
            modal.id = 'email-editor-modal';
            modal.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.75);display:flex;align-items:center;justify-content:center;padding:16px';
            modal.innerHTML = `
                <div style="background:var(--surface);border-radius:16px;width:100%;max-width:1140px;height:90vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 32px 80px rgba(0,0,0,.6)">
                    <div style="padding:18px 24px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:14px;flex-shrink:0">
                        <div style="width:36px;height:36px;background:var(--accent);border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        </div>
                        <div style="flex:1;min-width:0">
                            <div style="font-size:11px;color:var(--ink3);margin-bottom:5px;font-weight:600;text-transform:uppercase;letter-spacing:.5px">&#201;dition de l'email &mdash; ${esc(lead.nom || '')}</div>
                            <input id="eme-subject" type="text" value="${esc(subjectVal)}"
                                style="width:100%;font-size:15px;font-weight:600;background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:7px 12px;color:var(--ink);outline:none;transition:border-color .2s"
                                placeholder="Objet de l'email..."
                                onfocus="this.style.borderColor='var(--accent)'" onblur="this.style.borderColor='var(--border)'">
                        </div>
                        <button id="eme-close" title="Fermer" style="width:34px;height:34px;border-radius:50%;background:var(--surface2);border:1px solid var(--border);cursor:pointer;font-size:16px;color:var(--ink3);display:flex;align-items:center;justify-content:center">&#x2715;</button>
                    </div>
                    <div style="flex:1;display:grid;grid-template-columns:1fr 1fr;overflow:hidden;min-height:0">
                        <div style="display:flex;flex-direction:column;border-right:1px solid var(--border)">
                            <div style="padding:7px 16px;font-size:10px;font-weight:700;color:var(--ink3);text-transform:uppercase;letter-spacing:.6px;background:var(--surface2);border-bottom:1px solid var(--border);flex-shrink:0">&#9998; HTML</div>
                            <textarea id="eme-body" spellcheck="false" style="flex:1;resize:none;background:var(--bg);color:var(--ink);font-family:'JetBrains Mono',monospace;font-size:11.5px;line-height:1.6;padding:14px 16px;border:none;outline:none;overflow-y:auto">${esc(bodyVal)}</textarea>
                        </div>
                        <div style="display:flex;flex-direction:column;overflow:hidden">
                            <div style="padding:7px 16px;font-size:10px;font-weight:700;color:var(--ink3);text-transform:uppercase;letter-spacing:.6px;background:var(--surface2);border-bottom:1px solid var(--border);flex-shrink:0">&#128065; Pr&#233;visualisation</div>
                            <iframe id="eme-preview" style="flex:1;border:none;background:#fff"></iframe>
                        </div>
                    </div>
                    <div style="padding:14px 24px;border-top:1px solid var(--border);display:flex;align-items:center;gap:10px;justify-content:space-between;flex-shrink:0;background:var(--surface)">
                        <div style="font-size:12px;color:var(--ink3)">Stock&#233; sur la fiche du prospect (data_extra) — l'envoi r&#233;el suit les r&#232;gles de la campagne.</div>
                        <div style="display:flex;gap:10px">
                            <button id="eme-cancel" class="btn bg1" style="padding:9px 18px">Annuler</button>
                            <button id="eme-save" class="btn bp1" style="padding:9px 18px;min-width:140px">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;vertical-align:-2px"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
                                Enregistrer
                            </button>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);

            const iframe = document.getElementById('eme-preview');
            const textarea = document.getElementById('eme-body');

            function _updatePreview() {
                const blob = new Blob([textarea.value], { type: 'text/html' });
                const url = URL.createObjectURL(blob);
                iframe.src = url;
                iframe.onload = () => URL.revokeObjectURL(url);
            }
            _updatePreview();

            let _previewTimer;
            textarea.addEventListener('input', () => {
                clearTimeout(_previewTimer);
                _previewTimer = setTimeout(_updatePreview, 450);
            });

            const _close = () => modal.remove();
            document.getElementById('eme-close').onclick = _close;
            document.getElementById('eme-cancel').onclick = _close;
            modal.addEventListener('click', e => { if (e.target === modal) _close(); });

            document.getElementById('eme-save').onclick = async () => {
                const saveBtn = document.getElementById('eme-save');
                saveBtn.disabled = true;
                saveBtn.textContent = 'Enregistrement...';
                const newSubject = document.getElementById('eme-subject').value.trim();
                const newBody = textarea.value;
                try {
                    // 1) v2 : stockage dans data_extra (fusion backend)
                    let ok = await _saveExtra(leadId, { email_objet: newSubject, email_corps: newBody });
                    // 2) repli legacy
                    if (!ok) {
                        const resp = await fetch('/api/email/update', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ lead_id: leadId, objet: newSubject, corps: newBody }),
                        });
                        const data = await resp.json();
                        ok = !!(data && data.success);
                    }
                    if (ok) {
                        _t('Email mis à jour', 'success');
                        _close();
                        _panelReload(leadId);
                    } else {
                        _t('Erreur : enregistrement impossible', 'error');
                        saveBtn.disabled = false;
                        saveBtn.textContent = 'Enregistrer';
                    }
                } catch (err) {
                    _t('Erreur réseau : ' + err.message, 'error');
                    saveBtn.disabled = false;
                    saveBtn.textContent = 'Enregistrer';
                }
            };
        };
    }

    if (typeof window.sendTestEmail !== 'function') {
        window.sendTestEmail = async function sendTestEmail(leadId) {
            const v2 = (typeof _ulIsV2 === 'function') && _ulIsV2();
            try {
                const r = await fetch(v2 ? ('/api/v2/leads/' + leadId + '/email/test') : '/api/email/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(v2 ? {} : { lead_id: leadId }),
                });
                const d = await r.json();
                if (d.error) { _t('Erreur: ' + d.error, 'error'); return; }
                _t('Email test envoyé', 'success');
            } catch (e) { _t('Erreur: ' + e.message, 'error'); }
        };
    }

    /* ─── Panneau latéral : envoi réel v2 ─────────────────────────────────── */

    if (typeof window.panelSendEmail !== 'function') {
        window.panelSendEmail = async function panelSendEmail(leadId) {
            const v2 = (typeof _ulIsV2 === 'function') && _ulIsV2();
            try {
                if (v2) {
                    const r = await fetch('/api/v2/leads/' + leadId + '/email/send', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: '{}',
                    });
                    let d = {};
                    try { d = await r.json(); } catch (e) { d = { error: 'Réponse invalide' }; }
                    if (d.error) { _t('Erreur: ' + d.error, 'error'); return; }
                    _t(d.message || d.statut || 'Envoi lancé', d.success ? 'success' : 'info');
                    if (window._panelReload) _panelReload(leadId);
                    return;
                }
                // Repli legacy (leads_audites approuvés)
                const r = await fetch('/api/email/send-approved', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ lead_ids: [leadId] }),
                });
                const d = await r.json();
                if (d.error) { _t('Erreur: ' + d.error, 'error'); return; }
                _t((d.total || 1) + ' email(s) envoyé(s)', 'success');
                if (window._panelReload) _panelReload(leadId);
            } catch (e) { _t('Erreur: ' + e.message, 'error'); }
        };
    }

    /* ─── Panneau latéral : maquette IA ───────────────────────────────────── */

    if (typeof window.dialogOpenMaquette !== 'function') {
        window.dialogOpenMaquette = function dialogOpenMaquette(leadId) {
            if (!window.IaActions || typeof window.IaActions.leadMaquette !== 'function') {
                _t('Assistant IA indisponible', 'error');
                return;
            }
            window.IaActions.leadMaquette(leadId).then(d => {
                if (!d || !d.liste || !d.files || !d.files.length) {
                    _t('Aucune maquette générée pour ce lead.', 'error');
                    return;
                }
                const existing = document.getElementById('maquette-view-modal');
                if (existing) existing.remove();

                const modal = document.createElement('div');
                modal.id = 'maquette-view-modal';
                modal.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.85);display:flex;flex-direction:column;align-items:stretch;padding:0';
                const esc = s => (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
                const lbl = esc(d.liste) + ' / PROMPT/' + esc(d.lead_id) + '/index.html';
                modal.innerHTML = `
                    <div style="display:flex;align-items:center;gap:12px;padding:12px 20px;background:#0f172a;color:#fff;flex-shrink:0">
                        <span style="font-weight:700;font-size:14px">🎨 Maquette — ${lbl}</span>
                        <span style="flex:1"></span>
                        ${d.files.includes('capture.png') ? `<button onclick="document.getElementById('maq-frame').src='/api/ia/maquettes/${esc(d.liste)}/${esc(d.lead_id)}/capture.png'" style="margin-right:8px;padding:7px 12px;border-radius:8px;border:none;background:#334155;color:#fff;cursor:pointer;font-size:12px">Capture (PNG)</button>` : ''}
                        <button onclick="document.getElementById('maq-frame').src='/api/ia/maquettes/${esc(d.liste)}/${esc(d.lead_id)}/index.html'" style="margin-right:8px;padding:7px 12px;border-radius:8px;border:none;background:#334155;color:#fff;cursor:pointer;font-size:12px">Page (HTML)</button>
                        <button onclick="this.closest('#maquette-view-modal').remove()" style="width:34px;height:34px;border-radius:50%;border:none;background:#475569;color:#fff;cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center">✕</button>
                    </div>
                    <iframe id="maq-frame" style="flex:1;border:none;background:#fff" src="/api/ia/maquettes/${esc(d.liste)}/${esc(d.lead_id)}/index.html"></iframe>
                `;
                document.body.appendChild(modal);
            }).catch(e => _t('Erreur maquette: ' + e, 'error'));
        };
    }

    /* ─── Audit (par lead) : lancer / relancer / suivi / rapports ─────────── */

    if (typeof window.auditLead !== 'function') {
        window.auditLead = async function auditLead(leadId) {
            const cached = _cachedLead(leadId);
            const nom = (cached && cached.nom) || ('Lead #' + leadId);
            _t('Audit en cours pour ' + nom + '...', 'info');
            const gp = document.getElementById('sidebar-audit');
            if (gp) gp.style.display = 'block';
            try {
                const r = await fetch('/api/audit/launch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ lead_ids: [leadId] }),
                });
                const d = await r.json();
                if (d.error) {
                    _t('Erreur: ' + d.error, 'error');
                    if (gp) gp.style.display = 'none';
                    _panelReload(leadId);
                    return;
                }
                _t('Audit démarré', 'info');
                if (typeof pollAuditCompletion === 'function') pollAuditCompletion(leadId, 0);
            } catch (e) {
                _t('Erreur réseau: ' + e.message, 'error');
                if (gp) gp.style.display = 'none';
            }
        };
    }

    if (typeof window.regenerateAudit !== 'function') {
        window.regenerateAudit = async function regenerateAudit(leadId) {
            const cached = _cachedLead(leadId);
            const leadName = (cached && cached.nom) || ('Lead #' + leadId);
            _t('Lancement de l\u2019audit pour ' + leadName + '...', 'info');

            const content = document.getElementById('panel-content');
            if (content) {
                content.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--ink3)"><div style="font-size:24px;margin-bottom:8px">⏳</div>Audit en cours pour <strong>' + (typeof escHtml === 'function' ? escHtml(leadName) : leadName) + '</strong>...</div>';
            }
            const gp = document.getElementById('sidebar-audit');
            if (gp) gp.style.display = 'block';

            try {
                const r = await fetch('/api/audit/launch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ lead_ids: [leadId] }),
                });
                const data = await r.json();
                if (data.error) {
                    _t('Erreur: ' + data.error, 'error');
                    if (gp) gp.style.display = 'none';
                    _panelReload(leadId);
                    return;
                }
                _t('Audit démarré...', 'info');
                if (typeof pollAuditCompletion === 'function') pollAuditCompletion(leadId, 0);
            } catch (e) {
                _t('Erreur réseau: ' + e.message, 'error');
                if (gp) gp.style.display = 'none';
                _panelReload(leadId);
            }
        };
    }

    if (typeof window.pollAuditCompletion !== 'function') {
        window.pollAuditCompletion = function pollAuditCompletion(leadId, attempts) {
            const maxAttempts = 150;
            const gp = document.getElementById('sidebar-audit');
            const textEl = document.getElementById('sidebar-audit-text');
            const pctEl = document.getElementById('sidebar-audit-pct');
            const barEl = document.getElementById('sidebar-audit-bar');

            fetch('/api/audit/status')
                .then(r => r.json())
                .then(status => {
                    if (status.running) {
                        const total = status.total || 1;
                        const current = status.current || 0;
                        const pct = total > 0 ? Math.round((current / total) * 100) : Math.min(attempts * 2, 90);
                        if (textEl) textEl.innerHTML = `<strong>${current}</strong>/${total} audité(s) — en cours...`;
                        if (pctEl) pctEl.textContent = pct + '%';
                        if (barEl) barEl.style.width = pct + '%';
                        attempts++;
                        if (attempts >= maxAttempts) {
                            if (gp) gp.style.display = 'none';
                            _t('Audit continue en arrière-plan (>5min)', 'warning');
                            _panelReload(leadId);
                            return;
                        }
                        setTimeout(() => pollAuditCompletion(leadId, attempts), 2000);
                        return;
                    }
                    if (gp) gp.style.display = 'none';
                    if ((status.failed || 0) > 0) {
                        _t(`Audit : ${status.current - status.failed} OK, ${status.failed} échec(s)`, 'warning');
                    } else if (status.current > 0) {
                        _t('Audit terminé avec succès !', 'success');
                    }
                    _panelReload(leadId);
                })
                .catch(() => {
                    attempts++;
                    if (attempts >= maxAttempts) {
                        if (gp) gp.style.display = 'none';
                        _t('Timeout — audit en arrière-plan', 'warning');
                        _panelReload(leadId);
                        return;
                    }
                    setTimeout(() => pollAuditCompletion(leadId, attempts), 2000);
                });
        };
    }

    if (typeof window.previewReport !== 'function') {
        window.previewReport = function previewReport(slug) {
            slug = slug || '';
            fetch('/api/previews')
                .then(r => r.json())
                .then(pd => {
                    const preview = (pd.previews || []).find(p => p.slug === slug || p.slug.includes(slug));
                    if (preview && preview.local) {
                        window.open('/previews/' + slug + '/', '_blank');
                    } else if (slug) {
                        window.open('https://audit.incidenx.com/' + slug + '/', '_blank');
                    } else {
                        _t('Aucun rapport généré pour ce lead. Cliquer sur "Relancer l\u2019audit" pour en générer un.', 'error');
                    }
                })
                .catch(e => _t('Erreur: ' + e.message, 'error'));
        };
    }

    if (typeof window.pushReport !== 'function') {
        window.pushReport = async function pushReport(slug) {
            slug = slug || '';
            if (!slug) { _t('Aucun slug de rapport', 'error'); return; }
            try {
                const pd = await fetch('/api/previews').then(r => r.json());
                const preview = (pd.previews || []).find(p => p.slug === slug);
                if (!preview || !preview.local) {
                    _t('Aucun mockup local trouvé. Lancer l\u2019audit d\u2019abord.', 'warning');
                    return;
                }
                _t('Publication en cours...', 'info');
                const pushRes = await fetch('/api/previews/push', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ slugs: [slug] }),
                }).then(r => r.json());
                if (pushRes.published && pushRes.published.length > 0) {
                    _t('Mockup publié : ' + pushRes.published[0].url, 'success');
                } else if (pushRes.results && pushRes.results[0] && pushRes.results[0].status === 'published') {
                    _t('Mockup publié : ' + pushRes.results[0].url, 'success');
                } else {
                    _t('Erreur: ' + (pushRes.error || pushRes.failed?.[0]?.error || 'Publication échouée'), 'error');
                }
                _panelReload(Number(window._selectedLeadId));
            } catch (e) { _t('Erreur: ' + e.message, 'error'); }
        };
    }

    // Aliens legacy (V5 : même comportement)
    if (typeof window.launchAuditForLead !== 'function') {
        window.launchAuditForLead = (leadId) => { if (typeof auditLead === 'function') auditLead(leadId); };
    }
    if (typeof window.regenerateReport !== 'function') {
        window.regenerateReport = (leadId) => { if (typeof auditLead === 'function') auditLead(leadId); };
    }
    if (typeof window.startAuditPolling !== 'function') {
        window.startAuditPolling = function startAuditPolling() {
            console.log('[Audit] Démarrage du tracking d\u2019état d\u2019audit...');
            const gp = document.getElementById('sidebar-audit');
            if (gp) {
                gp.style.display = 'block';
                const textEl = document.getElementById('sidebar-audit-text');
                if (textEl) textEl.textContent = 'Démarrage de l\u2019audit...';
            }
        };
    }

    /* ─── Sources : boutons Stop (scraper_watchdog legacy) ───────────────── */

    if (typeof window.sniperStop !== 'function') {
        window.sniperStop = async function sniperStop(sourceKey) {
            if (!confirm(`Voulez-vous arrêter cette tâche (${sourceKey}) ?`)) return;
            try {
                const r = await fetch('/api/scraper/stop', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key: sourceKey }),
                });
                const contentType = r.headers.get('content-type') || '';
                if (contentType.indexOf('application/json') !== -1) {
                    const d = await r.json();
                    _t(`⏹ ${sourceKey} : ${d.message || d.error || 'Arrêt demandé'}`, 'info');
                } else {
                    _t(`⏹ ${sourceKey} — Erreur serveur ${r.status}`, 'error');
                }
            } catch (e) { console.error('[v6_restore] sniperStop', e); }
        };
    }

    /* ─── Rafraîchissement global (triggerGlobalLeadRefresh) ─────────────── */

    if (typeof window.triggerGlobalLeadRefresh !== 'function') {
        window.triggerGlobalLeadRefresh = function triggerGlobalLeadRefresh(id) {
            _silentRefresh();
            if (id) _panelReload(id);
        };
    }

    /* ─── Alias ListsModule (legacy) → ListesModule (v2) + shim + Liste ▾ ── */

    if (!window.ListesModule) window.ListesModule = window.ListesModule || {};
    if (!window.ListsModule) window.ListsModule = window.ListesModule;

    if (typeof window.ListesModule.toggleAddDropdown !== 'function') {
        window.ListesModule.toggleAddDropdown = function toggleAddDropdown() {
            const m = document.getElementById('lists-add-dropdown-menu');
            if (!m) return;
            const show = m.style.display !== 'block';
            m.style.display = show ? 'block' : 'none';
            if (show) _populateAddDropdown();
        };
    }
    if (typeof window.ListesModule.openCreateAndAdd !== 'function') {
        window.ListesModule.openCreateAndAdd = function openCreateAndAdd() {
            // v2 : un prospect appartient à UNE liste → le « déplacer » passe par l'onglet Listes.
            if (window.ListesModule && typeof window.ListesModule.openCreate === 'function') {
                window.ListesModule.openCreate();
                _t('Liste créée — déplacez les prospects depuis l\u2019onglet Listes', 'info');
            } else {
                _t('Créez la liste depuis l\u2019onglet Listes', 'info');
            }
        };
    }

    async function _populateAddDropdown() {
        const box = document.getElementById('lists-dropdown-items');
        if (!box) return;
        box.innerHTML = '<div style="padding:12px;text-align:center;color:var(--ink3);font-size:11px">Chargement…</div>';
        try {
            const r = await fetch('/api/v2/listes');
            const d = await r.json();
            const listes = d.listes || d || [];
            if (!listes.length) {
                box.innerHTML = '<div style="padding:12px;text-align:center;color:var(--ink3);font-size:11px">Aucune liste. Créez-en une.</div>';
                return;
            }
            box.innerHTML = listes.slice(0, 30).map(l => `
                <div style="padding:8px 12px;cursor:pointer;border-bottom:1px solid #f1f5f9;font-size:12px;display:flex;justify-content:space-between;gap:8px"
                     onclick="window.ListesModule.toggleAddDropdown()">
                    <span>${typeof escHtml === 'function' ? escHtml(l.nom) : l.nom}</span>
                    <span style="color:var(--ink3);flex-shrink:0">${l.nb_leads ?? 0}</span>
                </div>`).join('')
                + '<div style="padding:8px 12px;font-size:10px;color:var(--ink3);font-style:italic">v2 : un prospect appartient à une seule liste — gérez l\u2019affectation dans l\u2019onglet Listes</div>';
        } catch (e) {
            box.innerHTML = '<div style="padding:12px;color:var(--red);font-size:11px">Erreur chargement des listes</div>';
        }
    }

    /* ─── Bouton « Nouveau scraping » : remplacer le placeholder V6 ──────── */

    const _legacyOpenScraper = window.openScraperModal;
    window.openScraperModal = function openScraperModal() {
        const m = document.getElementById('modal-scraper');
        if (m) {
            if (typeof openModal === 'function') openModal('modal-scraper');
            else m.style.display = 'flex';
            return;
        }
        if (typeof _legacyOpenScraper === 'function') _legacyOpenScraper();
    };

    console.log('[v6_restore] Actions panneau latéral restaurées (v2 data_extra)');
})();