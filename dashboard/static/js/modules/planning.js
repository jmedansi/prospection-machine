/**
 * dashboard/static/js/modules/planning.js
 * Handles Planning view (Queue, Quota, Niche Stats)
 */

const API = window.API_V5 || window.API;
const UI = window.UI;

export class PlanningModule {
    static async init() {
        this.renderBase();
        await this.loadQueue();
    }

    static renderBase() {
        const container = document.getElementById('section-planificateur-content');
        if (!container) return;

        container.innerHTML = `
            <div id="quota-section" style="margin-bottom:24px">
                <div class="card" style="padding:24px">
                    <div style="display:flex;justify-content:space-between;margin-bottom:12px">
                        <span style="font-weight:700">Quota Emails Quotidien</span>
                        <span id="quota-text" style="color:var(--ink3)">Chargement...</span>
                    </div>
                    <div style="height:8px;background:var(--surface2);border-radius:4px;overflow:hidden">
                        <div id="quota-fill" style="height:100%;width:0%;background:var(--accent);transition:width 1s ease"></div>
                    </div>
                </div>
            </div>

            <div class="mg">
                <div class="mc">
                    <div class="ml">File d'attente</div>
                    <div id="queue-list" style="margin-top:15px;display:flex;flex-direction:column;gap:10px">
                        <div class="ms" style="text-align:center;padding:20px">Chargement des campagnes...</div>
                    </div>
                    <div style="margin-top:20px">
                        <button class="btn btn-primary" style="width:100%" onclick="PlanningModule.openScraper()">+ Nouvelle Campagne</button>
                    </div>
                </div>

                <div class="mc">
                    <div class="ml">Performance par Niche</div>
                    <div id="niche-stats" style="margin-top:15px;display:flex;flex-direction:column;gap:12px">
                        <div class="ms" style="text-align:center;padding:20px">Analyse des niches...</div>
                    </div>
                </div>
            </div>
        `;
    }

    static async loadQueue() {
        try {
            const [q, d] = await Promise.all([
                fetch('/api/planning/quota').then(r => r.json()),
                fetch('/api/planning').then(r => r.json())
            ]);

            // Render Quota
            const used = q.sent || 0;
            const max = q.quota || 100;
            const pct = Math.min(100, Math.round((used / max) * 100));
            UI.setText('quota-text', `${used} / ${max} envoyés aujourd'hui`);
            const fill = document.getElementById('quota-fill');
            if (fill) fill.style.width = `${pct}%`;

            // Render Queue
            const queueList = document.getElementById('queue-list');
            const campaigns = d.campaigns || [];
            if (campaigns.length === 0) {
                queueList.innerHTML = '<div class="ms">Aucune campagne en attente</div>';
            } else {
                queueList.innerHTML = campaigns.map(c => `
                    <div class="card-inner" style="padding:12px;background:var(--bg-app);border-radius:8px;display:flex;justify-content:space-between;align-items:center">
                        <div>
                            <div style="font-weight:700;font-size:13px">${c.secteur} · ${c.city || c.ville}</div>
                            <div style="font-size:11px;color:var(--ink3)">${c.limit_leads} leads · ${c.date_planifiee} ${c.heure}</div>
                        </div>
                        <span class="status-pill status-${c.statut}">${c.statut}</span>
                    </div>
                `).join('');
            }

            // Load Niche Stats
            this.loadNicheStats();
        } catch (error) {
            console.error('Queue load fail:', error);
        }
    }

    static async loadNicheStats() {
        try {
            const niches = await fetch('/api/stats/niches').then(r => r.json());
            const nicheContainer = document.getElementById('niche-stats');
            if (niches.length === 0) {
                nicheContainer.innerHTML = '<div class="ms">Pas encore assez de données</div>';
                return;
            }

            nicheContainer.innerHTML = niches.slice(0, 5).map(n => {
                const rate = n.envois > 0 ? ((n.clics / n.envois) * 100).toFixed(1) : 0;
                return `
                    <div>
                        <div style="display:flex;justify-content:space-between;margin-bottom:4px;font-size:12px">
                            <span style="font-weight:600">${n.category} (${n.ville})</span>
                            <span style="color:var(--accent);font-weight:800">${rate}% clic</span>
                        </div>
                        <div style="height:4px;background:var(--surface2);border-radius:2px;overflow:hidden">
                            <div style="height:100%;width:${rate}%;background:var(--accent)"></div>
                        </div>
                    </div>
                `;
            }).join('');
        } catch (error) {
            console.error('Niche stats fail:', error);
        }
    }

    static openScraper() {
        UI.toast('Le lanceur de campagne sera disponible dans la prochaine étape', 'info');
    }
}

window.PlanningModule = PlanningModule;
