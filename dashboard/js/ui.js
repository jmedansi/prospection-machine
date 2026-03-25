/**
 * dashboard/js/ui.js — Variables d'état et utilitaires UI
 */

// --- État Global ---
let _allLeads = [];
let _currentIndex = 0;
let _emailsData = [];
let _leadsPagination = { page: 1, total_pages: 1, total: 0, per_page: 50 };
let _activeCampaignId = null;
let _activeDateStart = null;
let _activeDateEnd = null;
let _selectedCollecteIds = []; // IDs des collectes cochées sur la page Collecte

const TITLES = {
    cockpit: 'Cockpit',
    collecte: 'Radar — Sourcing',
    campagnes: 'Studio — Prospection',
    suivi: 'Suivi & CRM',
    rapports: 'Rapports Historique',
    settings: 'Paramètres'
};

// --- Utilitaires de Base ---
function setInner(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
}

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function escHtml(s) {
    if (!s) return "";
    return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function makeSlug(nom) {
    if (!nom) return 'unnamed';
    let slug = nom.toLowerCase().replace(/[^a-z0-9\s]/g, '');
    slug = slug.replace(/\s+/g, '-');
    slug = slug.replace(/^-+|-+$/g, '');
    return slug.substring(0, 50);
}

// --- Navigation et Modals ---
async function nav(id, el) {
    console.log("  [Nav] Opening section:", id);
    const p = document.getElementById('pg-' + id);
    if (!p) {
        console.error("  [Nav] Section not found:", 'pg-' + id);
        return;
    }

    document.querySelectorAll('.pg').forEach(div => div.classList.remove('active'));
    document.querySelectorAll('.ni').forEach(link => link.classList.remove('active'));
    
    p.classList.add('active');
    if (el) el.classList.add('active');
    
    const ptEl = document.getElementById('PT');
    if (ptEl) ptEl.textContent = TITLES[id] || id;

    // Chargement spécifique à l'onglet
    try {
        if (id === 'collecte') {
            if (typeof loadCollectes === 'function') await loadCollectes();
        } else if (id === 'campagnes') {
            if (typeof loadEmails === 'function') await loadEmails();
            if (typeof loadCampaigns === 'function') await loadCampaigns();
        } else if (id === 'suivi') {
            if (typeof loadCRM === 'function') await loadCRM();
            if (typeof loadTracking === 'function') await loadTracking();
        } else if (id === 'rapports') {
            if (typeof loadReports === 'function') await loadReports();
        } else if (id === 'settings') {
            if (typeof loadSettings === 'function') await loadSettings();
            if (typeof loadConfig === 'function') await loadConfig();
        }
    } catch (e) { console.error(`  [Nav] Error loading data for ${id}:`, e); }
}

function tab(id, el) {
    const parent = el.closest('.pg');
    parent.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    parent.querySelectorAll('.tp').forEach(t => t.classList.remove('active'));
    el.classList.add('active');
    const tp = document.getElementById(id);
    if (tp) tp.classList.add('active');
}

function openModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }

// --- Thème ---
function toggleTheme() {
    const d = document.documentElement;
    const t = d.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    d.setAttribute('data-theme', t);
    localStorage.setItem('theme', t);
    const i = document.getElementById('TI');
    if (!i) return;
    if (t === 'dark') {
        i.innerHTML = '<path d="M12 2a6 6 0 0 1-6 10A6 6 0 0 0 12 2z" fill="currentColor"/>';
    } else {
        i.innerHTML = '<circle cx="8" cy="8" r="3.5" stroke="currentColor" stroke-width="1.4"/><path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3.1 3.1l1.1 1.1M11.8 11.8l1.1 1.1M3.1 12.9l1.1-1.1M11.8 4.2l1.1-1.1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>';
    }
}

// Initialisation du thème
(function() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    window.addEventListener('DOMContentLoaded', () => {
        const i = document.getElementById('TI');
        if (i && savedTheme === 'dark') {
            i.innerHTML = '<path d="M12 2a6 6 0 0 1-6 10A6 6 0 0 0 12 2z" fill="currentColor"/>';
        }
    });
})();

// --- Toasts ---
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// --- Formateurs de Badges/Pills ---
function pillPerf(score) {
    score = parseInt(score) || 0;
    const cls = score >= 70 ? 'bg' : score >= 50 ? 'bo' : 'br';
    return `<span class="b ${cls}">${score}</span>`;
}

function pillUrgence(score) {
    score = parseFloat(score) || 0;
    const cls = score >= 7 ? 'br' : score >= 4 ? 'bo' : 'bg';
    return `<span class="b ${cls}">${parseFloat(score).toFixed(0)}/10</span>`;
}

// --- Synthèse des Problèmes Audités ---
function getAllProblemes(l) {
    let probleme = [];
    let priorite = null;
    
    if (!l.a_site) {
        probleme.push({ texte: "Pas de site web", type: "critique" });
    }
    if (l.score_perf && l.score_perf < 50) {
        probleme.push({ texte: "Performance critique (" + l.score_perf + ")", type: "critique" });
    } else if (l.score_perf && l.score_perf < 70) {
        probleme.push({ texte: "Performance moyenne (" + l.score_perf + ")", type: "moyen" });
    }
    if (l.lcp && parseFloat(l.lcp) > 3) {
        probleme.push({ texte: "LCP lent (" + l.lcp + "s)", type: "critique" });
    } else if (l.lcp && parseFloat(l.lcp) > 2) {
        probleme.push({ texte: "LCP améliorable (" + l.lcp + "s)", type: "moyen" });
    }
    if (l.score_seo && l.score_seo < 60) {
        probleme.push({ texte: "SEO faible (" + l.score_seo + ")", type: "critique" });
    } else if (l.score_seo && l.score_seo < 80) {
        probleme.push({ texte: "SEO perfectible (" + l.score_seo + ")", type: "moyen" });
    }
    if (l.note && l.note < 4) {
        probleme.push({ texte: "Note Google basse (" + l.note + ")", type: "moyen" });
    }
    if (l.avis && l.avis < 20) {
        probleme.push({ texte: "Peu d'avis (" + l.avis + ")", type: "moyen" });
    }
    
    if (probleme.length > 0) {
        const crit = probleme.find(p => p.type === "critique");
        priorite = crit || probleme[0];
    }
    
    return { probleme, priorite };
}

function synthProbleme(l) {
    const { probleme, priorite } = getAllProblemes(l);
    if (probleme.length === 0) return "Tout semble OK";
    let result = probleme.map(p => {
        if (priorite && p.texte === priorite.texte) return "⭐ " + p.texte;
        return p.texte;
    });
    return result.slice(0, 3).join(' · ');
}

function synthProblemeDetail(l) {
    const { probleme, priorite } = getAllProblemes(l);
    if (probleme.length === 0) return "Tout semble OK";
    return probleme.map(p => {
        if (priorite && p.texte === priorite.texte) return "⭐ " + p.texte;
        return p.texte;
    }).join('<br>');
}
