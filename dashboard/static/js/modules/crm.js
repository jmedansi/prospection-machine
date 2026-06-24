/**
 * dashboard/static/js/modules/crm.js
 * Handles CRM view (Email Tracking & Stats)
 */

const API = window.API_V5 || window.API;
const UI = window.UI;

export class CRMModule {
    static filter = 'all';

    static async init() {
        this.renderBase();
        if (typeof window.unifiedLeadsLoadLists === 'function') {
            await window.unifiedLeadsLoadLists();
        }
        await this.loadStats();
        await this.loadList();
    }

    static renderBase() {
        const container = document.getElementById('section-crm-content');
        if (!container) return;

        container.innerHTML = `
            <div class="mg">
                <div class="mc" id="crm-stat-sent"><div class="ml">Envoyés</div><div class="mv">—</div></div>
                <div class="mc" id="crm-stat-open"><div class="ml">Ouverts</div><div class="mv">—</div><div class="ms">%</div></div>
                <div class="mc" id="crm-stat-click"><div class="ml">Cliqués</div><div class="mv">—</div><div class="ms">%</div></div>
                <div class="mc" id="crm-stat-reply"><div class="ml">Réponses</div><div class="mv">—</div><div class="ms">%</div></div>
            </div>

            <div class="actions-bar card" style="margin-bottom:20px;display:flex;gap:10px;padding:12px">
                ${['all','opened','clicked','replied','bounce'].map(f => 
                    `<button class="btn ${this.filter === f ? 'btn-primary' : 'btn-ghost'}" onclick="CRMModule.setFilter('${f}')">${
                        {all:'Tous',opened:'Ouverts',clicked:'Cliqués',replied:'Réponses',bounce:'Bounces'}[f]
                    }</button>`
                ).join('')}
            </div>

            <div id="crm-list" class="table-container card">
                <table class="campaign-table">
                    <thead>
                        <tr>
                            <th>Prospect</th>
                            <th>Statut</th>
                            <th>Dernier Event</th>
                            <th>Score</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="crm-tbody">
                        <tr><td colspan="5" style="text-align:center;padding:40px">Chargement...</td></tr>
                    </tbody>
                </table>
            </div>
        `;
    }

    static async loadStats() {
        try {
            const stats = await API.getStats();
            const e = stats.email_stats || {};
            UI.setText('crm-stat-sent', stats.pipeline?.envoyes || 0);
            UI.setHTML('crm-stat-open', `<div class="mv">${(e.taux_ouverture||0).toFixed(1)}</div><div class="ms">%</div>`);
            UI.setHTML('crm-stat-click', `<div class="mv">${(e.taux_clic||0).toFixed(1)}</div><div class="ms">%</div>`);
            UI.setHTML('crm-stat-reply', `<div class="mv">${(e.taux_reponse||0).toFixed(1)}</div><div class="ms">%</div>`);
        } catch (error) {
            console.error('CRM Stats fail:', error);
        }
    }

    static async loadList() {
        const tbody = document.getElementById('crm-tbody');
        if (!tbody) return;

        try {
            // Mapping filters to status for now
            let status = 'envoye';
            if (this.filter === 'replied') status = 'repondu';
            
            const listEl = document.getElementById('crm-filter-list');
            const listId = listEl ? listEl.value : '';
            
            const params = { statut: status, limit: 50 };
            if (listId) params.list_id = listId;

            const data = await API.getLeads(params);
            const leads = data.leads || [];

            if (leads.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:40px">Aucun email trouvé avec ce filtre</td></tr>';
                return;
            }

            tbody.innerHTML = leads.map(l => `
                <tr onclick="DetailsModule.openLead(${l.id}, 'tracking')">
                    <td class="f-w-600">${l.name}</td>
                    <td><span class="status-pill status-${l.status}">${l.status}</span></td>
                    <td>${l.status === 'repondu' ? '💬 Réponse reçue' : '📤 Envoyé'}</td>
                    <td><span class="badge ${l.urgency_score > 70 ? 'bg-danger' : 'bg-success'}">${l.urgency_score || 0}</span></td>
                    <td><button class="btn btn-icon">👁️</button></td>
                </tr>
            `).join('');
        } catch (error) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:40px">Erreur de chargement</td></tr>';
        }
    }

    static setFilter(f) {
        this.filter = f;
        this.renderBase();
        this.loadList();
    }
}

window.CRMModule = CRMModule;
