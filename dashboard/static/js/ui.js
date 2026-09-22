/**
 * dashboard/js/ui.js — Variables d'état et utilitaires UI
 */

// --- État Global ---
let _allLeads = [];
let _currentIndex = 0;
let _emailsData = [];
let _leadsPagination = { page: 1, total_pages: 1, total: 0, per_page: 50 };
var _activeCampaignId = null;
let _activeSector = null;
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

function openModal(id) { const el = document.getElementById(id); if (el) el.classList.add('active'); }
function closeModal(id) { const el = document.getElementById(id); if (el) el.classList.remove('active'); }

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

// --- Alert & Popup Dialogs (remplace window.alert natif par de vrais popups modernes) ---
const _popupIcons = {
    info: 'ℹ️',
    success: '✅',
    warning: '⚠️',
    error: '❌',
    danger: '🚨'
};

const _popupColors = {
    info: 'var(--accent, #3b82f6)',
    success: '#10b981',
    warning: '#f59e0b',
    error: '#ef4444',
    danger: '#ef4444'
};

function _popupEnsureAnimStyle() {
    if (!document.getElementById('_popup-anim-style')) {
        const s = document.createElement('style');
        s.id = '_popup-anim-style';
        s.textContent = '@keyframes _popfade{from{opacity:0;transform:scale(.92) translateY(8px)}to{opacity:1;transform:scale(1) translateY(0)}}';
        document.head.appendChild(s);
    }
}

function _popupReplayAnimation(box) {
    const anim = box.style.animation;
    box.style.animation = 'none';
    void box.offsetWidth;
    box.style.animation = anim || '';
}

function _popupClose(modal, ns, val) {
    const state = modal._popupState;
    if (!state || state.ns !== ns) return;
    modal._popupState = null;
    modal.style.display = 'none';
    const r = state.resolve;
    // laisse le microtask s'exécuter, puis resolve (idempotent)
    setTimeout(() => r && r(val), 0);
}

function _popupBind(modal, ns, opts) {
    if (modal._popupBound === ns) return;
    modal._popupBound = ns;

    const onOk = () => _popupClose(modal, ns, opts.okValue);
    const onCancel = () => _popupClose(modal, ns, opts.cancelValue);
    const onBackdrop = (e) => { if (e.target === modal) onCancel(); };
    const onKey = (e) => {
        if (e.key === 'Escape') { e.preventDefault(); onCancel(); }
        else if (e.key === 'Enter' && !opts.noEnter) { e.preventDefault(); onOk(); }
    };

    modal.addEventListener('click', onBackdrop);
    if (opts.okBtn) opts.okBtn.addEventListener('click', onOk);
    if (opts.cancelBtn) opts.cancelBtn.addEventListener('click', onCancel);
    document.addEventListener('keydown', onKey);
}

function showAlert(message, { title = '', type = 'info', buttonText = 'Compris', html = false } = {}) {
    return new Promise(resolve => {
        _popupEnsureAnimStyle();

        let modal = document.getElementById('_alert-popup-modal');
        const create = !modal;
        if (!modal) {
            modal = document.createElement('div');
            modal.id = '_alert-popup-modal';
            modal.style.cssText = 'display:none;position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,0.6);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);align-items:center;justify-content:center;padding:16px;box-sizing:border-box;';
            modal.innerHTML = `
                <div id="_alert-popup-box" style="background:var(--surface, #1e293b);border:1px solid var(--border, rgba(255,255,255,0.1));border-radius:16px;padding:24px;width:100%;min-width:300px;max-width:440px;max-height:90vh;overflow-y:auto;box-shadow:0 24px 48px rgba(0,0,0,0.45);animation:_popfade .18s cubic-bezier(0.16, 1, 0.3, 1);display:flex;flex-direction:column;gap:16px;box-sizing:border-box;margin:auto">
                    <div style="display:flex;align-items:flex-start;gap:14px">
                        <div id="_alert-popup-icon" style="font-size:24px;line-height:1;flex-shrink:0;padding:6px;border-radius:10px;background:rgba(255,255,255,0.05);min-width:36px;height:36px;display:flex;align-items:center;justify-content:center"></div>
                        <div style="flex:1;min-width:0">
                            <h3 id="_alert-popup-title" style="margin:0 0 6px 0;font-size:15px;font-weight:700;color:var(--ink, #fff)"></h3>
                            <div id="_alert-popup-msg" style="font-size:13px;line-height:1.6;color:var(--ink2, #cbd5e1);word-break:break-word;white-space:pre-wrap"></div>
                        </div>
                    </div>
                    <div style="display:flex;justify-content:flex-end;margin-top:6px">
                        <button id="_alert-popup-ok" style="padding:9px 22px;border-radius:8px;border:none;background:var(--accent, #3b82f6);color:#fff;font-size:13px;font-weight:600;cursor:pointer;transition:opacity .15s ease">Compris</button>
                    </div>
                </div>`;
            document.body.appendChild(modal);
        }

        // Déduction automatique du type et du titre par défaut
        const msgStr = String(message ?? '');
        if (type === 'info') {
            const lower = (String(title) + ' ' + msgStr).toLowerCase();
            if (lower.includes('erreur') || lower.includes('échec') || lower.includes('impossible') || lower.includes('refusé')) type = 'error';
            else if (lower.includes('succès') || lower.includes('réussi') || lower.includes('enregistré')) type = 'success';
            else if (lower.includes('attention') || lower.includes('veuillez') || lower.includes('avertissement') || lower.includes('aucune')) type = 'warning';
        }

        if (!title) {
            title = type === 'error' ? 'Erreur' : type === 'success' ? 'Succès' : type === 'warning' ? 'Attention' : 'Information';
        }

        const box = modal.querySelector('#_alert-popup-box');
        const iconEl = modal.querySelector('#_alert-popup-icon');
        const titleEl = modal.querySelector('#_alert-popup-title');
        const msgEl = modal.querySelector('#_alert-popup-msg');
        const okBtn = modal.querySelector('#_alert-popup-ok');

        iconEl.textContent = _popupIcons[type] || 'ℹ️';
        iconEl.style.background = (type === 'warning' || type === 'error') ? 'rgba(239,68,68,0.08)' : 'rgba(255,255,255,0.05)';
        titleEl.textContent = title;
        if (html) msgEl.innerHTML = message;
        else msgEl.textContent = msgStr;

        okBtn.textContent = buttonText;
        okBtn.style.background = _popupColors[type] || 'var(--accent, #3b82f6)';

        modal._popupState = { ns: 'alert', resolve };
        _popupBind(modal, 'alert', { okBtn, okValue: undefined, cancelValue: undefined });
        modal.style.display = 'flex';
        box.scrollTop = 0;
        _popupReplayAnimation(box);
        setTimeout(() => okBtn.focus(), 50);
    });
}

function showPopup(options = {}) {
    if (typeof options === 'string') options = { message: options };
    return showAlert(options.message || options.html || '', options);
}

// Remplacer window.alert natif par notre popup
if (typeof window !== 'undefined') {
    window.showAlert = showAlert;
    window.showPopup = showPopup;
    window.alert = function (msg) {
        return showAlert(msg);
    };
}

// --- Confirm Dialog (remplace window.confirm natif) ---
function showConfirm(message, { title = 'Confirmation', confirmText = 'Confirmer', cancelText = 'Annuler', danger = false, html = false } = {}) {
    return new Promise(resolve => {
        _popupEnsureAnimStyle();

        let modal = document.getElementById('_confirm-modal');
        const create = !modal;
        if (!modal) {
            modal = document.createElement('div');
            modal.id = '_confirm-modal';
            modal.style.cssText = 'display:none;position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,0.6);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);align-items:center;justify-content:center;padding:16px;box-sizing:border-box;';
            modal.innerHTML = `
                <div id="_confirm-box" style="background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:26px;width:100%;min-width:300px;max-width:440px;max-height:90vh;overflow-y:auto;box-shadow:0 24px 48px rgba(0,0,0,0.45);animation:_popfade .18s cubic-bezier(0.16, 1, 0.3, 1);margin:auto;display:flex;flex-direction:column;gap:16px;box-sizing:border-box">
                    <div style="display:flex;align-items:flex-start;gap:14px">
                        <div style="font-size:24px;line-height:1;flex-shrink:0;padding:6px;border-radius:10px;background:rgba(255,255,255,0.05);min-width:36px;height:36px;display:flex;align-items:center;justify-content:center">${danger ? '⚠️' : '❓'}</div>
                        <div style="flex:1;min-width:0">
                            <div id="_confirm-title" style="font-size:15px;font-weight:700;color:var(--ink);margin-bottom:6px"></div>
                            <div id="_confirm-msg" style="font-size:13px;color:var(--ink2);line-height:1.6;word-break:break-word;white-space:pre-wrap"></div>
                        </div>
                    </div>
                    <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:6px">
                        <button id="_confirm-cancel" style="padding:8px 18px;border-radius:8px;border:1px solid var(--border);background:transparent;color:var(--ink2);font-size:13px;cursor:pointer;font-weight:500;transition:background .15s ease"></button>
                        <button id="_confirm-ok" style="padding:8px 20px;border-radius:8px;border:none;font-size:13px;font-weight:600;cursor:pointer;color:#fff;transition:opacity .15s ease"></button>
                    </div>
                </div>`;
            document.body.appendChild(modal);
        }

        const box = modal.querySelector('#_confirm-box');
        modal.querySelector('#_confirm-title').textContent = title;
        const msgEl = modal.querySelector('#_confirm-msg');
        const cancelBtn = modal.querySelector('#_confirm-cancel');
        const okBtn = modal.querySelector('#_confirm-ok');
        if (html) msgEl.innerHTML = message;
        else msgEl.textContent = message;
        cancelBtn.textContent = cancelText;
        okBtn.textContent = confirmText;
        okBtn.style.background = danger ? 'var(--red, #ef4444)' : 'var(--accent, #3b82f6)';

        modal._popupState = { ns: 'confirm', resolve };
        _popupBind(modal, 'confirm', { okBtn, cancelBtn, okValue: true, cancelValue: false });
        modal.style.display = 'flex';
        box.scrollTop = 0;
        _popupReplayAnimation(box);
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
