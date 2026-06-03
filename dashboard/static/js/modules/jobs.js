(function() {
    const API = window.API_V5;

    class JobsModule {
        static timer = null;

        static init() {
            if (this.timer) return;
            console.log('[JobsModule] Polling started');
            this.poll();
            this.timer = setInterval(() => this.poll(), 5000); // 5 seconds
        }

        static async poll() {
            try {
                const UI = window.UI;

                // 1. Poll Audit Status
                const auditResp = await fetch('/api/audit/status').then(r => r.json());
                this.updateBarV5('sidebar-audit', auditResp);
                
                if (!auditResp.running && this.lastAuditRunning) {
                    UI.toast('Audit terminé', 'success');
                    await this.showAuditRecap(auditResp);
                    if (window.unifiedLeadsLoad) window.unifiedLeadsLoad();
                }
                this.lastAuditRunning = auditResp.running;

                // 2. Poll Enrichment (Email Search) Status
                const enrichResp = await fetch('/api/leads/enrich/status').then(r => r.json());
                this.updateBarV5('sidebar-enrich', enrichResp);

                if (!enrichResp.running && this.lastEnrichRunning) {
                    UI.toast('Recherche d\'emails terminée', 'success');
                    this.showEnrichRecap(enrichResp);
                    if (window.unifiedLeadsLoad) window.unifiedLeadsLoad();
                }
                this.lastEnrichRunning = enrichResp.running;

                // 3. Poll Email Sending Status
                const emailResp = await fetch('/api/email/status').then(r => r.json()).catch(() => ({running:false}));
                this.updateBarV5('sidebar-email', emailResp);
                
                if (!emailResp.running && this.lastEmailRunning) {
                    UI.toast('Envoi d\'emails terminé', 'success');
                }
                this.lastEmailRunning = emailResp.running;

            } catch (error) {
                console.warn('[JobsModule] Polling error:', error);
            }
        }

        /**
         * Updates V5 Sidebar progress bars (sidebar-enrich, sidebar-audit, etc.)
         */
        static updateBarV5(id, data) {
            const el = document.getElementById(id);
            if (!el) return;

            if (data.running && data.total > 0) {
                const pct = Math.round((data.current / data.total) * 100);
                el.style.display = 'block';
                
                const pctEl = el.querySelector('.sb-progress-header span:last-child');
                if (pctEl) pctEl.textContent = `${pct}%`;
                
                const barEl = el.querySelector('.sb-progress-fill');
                if (barEl) barEl.style.width = `${pct}%`;
                
                const textEl = el.querySelector('.sb-progress-text');
                if (textEl) textEl.textContent = `${data.current}/${data.total} traité(s)...`;
            } else {
                el.style.display = 'none';
            }
        }

        static showEnrichRecap(data) {
            const success = data.success || 0;
            const total = data.total || 0;
            const failed = data.failed || 0;
            
            let html = `
                <div style="text-align:center; margin-bottom:24px">
                    <div style="font-size:48px; margin-bottom:12px">${success > 0 ? '🚀' : '📭'}</div>
                    <h3 style="margin:0; font-size:18px">Recherche terminée</h3>
                    <p style="color:var(--ink3); font-size:14px; margin-top:4px">${total} leads analysés</p>
                </div>
                
                <div class="recap-list">
                    <p><span>🎯 Emails trouvés</span> <span style="color:var(--accent)">+${success}</span></p>
                    <p><span>❓ Aucun résultat</span> <span style="color:var(--red)">${failed}</span></p>
                </div>

                <div style="font-size:12px; color:var(--ink3); background:var(--bg-app); padding:12px; border-radius:8px; margin-bottom:12px">
                    <i class="fas fa-info-circle"></i> 
                    Certains sites utilisent des protections anti-spam ou n'affichent aucun email publiquement.
                </div>
            `;
            
            if (data.results && data.results.length > 0) {
                html += `<div style="max-height:150px; overflow-y:auto; border-top:1px solid var(--border); padding-top:12px">
                            <p style="font-size:11px; font-weight:700; text-transform:uppercase; color:var(--ink3); margin-bottom:8px">Derniers résultats :</p>
                            <ul style="font-size:11px; padding:0; list-style:none; margin:0">`;
                data.results.slice(-8).reverse().forEach(r => {
                    const icon = r.status === 'success' ? '✅' : '❌';
                    const label = r.found && r.found.length > 0 ? `Trouvé : ${r.found[0]}` : 'Non trouvé';
                    html += `<li style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid var(--bg-app)">
                                <span>${icon} Lead #${r.id}</span>
                                <span style="color:${r.status === 'success' ? 'var(--accent)' : 'var(--ink3)'}">${label}</span>
                             </li>`;
                });
                html += `</ul></div>`;
            }

            window.UI.alert(html, { title: 'Récapitulatif Recherche Emails' });
        }

        static async showAuditRecap(data) {
            const total = data.total || 0;
            const failed = data.failed || 0;
            const success = Math.max(0, (data.current || 0) - failed);
            const icon = failed === 0 ? '✅' : '⚠️';
            const title = failed === 0 ? 'Audit terminé' : 'Audit terminé avec erreurs';

            let previewNote = `
                <div style="font-size:12px; color:var(--ink3); background:var(--bg-app); padding:12px; border-radius:8px; margin-top:14px">
                    <i class="fas fa-info-circle"></i>
                    Si un rapport a été généré, il est disponible localement via le dashboard (/previews/&lt;slug&gt;/).
                </div>
            `;

            try {
                const resp = await fetch('/api/previews');
                const json = await resp.json();
                if (json.rapports && json.rapports.length > 0) {
                    const count = json.rapports.length;
                    const firstSlug = json.rapports[0].slug;
                    previewNote = `
                        <div style="font-size:12px; color:var(--ink3); background:var(--bg-app); padding:12px; border-radius:8px; margin-top:14px">
                            <i class="fas fa-info-circle"></i>
                            ${count} rapport(s) local(aux) disponibles.
                            <a href="/previews/${firstSlug}/" target="_blank" style="color:var(--accent); text-decoration:underline;">Voir un rapport</a>
                        </div>
                    `;
                }
            } catch (e) {
                console.warn('[JobsModule] Impossible de récupérer les rapports locaux:', e);
            }

            let html = `
                <div style="text-align:center; margin-bottom:20px">
                    <div style="font-size:42px; margin-bottom:10px">${icon}</div>
                    <h3 style="margin:0; font-size:18px">${title}</h3>
                    <p style="color:var(--ink3); font-size:14px; margin-top:6px">${success}/${total} audits réussis</p>
                </div>
                <div class="recap-list">
                    <p><span>✔️ Audits OK</span> <span style="color:var(--accent)">${success}</span></p>
                    <p><span>❌ Échecs</span> <span style="color:var(--red)">${failed}</span></p>
                </div>
                ${previewNote}
            `;

            if (data.returncode && data.returncode !== 0) {
                html += `
                    <div style="margin-top:12px; padding:12px; border-radius:8px; background:#ffefef; color:#991b1b; font-size:13px">
                        <strong>Attention :</strong> le processus d'audit s'est terminé avec un code ${data.returncode}.
                    </div>
                `;
            }

            window.UI.alert(html, { title: 'Récapitulatif Audit' });
        }

        static stop() {
            if (this.timer) clearInterval(this.timer);
        }
    }

    window.JobsModule = JobsModule;
})();
