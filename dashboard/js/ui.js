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
    if (!el) return;
    const prev = el.textContent;
    el.textContent = text;
    if (prev !== String(text) && (el.classList.contains('mv') || el.classList.contains('pn'))) {
        el.classList.remove('bump');
        void el.offsetWidth; // reflow pour relancer l'animation
        el.classList.add('bump');
    }
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
            if (typeof loadStats === 'function') await loadStats();
            if (typeof loadCRM === 'function') await loadCRM();
            if (typeof loadTracking === 'function') await loadTracking();
            if (typeof loadCRMCounts === 'function') await loadCRMCounts();
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
const _toastIcons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span class="t-icon">${_toastIcons[type] || '✅'}</span><span class="t-msg">${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(110%)';
        setTimeout(() => toast.remove(), 350);
    }, 4000);
}

// --- Confirm Dialog (remplace window.confirm natif) ---
function showConfirm(message, { title = 'Confirmation', confirmText = 'Confirmer', cancelText = 'Annuler', danger = false } = {}) {
    return new Promise(resolve => {
        let modal = document.getElementById('_confirm-modal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = '_confirm-modal';
            modal.style.cssText = 'display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.55);backdrop-filter:blur(4px);align-items:center;justify-content:center;';
            modal.innerHTML = `
                <div id="_confirm-box" style="background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:28px 28px 22px;min-width:320px;max-width:460px;box-shadow:0 24px 48px rgba(0,0,0,0.35);animation:_cfade .15s ease">
                    <div id="_confirm-title" style="font-size:15px;font-weight:700;color:var(--ink);margin-bottom:10px"></div>
                    <div id="_confirm-msg"  style="font-size:13px;color:var(--ink2);line-height:1.55;margin-bottom:24px"></div>
                    <div style="display:flex;justify-content:flex-end;gap:10px">
                        <button id="_confirm-cancel" style="padding:8px 18px;border-radius:8px;border:1px solid var(--border);background:transparent;color:var(--ink2);font-size:13px;cursor:pointer;font-weight:500"></button>
                        <button id="_confirm-ok"     style="padding:8px 20px;border-radius:8px;border:none;font-size:13px;font-weight:600;cursor:pointer;"></button>
                    </div>
                </div>`;
            document.body.appendChild(modal);
        }

        const style = document.getElementById('_confirm-style') || (() => {
            const s = document.createElement('style');
            s.id = '_confirm-style';
            s.textContent = '@keyframes _cfade{from{opacity:0;transform:scale(.96)}to{opacity:1;transform:scale(1)}}';
            document.head.appendChild(s); return s;
        })();

        modal.querySelector('#_confirm-title').textContent = title;
        modal.querySelector('#_confirm-msg').textContent   = message;
        const cancelBtn = modal.querySelector('#_confirm-cancel');
        const okBtn     = modal.querySelector('#_confirm-ok');
        cancelBtn.textContent = cancelText;
        okBtn.textContent     = confirmText;
        okBtn.style.background = danger ? 'var(--red, #ef4444)' : 'var(--accent, #3b82f6)';
        okBtn.style.color      = '#fff';

        modal.style.display = 'flex';

        const close = val => {
            modal.style.display = 'none';
            okBtn.removeEventListener('click', onOk);
            cancelBtn.removeEventListener('click', onCancel);
            modal.removeEventListener('click', onBackdrop);
            resolve(val);
        };
        const onOk       = () => close(true);
        const onCancel   = () => close(false);
        const onBackdrop = e => { if (e.target === modal) close(false); };

        okBtn.addEventListener('click', onOk);
        cancelBtn.addEventListener('click', onCancel);
        modal.addEventListener('click', onBackdrop);
        setTimeout(() => okBtn.focus(), 50);
    });
}

// --- Skeleton loader ---
function skeletonTable(rows = 6) {
    const widths = [
        ['24px','120px','80px','50px','20px','20px','30px','60px','80px'],
        ['24px','100px','70px','40px','20px','20px','30px','60px','80px'],
        ['24px','140px','90px','55px','20px','20px','30px','60px','80px'],
    ];
    return Array.from({length: rows}, (_, i) =>
        `<tr class="skeleton-row">${widths[i % 3].map(w =>
            `<td><span class="skeleton" style="width:${w};height:13px"></span></td>`
        ).join('')}</tr>`
    ).join('');
}

function skeletonPanel() {
    return `<div class="panel-skeleton">
        <div style="display:flex;gap:14px;align-items:center">
            <span class="skeleton sk-avatar"></span>
            <div style="flex:1;display:flex;flex-direction:column;gap:8px">
                <span class="skeleton sk-line" style="width:60%"></span>
                <span class="skeleton sk-line" style="width:40%"></span>
            </div>
        </div>
        <span class="skeleton sk-block"></span>
        <span class="skeleton sk-line" style="width:100%"></span>
        <span class="skeleton sk-line" style="width:80%"></span>
        <span class="skeleton sk-line" style="width:90%"></span>
        <span class="skeleton sk-block"></span>
    </div>`;
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
