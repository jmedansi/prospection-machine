/**
 * dashboard/static/js/modules/leads.js
 * Handles Leads Table, Filtering, Search and Pagination
 */

// Use global exports from api.js (loaded as module in base.html)
const API = window.API_V5 || window.API;
const AppState = window.AppState || { init: () => {}, get: () => {}, set: () => {} };
const UI = window.UI || { toast: () => {}, showLoading: () => {}, hideLoading: () => {} };

class LeadsModule {
    static async init() {
        this.setupListeners();
        await this.refresh();
    }

    static setupListeners() {
        const searchInput = document.getElementById('search-lead');
        if (searchInput) {
            let timeout;
            searchInput.addEventListener('keyup', () => {
                clearTimeout(timeout);
                timeout = setTimeout(() => this.handleSearch(), 300);
            });
        }

        ['filter-statut', 'filter-site', 'filter-email', 'filter-sector'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('change', () => this.refresh(1));
        });

        // Event delegation for pagination
        document.addEventListener('click', (e) => {
            if (e.target.closest('#btn-prev-page')) {
                const page = AppState.state.pagination.page;
                if (page > 1) this.refresh(page - 1);
            }
            if (e.target.closest('#btn-next-page')) {
                const page = AppState.state.pagination.page;
                const total = AppState.state.pagination.total_pages;
                if (page < total) this.refresh(page + 1);
            }
        });

        // Row click for detail panel
        const tableBody = document.getElementById('tbody-campaign');
        if (tableBody) {
            tableBody.addEventListener('click', (e) => {
                const tr = e.target.closest('tr');
                if (!tr) return;
                
                // Don't open if clicking checkbox or actions
                if (e.target.closest('.lead-checkbox') || e.target.closest('.actions-cell') || e.target.closest('a')) {
                    return;
                }
                
                const id = tr.dataset.id;
                if (id) {
                    window.DetailsModule.openLead(id);
                }
            });
        }
    }

    static handleSearch() {
        const query = document.getElementById('search-lead').value;
        AppState.setFilters({ search: query });
        this.refresh(1);
    }

    /**
     * Fetch and render leads
     */
    static async refresh(page = 1) {
        console.log(`[LeadsModule] Refreshing page ${page}...`);
        const tableBody = document.getElementById('tbody-campaign');
        if (tableBody) tableBody.innerHTML = '<tr><td colspan="9" style="text-align:center;padding:40px">Chargement...</td></tr>';

        try {
            const params = {
                page,
                statut: document.getElementById('filter-statut')?.value || 'tous',
                site: document.getElementById('filter-site')?.value || 'tous',
                email: document.getElementById('filter-email')?.value || 'tous',
                sector: document.getElementById('filter-sector')?.value || 'tous',
                search: document.getElementById('search-lead')?.value || '',
                campaign_id: AppState.state.filters.campaign_id
            };

            console.log('[LeadsModule] Fetching with params:', params);
            const data = await API.getLeads(params);
            console.log('[LeadsModule] Data received:', data);
            
            // Fix: API returns flat pagination data, not a nested 'pagination' object
            const pagination = {
                page: data.page,
                total: data.total,
                total_pages: data.total_pages
            };

            AppState.setState({ 
                leads: data.leads, 
                pagination: pagination
            });

            this.render(data.leads);
            this.updatePaginationUI(pagination);
            this.updateCountUI(pagination.total);

        } catch (error) {
            console.error('Failed to load leads:', error);
            UI.toast('Erreur lors du chargement des leads', 'error');
        }
    }

    static render(leads) {
        const tableBody = document.getElementById('tbody-campaign');
        if (!tableBody) return;

        if (!leads || leads.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="9" style="text-align:center;padding:40px">Aucun lead trouvé</td></tr>';
            return;
        }

        tableBody.innerHTML = leads.map(lead => `
            <tr data-id="${lead.id}">
                <td><input type="checkbox" class="lead-checkbox" value="${lead.id}"></td>
                <td class="f-w-600 col-prospect" title="${this.escapeHTML(lead.name)}">${this.escapeHTML(lead.name)}</td>
                <td>${this.escapeHTML(lead.city || '-')}</td>
                <td><span class="badge ${this.getBadgeClass(lead.perf_score)}">${lead.perf_score || 0}</span></td>
                <td><span class="badge ${this.getBadgeClass(lead.seo_score)}">${lead.seo_score || 0}</span></td>
                <td><span class="badge ${this.getUrgencyClass(lead.urgency_score)}">${lead.urgency_score || 0}/10</span></td>
                <td><span class="status-pill status-${lead.status}">${lead.status}</span></td>
                <td>${lead.has_email ? '✅' : '❌'}</td>
                <td class="actions-cell">
                    <button class="btn-icon" title="Éditer" onclick="editLead(${lead.id})">✏️</button>
                    ${lead.report_url ? `<a href="${lead.report_url}" target="_blank" class="btn-icon" title="Rapport">📄</a>` : ''}
                </td>
            </tr>
        `).join('');
    }

    static updatePaginationUI(pagination) {
        console.log('[LeadsModule] Updating Pagination UI:', pagination);
        if (!pagination || typeof pagination.page === 'undefined') {
            console.error('[LeadsModule] Pagination data is invalid or missing:', pagination);
            return;
        }

        const page = pagination.page || 1;
        const total_pages = pagination.total_pages || 1;

        UI.setText('page-info', `page ${page} sur ${total_pages}`);
        
        const prevBtn = document.getElementById('btn-prev-page');
        const nextBtn = document.getElementById('btn-next-page');
        
        if (prevBtn) prevBtn.disabled = (page <= 1);
        if (nextBtn) nextBtn.disabled = (page >= total_pages);

        // Update select if needed
        const select = document.getElementById('page-select');
        if (select) {
            select.innerHTML = Array.from({length: total_pages}, (_, i) => 
                `<option value="${i+1}" ${i+1 === page ? 'selected' : ''}>${i+1}</option>`
            ).join('');
        }
    }

    static updateCountUI(total) {
        UI.setText('campaign-count', `${total} leads`);
    }

    static getBadgeClass(score) {
        if (!score) return 'bg-neutral';
        if (score >= 80) return 'bg-success';
        if (score >= 50) return 'bg-warning';
        return 'bg-danger';
    }

    static getUrgencyClass(score) {
        if (!score) return 'bg-neutral';
        if (score >= 7) return 'bg-danger';
        if (score >= 4) return 'bg-warning';
        return 'bg-success';
    }

    static escapeHTML(str) {
        if (!str) return '';
        const p = document.createElement('p');
        p.textContent = str;
        return p.innerHTML;
    }
}

window.LeadsModule = LeadsModule;

// ─── Global Edit Lead Function ─────────────────────────────
// Détecte automatiquement mobile vs desktop et appelle la bonne fonction
function editLead(leadId) {
    const isMobile = window.innerWidth <= 768 || 'ontouchstart' in window;
    const hasMobileEdit = typeof mOpenEditLead === 'function';
    
    if (isMobile && hasMobileEdit) {
        // Mode mobile: utiliser le sheet bottom
        mOpenEditLead(leadId);
    } else if (typeof openEditLeadFromPanel === 'function') {
        // Mode desktop: utiliser le modal
        openEditLeadFromPanel(leadId);
    } else {
        // Fallback: charger les données et afficher le modal desktop
        fetch(`/api/leads/${leadId}`).then(r => r.json()).then(resp => {
            const lead = resp.lead || resp;
            const modal = document.getElementById('modal-edit-lead');
            if (modal) {
                document.getElementById('edit-lead-id').value = lead.id || '';
                document.getElementById('edit-lead-nom').value = lead.nom || lead.name || '';
                document.getElementById('edit-lead-email').value = lead.email || '';
                document.getElementById('edit-lead-tel').value = lead.telephone || lead.phone || lead.tel || '';
                document.getElementById('edit-lead-site').value = lead.site_web || lead.website || lead.site || '';
                if (document.getElementById('edit-lead-sector')) {
                    document.getElementById('edit-lead-sector').value = lead.secteur || lead.sector || lead.category || '';
                }
                if (document.getElementById('edit-lead-ville')) {
                    document.getElementById('edit-lead-ville').value = lead.ville || lead.city || '';
                }
                modal.style.display = 'flex';
            } else {
                console.error('Modal edit lead non trouvé');
            }
        }).catch(e => {
            console.error('Erreur chargement lead:', e);
            if (typeof showToast === 'function') {
                showToast('Erreur de chargement du lead', 'error');
            }
        });
    }
}
