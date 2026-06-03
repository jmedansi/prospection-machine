/**
 * dashboard/static/js/modules/details.js
 * Handles Lead Detail Side Panel (Infos, Audit, Email, Tracking)
 */

const API = window.API_V5 || window.API;
const UI = window.UI;

class DetailsModule {
    static currentLead = null;
    static currentTab = 'infos';

    static init() {
        this.setupListeners();
    }

    static setupListeners() {
        document.querySelectorAll('.side-panel-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                this.switchTab(tab.dataset.tab);
            });
        });
    }

    /**
     * Open the side panel for a specific lead
     */
    static async openLead(leadId) {
        console.log(`[DetailsModule] Opening lead ${leadId}...`);
        UI.openSidePanel();
        UI.setHTML('panel-content', '<div style="padding:40px;text-align:center">Chargement...</div>');
        UI.setHTML('panel-footer', '');

        try {
            const resp = await API.getLead(leadId);
            this.currentLead = resp.lead || resp;
            this.currentTab = 'infos';
            
            // Update Header
            UI.setText('panel-lead-name', this.currentLead.name || 'Lead');
            UI.setText('panel-lead-meta', `${this.currentLead.city || '-'} · ${this.currentLead.sector || '-'}`);
            
            this.renderTab(this.currentTab);
        } catch (error) {
            console.error('Failed to load lead details:', error);
            UI.toast('Erreur lors du chargement des détails', 'error');
            UI.setHTML('panel-content', '<div style="padding:40px;text-align:center">Erreur de chargement.</div>');
        }
    }

    static switchTab(tab) {
        this.currentTab = tab;
        UI.toggleActive('.side-panel-tab', tab);
        this.renderTab(tab);
    }

    static renderTab(tab) {
        if (!this.currentLead) return;
        
        const content = document.getElementById('panel-content');
        const footer = document.getElementById('panel-footer');
        
        // Reset
        content.innerHTML = '';
        footer.innerHTML = '';

        switch (tab) {
            case 'infos':
                this.renderInfos(content, footer);
                break;
            case 'audit':
                this.renderAudit(content, footer);
                break;
            case 'email':
                this.renderEmail(content, footer);
                break;
            case 'tracking':
                this.renderTracking(content, footer);
                break;
        }
    }

    static renderInfos(content, footer) {
        const lead = this.currentLead;
        content.innerHTML = `
            <div class="info-grid" style="display:flex;flex-direction:column;gap:16px">
                <div class="row"><div class="lbl" style="font-size:11px;color:var(--ink3);text-transform:uppercase;font-weight:700">Statut</div><div class="val"><span class="status-pill status-${lead.status}">${lead.status}</span></div></div>
                <div class="row"><div class="lbl" style="font-size:11px;color:var(--ink3);text-transform:uppercase;font-weight:700">Email</div><div class="val">${lead.email ? `<a href="mailto:${lead.email}" style="color:var(--accent);font-weight:600">${lead.email}</a>` : 'Non disponible'}</div></div>
                <div class="row"><div class="lbl" style="font-size:11px;color:var(--ink3);text-transform:uppercase;font-weight:700">Téléphone</div><div class="val">${lead.phone || '—'}</div></div>
                <div class="row"><div class="lbl" style="font-size:11px;color:var(--ink3);text-transform:uppercase;font-weight:700">Email 2</div><div class="val">${lead.email_2 ? `<a href="mailto:${lead.email_2}" style="color:var(--accent);font-weight:600">${lead.email_2}</a>` : '—'}</div></div>
                <div class="row"><div class="lbl" style="font-size:11px;color:var(--ink3);text-transform:uppercase;font-weight:700">Téléphone 2</div><div class="val">${lead.phone_2 || '—'}</div></div>
                <div class="row"><div class="lbl" style="font-size:11px;color:var(--ink3);text-transform:uppercase;font-weight:700">Site Web</div><div class="val">${lead.website ? `<a href="${lead.website}" target="_blank" style="color:var(--accent)">${lead.website}</a>` : '—'}</div></div>
                <div class="row"><div class="lbl" style="font-size:11px;color:var(--ink3);text-transform:uppercase;font-weight:700">Avis Google</div><div class="val">${lead.reviews || 0} avis · note ${lead.rating || '-'}</div></div>
                <hr style="border:none;border-top:1px solid var(--border);margin:8px 0">
                <div class="row"><div class="lbl" style="font-size:11px;color:var(--ink3);text-transform:uppercase;font-weight:700">Notes (Sauvegarde auto)</div>
                     <textarea id="panel-lead-notes" class="inp" style="width:100%;height:80px;resize:vertical;font-size:12px;margin-top:4px" onblur="DetailsModule.saveNotes(${lead.id}, this.value)" placeholder="Ajouter une note...">${lead.notes || ''}</textarea>
                </div>
                <hr style="border:none;border-top:1px solid var(--border);margin:8px 0">
                <div class="row"><div class="lbl" style="font-size:11px;color:var(--ink3);text-transform:uppercase;font-weight:700">Probleme Diagnostiqué</div><div class="val" style="color:var(--ink2)">${lead.main_problem || '—'}</div></div>
                <div class="row"><div class="lbl" style="font-size:11px;color:var(--ink3);text-transform:uppercase;font-weight:700">Service Proposé</div><div class="val" style="font-weight:600;color:var(--ink)">${lead.suggested_service || '—'}</div></div>
                
                <!-- Section Plus d'infos -->
                <div style="margin-top:12px;padding:12px;background:var(--surface2);border-radius:8px;border-left:3px solid var(--accent)">
                    <div style="font-size:11px;color:var(--ink3);text-transform:uppercase;font-weight:700;margin-bottom:8px">✨ Plus d'infos</div>
                    <div style="font-size:12px;display:flex;flex-direction:column;gap:8px">
                        ${lead.date_scraping ? `<div><span style="color:var(--ink3)">Détecté le :</span> ${new Date(lead.date_scraping).toLocaleDateString('fr-FR')}</div>` : ''}
                        ${lead.mot_cle ? `<div><span style="color:var(--ink3)">Mot-clé :</span> <span class="badge">${lead.mot_cle}</span></div>` : ''}
                        
                        ${(() => {
                            try {
                                if (!lead.donnees_audit) return '';
                                const audit = typeof lead.donnees_audit === 'string' ? JSON.parse(lead.donnees_audit) : lead.donnees_audit;
                                let html = '';
                                
                                // Si c'est une pub Facebook
                                if (audit.ad_start) {
                                    html += `<div><span style="color:var(--ink3)">Diffusion :</span> ${audit.ad_start}</div>`;
                                }
                                if (audit.ad_body) {
                                    html += `<div style="margin-top:4px"><span style="color:var(--ink3);display:block;margin-bottom:2px">Contenu de la pub :</span>
                                             <div style="font-style:italic;background:var(--surface1);padding:8px;border-radius:4px;border:1px solid var(--border)">${audit.ad_body}</div></div>`;
                                }
                                
                                // Autres technos
                                if (audit.cms || audit.cms_detected) {
                                    html += `<div><span style="color:var(--ink3)">Technologie :</span> ${audit.cms || audit.cms_detected}</div>`;
                                }

                                if (audit.fan_count) {
                                    html += `<div><span style="color:var(--ink3)">Notoriété :</span> ${audit.fan_count} abonnés</div>`;
                                }

                                return html;
                            } catch(e) { return ''; }
                        })()}
                    </div>
                </div>
            </div>
        `;
        
        footer.innerHTML = `
            <button class="btn btn-secondary" style="flex:1" onclick="DetailsModule.switchTab('audit')">Voir Audit</button>
            <button class="btn btn-primary" style="flex:1" onclick="DetailsModule.quickAction()">Action Rapide</button>
        `;
    }

    static renderAudit(content, footer) {
        const lead = this.currentLead;
        if (!lead.urgency_score && (lead.status === 'scrape' || lead.status === 'scraped')) {
            content.innerHTML = '<div style="padding:40px;text-align:center">Lead non audité.</div>';
            footer.innerHTML = `<button class="btn btn-primary" style="flex:1" onclick="DetailsModule.launchAudit(${lead.id})">Lancer l'audit</button>`;
            return;
        }

        const scoreColor = lead.urgency_score >= 80 ? 'var(--red)' : (lead.urgency_score >= 50 ? 'var(--orange)' : 'var(--accent)');

        content.innerHTML = `
            <div class="audit-view">
                <div class="score-box" style="background:var(--surface2);padding:24px;border-radius:var(--radius-md);text-align:center;margin-bottom:20px">
                    <div style="font-size:48px;font-weight:800;color:${scoreColor}">${lead.urgency_score || 0}</div>
                    <div style="font-size:12px;color:var(--ink3);text-transform:uppercase;font-weight:700">Score d'urgence / 100</div>
                </div>
                
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px">
                    <div style="background:var(--surface2);padding:16px;border-radius:var(--radius-md);text-align:center">
                        <div style="font-size:18px;font-weight:700;color:var(--accent)">${lead.perf_score || 0}%</div>
                        <div style="font-size:10px;color:var(--ink3)">Performance</div>
                        <div style="font-size:9px;color:var(--ink3);margin-top:4px">LCP: ${lead.lcp || 0}ms</div>
                    </div>
                    <div style="background:var(--surface2);padding:16px;border-radius:var(--radius-md);text-align:center">
                        <div style="font-size:18px;font-weight:700;color:var(--accent)">${lead.seo_score || 0}%</div>
                        <div style="font-size:10px;color:var(--ink3)">SEO Mobile</div>
                        <div style="font-size:9px;color:var(--ink3);margin-top:4px">CMS: ${lead.cms || '—'}</div>
                    </div>
                </div>

                ${lead.report_url ? `<div style="margin-bottom:16px"><a href="${lead.report_url}" target="_blank" class="btn btn-ghost" style="width:100%;justify-content:center">📄 Voir le rapport complet</a></div>` : ''}
                
                <div class="txt-box" style="background:var(--accent-soft);padding:16px;border-radius:var(--radius-md);font-size:13px;line-height:1.6;color:var(--ink2)">
                    ${lead.audit_summary || 'Diagnostic établi : ' + (lead.main_problem || 'Prêt pour l\'envoi.')}
                </div>
            </div>
        `;

        footer.innerHTML = `<button class="btn btn-secondary" style="flex:1" onclick="DetailsModule.launchAudit(${lead.id})">Régénérer Audit</button>`;
    }

    static renderEmail(content, footer) {
        const lead = this.currentLead;
        if (!lead.email_subject && lead.status !== 'email_genere' && lead.status !== 'envoye') {
            content.innerHTML = '<div style="padding:40px;text-align:center">Email non généré.</div>';
            footer.innerHTML = `<button class="btn btn-primary" style="flex:1" onclick="DetailsModule.generateEmail(${lead.id})">Générer l'email</button>`;
            return;
        }

        content.innerHTML = `
            <div class="row" style="margin-bottom:12px"><div class="lbl" style="font-size:11px;color:var(--ink3);text-transform:uppercase;font-weight:700">Objet</div><div class="val" style="font-weight:700">${lead.email_subject || '—'}</div></div>
            <iframe id="email-preview" srcdoc="Loading..." style="width:100%;height:350px;border:1px solid var(--border);border-radius:8px;background:white"></iframe>
        `;

        const iframe = document.getElementById('email-preview');
        if (iframe && lead.email_body) {
            const body = `<!DOCTYPE html><html><head><style>body{font-family:sans-serif;font-size:14px;line-height:1.5;color:#334155;padding:20px}</style></head><body><div id="typewriter-root"></div></body></html>`;
            iframe.srcdoc = body;
            
            iframe.onload = () => {
                const target = iframe.contentDocument.getElementById('typewriter-root');
                if (target) {
                    this.typeWriteHTML(target, lead.email_body);
                }
            };
        }
    }

    static typeWriteHTML(el, html) {
        let i = 0;
        const speed = 2; // ms per char
        const type = () => {
            if (i < html.length) {
                // Si on rencontre un <, on saute jusqu'au > pour ne pas casser le HTML pendant le rendu
                if (html.charAt(i) === '<') {
                    const end = html.indexOf('>', i);
                    if (end !== -1) i = end;
                }
                el.innerHTML = html.substring(0, i + 1);
                i++;
                setTimeout(type, speed);
            }
        };
        type();
    }

        const isEnvoye = lead.status === 'envoye' || lead.email_status === 'envoye';

        footer.innerHTML = `
            <button class="btn btn-secondary" style="flex:1" onclick="DetailsModule.testEmail(${lead.id})" ${isEnvoye ? 'disabled' : ''}>Test</button>
            <button class="btn ${lead.is_approved ? (isEnvoye ? 'btn-ghost' : 'btn-success') : 'btn-primary'}" 
                    style="flex:1" 
                    onclick="DetailsModule.approveAndSend(${lead.id})"
                    ${isEnvoye ? 'disabled' : ''}>
                ${isEnvoye ? 'Déjà Envoyé' : (lead.is_approved ? 'Envoyer Maintenant' : 'Approuver & Envoyer')}
            </button>
        `;
    }

    static renderTracking(content, footer) {
        const lead = this.currentLead;
        if (!lead.sent_at && lead.status !== 'envoye' && lead.status !== 'repondu') {
            content.innerHTML = '<div style="padding:40px;text-align:center">Pas encore de tracking (email non envoyé).</div>';
            return;
        }

        content.innerHTML = `
            <div class="tracking-steps" style="display:flex;flex-direction:column;gap:12px">
                <div style="display:flex;align-items:center;gap:12px;padding:12px;background:var(--surface2);border-radius:8px">
                    <div style="font-size:20px">📤</div>
                    <div><div style="font-weight:700;font-size:13px">Email Envoyé</div><div style="font-size:11px;color:var(--ink3)">Le ${lead.sent_at || '-'}</div></div>
                    <div style="margin-left:auto;color:var(--accent)">✅</div>
                </div>
                <div style="display:flex;align-items:center;gap:12px;padding:12px;background:var(--surface2);border-radius:8px;opacity:${lead.is_opened ? '1' : '0.5'}">
                    <div style="font-size:20px">👀</div>
                    <div><div style="font-weight:700;font-size:13px">Email Ouvert</div><div style="font-size:11px;color:var(--ink3)">${lead.opened_at || (lead.is_opened ? 'Ouvert' : 'En attente...')}</div></div>
                    <div style="margin-left:auto;color:var(--accent)">${lead.is_opened ? '✅' : '⬜'}</div>
                </div>
                <div style="display:flex;align-items:center;gap:12px;padding:12px;background:var(--surface2);border-radius:8px;opacity:${lead.is_clicked ? '1' : '0.5'}">
                    <div style="font-size:20px">🖱️</div>
                    <div><div style="font-weight:700;font-size:13px">Lien Cliqué</div><div style="font-size:11px;color:var(--ink3)">${lead.is_clicked ? 'Rapport consulté' : 'En attente...'}</div></div>
                    <div style="margin-left:auto;color:var(--accent)">${lead.is_clicked ? '✅' : '⬜'}</div>
                </div>
                <div style="display:flex;align-items:center;gap:12px;padding:12px;background:var(--surface2);border-radius:8px;opacity:${lead.is_replied ? '1' : '0.5'}">
                    <div style="font-size:20px">💬</div>
                    <div><div style="font-weight:700;font-size:13px">Réponse Reçue</div><div style="font-size:11px;color:var(--ink3)">${lead.is_replied ? 'Contact établi' : 'En attente...'}</div></div>
                    <div style="margin-left:auto;color:var(--accent)">${lead.is_replied ? '✅' : '⬜'}</div>
                </div>
            </div>
        `;
    }

    // ACTIONS
    static async launchAudit(id) {
        UI.toast("Lancement de l'audit...", "info");
        try {
            await API.launchAudit([id]);
            UI.toast("Audit lancé", "success");
            this.openLead(id);
        } catch (e) {
            UI.toast("Échec de l'audit", "error");
        }
    }

    static async generateEmail(id) {
        UI.toast("Génération de l'email...", "info");
        try {
            await API.generateEmail(id);
            UI.toast("Email généré", "success");
            this.openLead(id);
        } catch (e) {
            UI.toast("Échec de génération", "error");
        }
    }

    static async testEmail(id) {
        UI.toast("Envoi de l'email de test...", "info");
        try {
            await API.testEmail(id);
            UI.toast("Email de test envoyé", "success");
        } catch (e) {
            UI.toast("Erreur envoi test", "error");
        }
    }

    static async approveAndSend(id) {
        try {
            if (!this.currentLead.is_approved) {
                UI.toast("Approbation...", "info");
                await API.approveEmail(id);
                this.currentLead.is_approved = true;
            }
            UI.toast("Envoi en cours...", "info");
            await API.sendApprovedEmail(id);
            UI.toast("Email envoyé avec succès", "success");
            this.openLead(id);
        } catch (e) {
            UI.toast("Erreur lors de l'envoi", "error");
        }
    }

    static quickAction() {
        const lead = this.currentLead;
        const status = lead.status;
        if (status === 'scrape' || status === 'scraped' || status === 'en_attente') this.launchAudit(lead.id);
        else if (status === 'audite') this.generateEmail(lead.id);
        else this.switchTab('email');
    }

    static async saveNotes(id, notes) {
        try {
            const r = await fetch(`/api/leads/${id}/edit`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ notes: notes })
            });
            const d = await r.json();
            if (d.success) {
                if (this.currentLead && this.currentLead.id === id) {
                    this.currentLead.notes = notes;
                }
                UI.toast("Notes sauvegardées", "success");
                // Optionnel: mettre à jour la ligne dans la table si nécessaire,
                // mais les notes ne sont pas affichées dans la table actuellement.
            } else {
                UI.toast("Erreur sauvegarde notes", "error");
            }
        } catch (e) {
            console.error(e);
            UI.toast("Erreur sauvegarde notes", "error");
        }
    }
}

window.DetailsModule = DetailsModule;
