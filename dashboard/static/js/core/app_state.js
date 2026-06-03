/**
 * dashboard/static/js/core/app_state.js
 * Global application state management for V5
 */

export class AppState {
    static state = {
        leads: [],
        pagination: {
            page: 1,
            total_pages: 1,
            total: 0
        },
        filters: {
            campaign_id: null,
            status: 'tous',
            search: ''
        },
        selectedIds: []
    };

    static init() {
        console.log('[AppState] Initialized');
    }

    static setState(newState) {
        this.state = { ...this.state, ...newState };
    }

    static setFilters(newFilters) {
        this.state.filters = { ...this.state.filters, ...newFilters };
    }
}

window.AppState = AppState;
window.AppState_V5 = AppState;
