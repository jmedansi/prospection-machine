/**
 * dashboard/static/js/views/dashboard_v5.js
 * Main entry point for the V5 Dashboard
 */

import { Router } from '/static/js/core/router.js';
import { API } from '/static/js/core/api.js';
import { AppState } from '/static/js/core/app_state.js';
import { UI } from '/static/js/core/ui.js';
import { LeadsModule } from '/static/js/modules/leads.js';
import { StatsModule } from '/static/js/modules/stats.js';
import { ActionsModule } from '/static/js/modules/actions.js';
import { DetailsModule } from '/static/js/modules/details.js';
import { CRMModule } from '/static/js/modules/crm.js';
import { PlanningModule } from '/static/js/modules/planning.js';
import { JobsModule } from '/static/js/modules/jobs.js';

async function init() {
    console.log('🚀 [V5] Initializing Dashboard...');

    try {
        // 1. Initialize Navigation & Global State
        Router.init();
        AppState.init();

        // 2. Initialize UI & Actions (attach listeners)
        ActionsModule.init();
        DetailsModule.init();
        JobsModule.init();

        // 3. Initialize Leads (attach listeners & first load)
        if (LeadsModule.init) await LeadsModule.init();

        // 4. Load Stats
        if (StatsModule.refresh) await StatsModule.refresh();

        console.log('✅ [V5] Dashboard fully loaded');
    } catch (error) {
        console.error('❌ [V5] Initialization failed:', error);
    }
}

// Ensure DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
