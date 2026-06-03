(function() {
    const API = window.API_V5 || window.API;
    const UI = window.UI || { toast: () => {} };

    class StatsModule {
        /**
         * Refresh all dashboard metrics
         */
        static async refresh() {
            try {
                const stats = await API.getStats();
                this.render(stats);
            } catch (error) {
                console.error('Failed to load stats:', error);
                UI.toast('Erreur lors du chargement des statistiques', 'error');
            }
        }

        /**
         * Map data to DOM elements
         */
        static render(data) {
            // Pipeline
            UI.setText('stat-audits-total', data.audited || 0);
            UI.setText('stat-pending-total', `+${data.scraped - data.audited || 0} en attente`);
            
            // Site
            UI.setText('stat-with-site-pct', data.scraped > 0 ? Math.round((data.audited / data.scraped) * 100) + '%' : '0%');
            UI.setText('stat-with-site', `${data.scraped || 0} leads`);

            // Emails
            UI.setText('stat-sent-total', data.sent || 0);
            UI.setText('provider-subtitle', `${data.ready_emails || 0} prêts à l'envoi`);

            // Responses
            UI.setText('stat-reponses', data.replies || 0);
            UI.setText('stat-reponses-positives', `${data.replies || 0} reçues`); // Example, replace with positives if available
            
            // Appointments
            UI.setText('stat-rdv', data.meetings || 0);
        }
    }

    window.StatsModule = StatsModule;
})();
