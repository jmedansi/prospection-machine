/**
 * dashboard/static/js/core/api.js
 * Standardized API client for Incidenx v5
 */

export class API {
    static async request(endpoint, options = {}) {
        const response = await fetch(endpoint, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });
        if (!response.ok) throw new Error(`API Error: ${response.status}`);
        return await response.json();
    }

    /**
     * Fetch Leads with V5 mapping
     */
    static async getLeads(filters = {}) {
        const params = new URLSearchParams(filters);
        params.set('v', '5'); // Always use V5 mapping
        return await this.request(`/api/leads?${params.toString()}`);
    }

    /**
     * Fetch Stats with V5 mapping
     */
    static async getStats(filters = {}) {
        const params = new URLSearchParams(filters);
        params.set('v', '5'); // Always use V5 mapping
        return await this.request(`/api/stats?${params.toString()}`);
    }

    /**
     * Fetch specific Lead details
     */
    static async getLead(id) {
        return await this.request(`/api/leads/${id}?v=5`);
    }

    /**
     * Audit Actions
     */
    static async launchAudit(ids) {
        return await this.request(`/api/audit/launch`, {
            method: 'POST',
            body: JSON.stringify({ lead_ids: ids })
        });
    }

    /**
     * Email Actions
     */
    static async generateEmail(id) {
        return await this.request(`/api/email/generate`, {
            method: 'POST',
            body: JSON.stringify({ lead_ids: [id] })
        });
    }

    static async testEmail(id, to = null) {
        return await this.request(`/api/email/test`, {
            method: 'POST',
            body: JSON.stringify({ lead_id: id, to: to })
        });
    }

    static async approveEmail(id) {
        return await this.request(`/api/email/approve`, {
            method: 'POST',
            body: JSON.stringify({ lead_id: id })
        });
    }

    static async disapproveEmail(id) {
        return await this.request(`/api/email/disapprove`, {
            method: 'POST',
            body: JSON.stringify({ lead_id: id })
        });
    }

    static async sendApprovedEmail(id) {
        return await this.request(`/api/email/send`, {
            method: 'POST',
            body: JSON.stringify({ lead_ids: [id] })
        });
    }

    /**
     * Bulk Action Example
     */
    static async bulkAction(action, ids) {
        const endpoints = {
            'audit': '/api/audit/launch',
            'email': '/api/email/generate',
            'find-emails': '/api/leads/find-emails',
            'delete': '/api/leads/batch-delete'
        };
        const endpoint = endpoints[action] || `/api/leads/bulk`;
        return await this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify({ lead_ids: ids, action })
        });
    }
}

// Pour compatibilité avec d'autres scripts si besoin
window.API = API;
window.API_V5 = API;
