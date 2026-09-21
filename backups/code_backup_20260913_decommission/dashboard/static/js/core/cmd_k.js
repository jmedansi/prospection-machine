/**
 * dashboard/static/js/core/cmd_k.js
 * Command Palette (Cmd+K) logic
 */

const CMD_K = {
    isOpen: false,
    results: [],
    activeIndex: 0,
    leads: [],
    campaigns: []
};

function initCmdK() {
    // Inject HTML
    const html = `
        <div id="cmd-k-overlay" class="cmd-k-overlay" style="display:none">
            <div class="cmd-k-modal">
                <div class="cmd-k-header">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--ink3)"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                    <input type="text" id="cmd-k-input" placeholder="Rechercher un lead, une campagne ou une action..." autocomplete="off">
                    <div class="cmd-k-esc">ESC</div>
                </div>
                <div id="cmd-k-results" class="cmd-k-results">
                    <!-- Results will be injected here -->
                </div>
                <div class="cmd-k-footer">
                    <span><kbd>↑↓</kbd> Naviguer</span>
                    <span><kbd>↵</kbd> Sélectionner</span>
                    <span><kbd>ESC</kbd> Fermer</span>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', html);

    // Event Listeners
    window.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            toggleCmdK();
        }
        if (e.key === 'Escape' && CMD_K.isOpen) {
            toggleCmdK(false);
        }
        if (CMD_K.isOpen) {
            if (e.key === 'ArrowDown') { e.preventDefault(); navigateCmdK(1); }
            if (e.key === 'ArrowUp') { e.preventDefault(); navigateCmdK(-1); }
            if (e.key === 'Enter') { e.preventDefault(); executeCmdK(); }
        }
    });

    document.getElementById('cmd-k-input').addEventListener('input', (e) => {
        searchCmdK(e.target.value);
    });

    document.getElementById('cmd-k-overlay').addEventListener('click', (e) => {
        if (e.target.id === 'cmd-k-overlay') toggleCmdK(false);
    });
}

function toggleCmdK(force) {
    CMD_K.isOpen = force !== undefined ? force : !CMD_K.isOpen;
    const el = document.getElementById('cmd-k-overlay');
    el.style.display = CMD_K.isOpen ? 'flex' : 'none';
    if (CMD_K.isOpen) {
        document.getElementById('cmd-k-input').focus();
        document.getElementById('cmd-k-input').value = '';
        searchCmdK('');
        // Pre-fetch data if needed
        fetchCmdKData();
    }
}

async function fetchCmdKData() {
    try {
        const [rLeads, rCamps] = await Promise.all([
            fetch('/api/leads/all?limit=50'),
            fetch('/api/campaigns')
        ]);
        const dLeads = await rLeads.json();
        const dCamps = await rCamps.json();
        CMD_K.leads = dLeads.leads || [];
        CMD_K.campaigns = dCamps || [];
    } catch (e) { console.error('CmdK Data Fetch failed', e); }
}

function searchCmdK(q) {
    q = q.toLowerCase().trim();
    const results = [];

    // 1. Actions rapides
    const actions = [
        { title: 'Aller au scraping', icon: '🕸️', action: () => { nav('campagne'); setTimeout(() => switchSectionTabDirect('sources'), 50); } },
        { title: 'Lancer un audit de masse', icon: '🔍', action: () => launchSelectedAudits() },
        { title: 'Voir les leads à traiter', icon: '📋', action: () => { nav('campagne'); setTimeout(() => switchSectionTabDirect('leads'), 50); } },
        { title: 'Ouvrir le mode Kanban', icon: '🗂', action: () => { nav('campagne'); setTimeout(() => { switchSectionTabDirect('leads'); setLeadsView('kanban'); }, 50); } },
        { title: 'Aller aux paramètres', icon: '⚙️', action: () => nav('settings') }
    ];
    actions.filter(a => a.title.toLowerCase().includes(q)).forEach(a => {
        results.push({ ...a, type: 'action' });
    });

    // 2. Campagnes
    (CMD_K.campaigns || []).filter(c => c.name && c.name.toLowerCase().includes(q)).slice(0, 5).forEach(c => {
        results.push({ title: `Campagne : ${c.name}`, icon: '🚀', type: 'campaign', id: c.id });
    });

    // 3. Leads
    (CMD_K.leads || []).filter(l => l.nom && l.nom.toLowerCase().includes(q) || (l.site_web && l.site_web.toLowerCase().includes(q))).slice(0, 10).forEach(l => {
        results.push({ title: l.nom, sub: l.site_web || l.ville, icon: '👤', type: 'lead', id: l.id });
    });

    CMD_K.results = results;
    CMD_K.activeIndex = 0;
    renderCmdKResults();
}

function renderCmdKResults() {
    const el = document.getElementById('cmd-k-results');
    if (!CMD_K.results.length) {
        el.innerHTML = '<div class="cmd-k-no-results">Aucun résultat trouvé</div>';
        return;
    }

    el.innerHTML = CMD_K.results.map((r, i) => `
        <div class="cmd-k-item ${i === CMD_K.activeIndex ? 'active' : ''}" onclick="executeCmdK(${i})">
            <span class="cmd-k-icon">${r.icon}</span>
            <div class="cmd-k-text">
                <div class="cmd-k-title">${r.title}</div>
                ${r.sub ? `<div class="cmd-k-sub">${r.sub}</div>` : ''}
            </div>
            <div class="cmd-k-type">${r.type}</div>
        </div>
    `).join('');
}

function navigateCmdK(dir) {
    CMD_K.activeIndex = (CMD_K.activeIndex + dir + CMD_K.results.length) % CMD_K.results.length;
    renderCmdKResults();
    // Ensure active item is visible
    const active = document.querySelector('.cmd-k-item.active');
    if (active) active.scrollIntoView({ block: 'nearest' });
}

// Helper pour switchSectionTab sans avoir besoin de passer un élément (pour Cmd+K)
function switchSectionTabDirect(tabName) {
    const section = document.querySelector('.section-tabs');
    if (!section) return;
    const tabs = section.querySelectorAll('.section-tab');
    const targetBtn = Array.from(tabs).find(t => t.textContent.toLowerCase().includes(tabName === 'leads' ? 'leads' : tabName));
    if (targetBtn) switchSectionTab(tabName, targetBtn);
}

function executeCmdK(index) {
    const idx = index !== undefined ? index : CMD_K.activeIndex;
    const item = CMD_K.results[idx];
    if (!item) return;

    toggleCmdK(false);

    if (item.action) {
        item.action();
    } else if (item.type === 'lead') {
        nav('campagne');
        setTimeout(() => { switchSectionTabDirect('leads'); openLeadPanel(item.id); }, 50);
    } else if (item.type === 'campaign') {
        nav('campagne');
        setTimeout(() => switchSectionTabDirect('sources'), 50);
    }
}

// Initialisation
document.addEventListener('DOMContentLoaded', initCmdK);
