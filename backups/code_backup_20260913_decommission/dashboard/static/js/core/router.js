/**
 * dashboard/static/js/core/router.js
 * handles view switching in the V5 dashboard
 */

export class Router {
    static views = ['cockpit', 'campagne', 'leads', 'sources', 'planificateur', 'sniper', 'suivi', 'roi', 'settings', 'health'];

    static init() {
        console.log('[Router] Initialized');

        // Expose nav globally for compatibility with sidebar.html onclick handlers
        window.nav = (view, element) => this.navigateTo(view, element);
    }

    static navigateTo(view, element) {
        console.log(`[Router] Navigating to: ${view}`);

        // 1. Update active nav link
        document.querySelectorAll('.ni').forEach(link => link.classList.remove('active'));
        if (element) {
            element.classList.add('active');
        } else {
            const link = document.getElementById(`nav-${view}`);
            if (link) link.classList.add('active');
        }

        // 2. Clear placeholder if exists
        const oldPlaceholder = document.getElementById('section-placeholder');
        if (oldPlaceholder) oldPlaceholder.classList.remove('active');

        // 3. Update visible sections
        document.querySelectorAll('.v-section').forEach(section => {
            section.classList.remove('active');
        });

        const targetSection = document.getElementById(`section-${view}`);
        if (targetSection) {
            targetSection.classList.add('active');

            // 4. Initialize feature-specific modules
            if (view === 'suivi' && window.CRMModule) window.CRMModule.init();
            if (view === 'planificateur' && window.PlanningModule) window.PlanningModule.init();
            if (view === 'cockpit' && window.LeadsModule) window.LeadsModule.refresh();

            // Update Page Title in Topbar
            const pageTitle = document.getElementById('PT');
            if (pageTitle) {
                const label = element?.innerText || view.charAt(0).toUpperCase() + view.slice(1);
                pageTitle.innerText = label.split('\n')[0].trim();
            }
        } else {
            console.warn(`[Router] Section 'section-${view}' not found. Showing placeholder.`);
            this.showPlaceholder(view);
        }
    }

    static showPlaceholder(view) {
        let container = document.querySelector('.ct');
        if (!container) container = document.body;

        let placeholder = document.getElementById('section-placeholder');
        if (!placeholder) {
            placeholder = document.createElement('div');
            placeholder.id = 'section-placeholder';
            placeholder.className = 'v-section';
            container.appendChild(placeholder);
        }

        placeholder.innerHTML = `
            <div class="card" style="text-align:center;padding:100px 20px;">
                <h2 style="margin-bottom:10px;">🚧 Section ${view.toUpperCase()}</h2>
                <p style="color:var(--ink3)">Cette vue est en cours de migration vers V5.</p>
                <div style="margin-top:20px;">
                    <button class="btn btn-primary" onclick="nav('cockpit')">Retour au Cockpit</button>
                </div>
            </div>
        `;

        placeholder.classList.add('active');
    }
}

window.Router_V5 = Router;
