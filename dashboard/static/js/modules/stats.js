(function() {
    // Résolu à l'appel : core/api.js ET core/ui.js sont des modules (exécutés en
    // defer) — au chargement de cette feuille, window.API/window.UI ne sont pas
    // encore définis.
    function getAPI() {
        return window.API_V5 || window.API;
    }
    function getUI() {
        return window.UI || { toast: () => {}, setText: () => {} };
    }

    class StatsModule {
        /**
         * Refresh all dashboard metrics
         */
        static async refresh() {
            try {
                const stats = await getAPI().getStats();
                this.render(stats);
            } catch (error) {
                console.error('Failed to load stats:', error);
                getUI().toast('Erreur lors du chargement des statistiques', 'error');
            }
        }

        /**
         * Map data to DOM elements
         */
        static render(data) {
            // Pipeline
            getUI().setText('stat-audits-total', data.audited || 0);
            getUI().setText('stat-pending-total', `+${data.scraped - data.audited || 0} en attente`);
            
            // Site
            getUI().setText('stat-with-site-pct', data.scraped > 0 ? Math.round((data.audited / data.scraped) * 100) + '%' : '0%');
            getUI().setText('stat-with-site', `${data.scraped || 0} leads`);

            // Emails
            getUI().setText('stat-sent-total', data.sent || 0);
            getUI().setText('provider-subtitle', `${data.ready_emails || 0} prêts à l'envoi`);

            // Responses
            getUI().setText('stat-reponses', data.replies || 0);
            getUI().setText('stat-reponses-positives', `${data.replies || 0} reçues`); // Example, replace with positives if available
            
            // Appointments
            getUI().setText('stat-rdv', data.meetings || 0);
        }
    }

    window.StatsModule = StatsModule;
})();
