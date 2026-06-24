/**
 * dashboard/static/js/modules/scraper_watchdog.js
 *
 * Watchdog global — poll /api/scraper/all-status toutes les 5 secondes.
 * Affiche dans la sidebar :
 *   - barre de progression + source active
 *   - bouton STOP accessible depuis n'importe quelle page
 *
 * Ne dépend d'aucun autre module. Doit être chargé avant les autres.
 */

// ─── État global watchdog ─────────────────────────────────────────────────────

const _watchdog = {
    interval: null,
    lastRunning: false,
    POLL_MS: 5000,
    bannerHidden: false, // Flag pour fermer manuellement la bannière
    failedHidden: false, // Flag pour fermer la bannière d'erreurs
    dismissedFailedIds: [], // IDs des campagnes en erreur ignorées par l'user
    lastFailedIds: [],
    activeIndex: 0,      // Index de la tâche affichée si multi-tâches
    tickCount: 0,
    initialized: false,
};

// ─── API endpoints par source ─────────────────────────────────────────────────

const _WATCHDOG_SOURCES = [
    { key: 'ads', label: 'Google Ads' },
    { key: 'fb_ads', label: 'Facebook Ads' },
    { key: 'tech', label: 'Tech/E-com' },
    { key: 'jobs', label: 'Jobs' },
    { key: 'maps', label: 'Google Maps' },
    { key: 'audit', label: 'Audit' },
    { key: 'enrichment', label: 'Recherche Emails' },
];

// ─── Stop function globale (appelée par les boutons Stop du dashboard) ────────

async function sniperStop(sourceKey) {
    if (!confirm(`Voulez-vous arrêter cette tâche (${sourceKey}) ?`)) return;

    try {
        const r = await fetch('/api/scraper/stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: sourceKey })
        });

        const contentType = r.headers.get("content-type");
        if (contentType && contentType.indexOf("application/json") !== -1) {
            const d = await r.json();
            const msg = d.message || d.error || 'Arrêt demandé';
            _wdLog(`⏹ ${sourceKey} — ${msg}`);
            if (typeof showToast === 'function') showToast(`⏹ ${sourceKey} : ${msg}`, 'info');
        } else {
            const text = await r.text();
            _wdLog(`⏹ ${sourceKey} — Erreur serveur ${r.status}`);
            console.error('[watchdog] Non-JSON response:', text);
        }
    } catch (e) {
        console.error('[watchdog] sniperStop error:', e);
    }
}

async function sniperForceStop(sourceKey) {
    if (!confirm("⚠️ Voulez-vous vraiment FORCER l'arrêt immédiat ?")) return;

    // On utilise maintenant la route centralisée dans campaigns.py
    const url = '/api/scraper/force-stop';

    try {
        const r = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: sourceKey })
        });

        const contentType = r.headers.get("content-type");
        if (contentType && contentType.indexOf("application/json") !== -1) {
            const d = await r.json();
            _wdLog(`💀 Force Stop — ${d.message || d.error || 'Effectué'}`);
            if (typeof showToast === 'function') showToast(`💀 Tâche arrêtée`, 'warning');
        } else {
            const text = await r.text();
            _wdLog(`💀 Force Stop — Erreur serveur ${r.status}`);
            console.error('[watchdog] ForceStop Non-JSON:', text);
            if (typeof showToast === 'function') showToast(`⚠️ Erreur serveur ${r.status}`, 'error');
        }
    } catch (e) {
        console.error('[watchdog] forceStop error:', e);
        if (typeof showToast === 'function') showToast(`❌ Erreur connexion`, 'error');
    }
}

function watchdogCloseBanner() {
    _watchdog.bannerHidden = true;
    localStorage.setItem('pm_watchdog_banner_hidden', 'true');
    const banner = document.getElementById('wd-banner');
    if (banner) banner.style.display = 'none';
    document.body.classList.remove('wd-active');
}

function watchdogDismissFailed() {
    _watchdog.failedHidden = true;
    const currentIds = _watchdog.lastFailedIds || [];

    // Persistance dans localStorage pour que ça survive au refresh
    try {
        const saved = JSON.parse(localStorage.getItem('pm_dismissed_failed_ids') || '[]');
        const updated = [...new Set([...saved.map(String), ...currentIds.map(String)])];
        localStorage.setItem('pm_dismissed_failed_ids', JSON.stringify(updated));
    } catch (e) { console.error('[watchdog] storage error', e); }

    const el = document.getElementById('wd-failed-banner');
    if (el) el.style.display = 'none';
}

// ─── Init ─────────────────────────────────────────────────────────────────────

function watchdogInit() {
    if (_watchdog.initialized) return;
    _watchdog.initialized = true;

    // Charger l'état de la bannière
    if (localStorage.getItem('pm_watchdog_banner_hidden') === 'true') {
        _watchdog.bannerHidden = true;
    }

    _injectBanner();
    _injectStyles();
    _watchdog.interval = setInterval(_watchdogTick, _watchdog.POLL_MS);
    _watchdogTick(); // première vérification immédiate
}

// ─── Tick — poll all-status ───────────────────────────────────────────────────

async function _watchdogTick() {
    try {
        _watchdog.tickCount++;
        const r = await fetch('/api/scraper/all-status');
        if (!r.ok) return;
        const d = await r.json();
        _renderWatchdog(d);
    } catch (_) { /* silencieux */ }
}

function _renderWatchdog(d) {
    const sources = d.sources || [];
    const anyRunning = d.running || sources.some(s => s.running);
    const failedRecent = d.failed_recent || [];

    const banner = document.getElementById('wd-banner');
    
    // Sidebar bars
    const bars = {
        maps: document.getElementById('sidebar-scrape'),
        ads: document.getElementById('sidebar-scrape'),
        fb_ads: document.getElementById('sidebar-scrape'),
        tech: document.getElementById('sidebar-scrape'),
        jobs: document.getElementById('sidebar-scrape'),
        audit: document.getElementById('sidebar-audit'),
        enrichment: document.getElementById('sidebar-enrich'),
        sending: document.getElementById('sidebar-email')
    };

    if (!anyRunning) {
        if (_watchdog.lastRunning) {
            if (typeof refreshAll === 'function') refreshAll();
            localStorage.removeItem('pm_watchdog_banner_hidden');
            _watchdog.bannerHidden = false;
        }
        _watchdog.lastRunning = false;
        if (banner) banner.style.display = 'none';
        Object.values(bars).forEach(b => { if(b) b.style.display = 'none'; });
        document.body.classList.remove('wd-active');
    } else {
        _watchdog.lastRunning = true;

        const activeSources = sources.filter(s => s.running);
        if (activeSources.length > 1) {
            if (_watchdog.tickCount % 2 === 0) {
                _watchdog.activeIndex = (_watchdog.activeIndex + 1) % activeSources.length;
            }
        } else {
            _watchdog.activeIndex = 0;
        }

        const active = activeSources[_watchdog.activeIndex];
        
        // --- Gestion de la bannière du haut ---
        if (active && banner) {
            if (_watchdog.bannerHidden) {
                banner.style.display = 'none';
                document.body.classList.remove('wd-active');
            } else {
                banner.style.display = 'flex';
                document.body.classList.add('wd-active');
            }
            
            const pct = active.total > 0 ? Math.round((active.processed / active.total) * 100) : null;
            const pctStr = pct !== null ? `${pct}%` : '…';
            
            const labelEl = document.getElementById('wd-label');
            const phaseEl = document.getElementById('wd-phase');
            const progEl = document.getElementById('wd-progress');
            const stopBtn = document.getElementById('wd-stop-btn');

            const phaseLabels = {
                scraping: 'Collecte', enrichment: 'Emails',
                audit: 'Audit', email_gen: 'Copies', sending: 'Envoi',
            };

            if (labelEl) labelEl.textContent = `${active.label || active.key} en cours${active.campaign_name ? ` · ${active.campaign_name}` : ''}`;
            if (phaseEl) phaseEl.textContent = active.phase ? `Phase : ${phaseLabels[active.phase] || active.phase}` : '';
            if (progEl) progEl.textContent = pct !== null ? `${active.processed || 0} / ${active.total || '?'} (${pctStr})` : `${active.accepted || 0} leads qualifiés`;

            if (stopBtn) {
                stopBtn.textContent = active.stop_requested ? '💀 Kill' : '⏹ Stop';
                stopBtn.onclick = () => active.stop_requested ? sniperForceStop(active.key) : sniperStop(active.key);
            }
        }

        // --- Mise à jour des barres latérales (Sidebar) ---
        // On n'affiche que celles qui sont réellement 'running'
        Object.entries(bars).forEach(([key, el]) => {
            if (!el) return;
            const s = sources.find(src => src.key === key);
            if (s && s.running) {
                el.style.display = 'block';
                const pct = s.total > 0 ? Math.round((s.processed / s.total) * 100) : (s.accepted > 0 ? null : 0);
                const pctStr = pct !== null ? `${pct}%` : '…';
                
                const pctEl = el.querySelector('.sb-progress-pct') || document.getElementById(`sidebar-${key}-pct`);
                const barEl = el.querySelector('.sb-progress-fill') || document.getElementById(`sidebar-${key}-bar`);
                const textEl = el.querySelector('.sb-progress-text') || document.getElementById(`sidebar-${key}-text`);
                
                if (pctEl) pctEl.textContent = pctStr;
                if (barEl) barEl.style.width = (pct || 30) + '%';
                if (textEl) {
                    if (key === 'audit' || key === 'enrichment' || key === 'sending') {
                        textEl.innerHTML = `<strong>${s.processed || 0}</strong>/${s.total || '?'}` + (s.failed ? ` · <span style="color:var(--red)">${s.failed} ❌</span>` : '');
                    } else {
                        textEl.textContent = s.current_kw ? `${s.label} — ${s.current_kw}` : `${s.accepted || 0} leads · ${s.rejected || 0} rejetés`;
                    }
                }
            } else {
                // Si la source n'est pas running, on cache sa barre (sauf si une autre source partage le même élément, ex: maps/ads)
                const otherRunningSharing = sources.some(src => src.running && bars[src.key] === el);
                if (!otherRunningSharing) {
                    el.style.display = 'none';
                }
            }
        });

        // Pill mobile (masquée)
        const mobilePill = document.getElementById('wd-mobile-pill');
        if (mobilePill) {
            mobilePill.style.display = 'none';
        }
    }

    // ── Badges dans le panneau Sources (si ouvert) ────────────────────────────
    sources.forEach(s => {
        if (typeof _setSourceRunning === 'function') _setSourceRunning(s.key, s.running);
    });

    _renderFailedBanner(failedRecent);
}

// ─── Injection HTML bannière ───────────────────────────────────────────────────

function _injectBanner() {
    if (document.getElementById('wd-banner')) return;
    const el = document.createElement('div');
    el.id = 'wd-banner';
    el.innerHTML = `
        <div id="wd-icon">⚙️</div>
        <div id="wd-info">
            <span id="wd-label">Scraper en cours</span>
            <span id="wd-phase" style="font-size:11px;opacity:.7"></span>
            <span id="wd-progress" style="font-size:11px;opacity:.7"></span>
            <span id="wd-log" style="font-size:11px;color:#fb923c;font-style:italic;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></span>
        </div>
        <div style="display:flex; gap:10px; align-items:center;">
            <button id="wd-stop-btn" title="Arrêter proprement le scraper">⏹ Stop</button>
            <button id="wd-close-btn" onclick="watchdogCloseBanner()" title="Masquer la bannière" style="background:none; border:none; color:white; cursor:pointer; font-size:16px; opacity:.5;">✕</button>
        </div>
    `;
    el.style.display = 'none';
    document.body.appendChild(el);
}

function _injectMobilePill() {
    if (document.getElementById('wd-mobile-pill')) return;
    const el = document.createElement('div');
    el.id = 'wd-mobile-pill';
    el.onclick = () => {
        _watchdog.bannerHidden = false; // Réafficher la bannière si on clique dessus
        _watchdogTick();
    };
    el.innerHTML = `
        <div class="wd-pill-icon-container">
            <div class="wd-pill-icon">⚙️</div>
            <div class="wd-pill-count" style="display:none; position:absolute; top:-5px; right:-5px; background:#ef4444; color:white; font-size:9px; padding:1px 4px; border-radius:10px; border:1px solid #1e1e2e;"></div>
        </div>
        <div class="wd-pill-content">
            <span class="wd-pill-label">Scraper</span>
            <span class="wd-pill-pct">...</span>
        </div>
    `;
    el.style.display = 'none';
    document.body.appendChild(el);
}

function _injectStyles() {
    if (document.getElementById('wd-styles')) return;
    const s = document.createElement('style');
    s.id = 'wd-styles';
    s.textContent = `
        #wd-banner {
            position: fixed;
            top: 0; left: 0; right: 0;
            z-index: 9999;
            display: none;
            align-items: center;
            gap: 10px;
            padding: 8px 16px;
            background: linear-gradient(90deg, #1e1e2e 0%, #2a1f3d 100%);
            color: #e2e8f0;
            font-size: 13px;
            border-bottom: 1px solid rgba(251,146,60,0.3);
            box-shadow: 0 2px 12px rgba(0,0,0,0.3);
        }
        #wd-icon {
            animation: wd-spin 2s linear infinite;
            font-size: 16px;
        }
        @keyframes wd-spin {
            0%   { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        #wd-info {
            flex: 1;
            display: flex;
            gap: 12px;
            align-items: center;
            flex-wrap: wrap;
        }
        #wd-label {
            font-weight: 600;
            color: #fb923c;
        }
        #wd-stop-btn {
            background: rgba(239,68,68,0.15);
            border: 1px solid rgba(239,68,68,0.4);
            color: #ef4444;
            padding: 4px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
            white-space: nowrap;
        }
        #wd-stop-btn:hover {
            background: rgba(239,68,68,0.3);
        }
        /* Décaler le contenu quand la bannière est visible */
        body.wd-active .app,
        body.wd-active .mn {
            margin-top: 36px;
        }

        /* Fix mobile padding-bottom pour la navigation */
        @media (max-width: 768px) {
            .ct, .mobile-content {
                padding-bottom: 120px !important;
            }
        }

        #wd-mobile-pill {
            position: fixed;
            bottom: 80px; /* Au-dessus de la nav mobile */
            right: 16px;
            z-index: 9997;
            background: rgba(30, 30, 46, 0.85);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            border: 1px solid rgba(251, 146, 60, 0.3);
            border-radius: 50px;
            padding: 6px 14px;
            display: none;
            align-items: center;
            gap: 10px;
            color: white;
            font-size: 11px;
            font-weight: 600;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4);
            animation: wd-pulse 2s infinite ease-in-out;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        .wd-pill-icon-container {
            position: relative;
            display: flex;
            align-items: center;
        }
        .wd-pill-icon {
            font-size: 12px;
            animation: wd-spin 2s linear infinite;
        }
        .wd-pill-pct {
            color: #fb923c;
            background: rgba(251, 146, 60, 0.1);
            padding: 2px 6px;
            border-radius: 10px;
            margin-left: 4px;
        }
        @keyframes wd-pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.03); }
            100% { transform: scale(1); }
        }

        @media (min-width: 769px) {
            #wd-mobile-pill { display: none !important; }
        }
    `;
    document.head.appendChild(s);
}

function _wdLog(msg) {
    console.info('[watchdog]', msg);
}

// ─── Bannière d'erreurs récentes ──────────────────────────────────────────────

function _renderFailedBanner(failed) {
    const currentIds = (failed || []).map(f => String(f.id));
    _watchdog.lastFailedIds = currentIds;

    let el = document.getElementById('wd-failed-banner');

    // Charger les IDs dismiss du localStorage
    let dismissed = [];
    try {
        dismissed = JSON.parse(localStorage.getItem('pm_dismissed_failed_ids') || '[]').map(String);
    } catch (e) { dismissed = []; }

    if (!failed || !failed.length) {
        if (el) el.style.display = 'none';
        if (dismissed.length) localStorage.removeItem('pm_dismissed_failed_ids');
        return;
    }

    // Nettoyage du localStorage : on ne garde que les IDs qui sont encore en erreur
    const stillFailedDismissed = dismissed.filter(id => currentIds.includes(id));
    if (stillFailedDismissed.length !== dismissed.length) {
        localStorage.setItem('pm_dismissed_failed_ids', JSON.stringify(stillFailedDismissed));
        dismissed = stillFailedDismissed;
    }

    // Est-ce qu'il y a au moins une erreur qui n'a PAS été dismiss par l'user ?
    const hasNewUnseenErrors = currentIds.some(id => !dismissed.includes(id));

    if (!hasNewUnseenErrors) {
        if (el) el.style.display = 'none';
        return;
    }

    if (!el) {
        el = document.createElement('div');
        el.id = 'wd-failed-banner';
        el.style.cssText = `
            position:fixed; bottom:16px; right:16px; z-index:9998;
            max-width:380px; background:#1c1017; border:1px solid rgba(239,68,68,0.35);
            border-radius:12px; box-shadow:0 8px 32px rgba(0,0,0,0.4);
            padding:14px 16px; font-size:12px; color:#fca5a5;
            display:flex; flex-direction:column; gap:8px;
            animation: wd-slideIn 0.3s ease;
        `;
        document.body.appendChild(el);
        // Ajouter l'animation
        const style = document.createElement('style');
        style.textContent = `@keyframes wd-slideIn { from { opacity:0; transform:translateY(20px); } to { opacity:1; transform:translateY(0); } }`;
        document.head.appendChild(style);
    }

    el.style.display = 'flex';
    const sourceLabels = { maps: 'Maps', ads: 'Ads', fb_ads: 'FB Ads', tech: 'E-com', jobs: 'Jobs', bodacc: 'BODACC' };

    el.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center">
            <span style="font-weight:700;color:#ef4444;font-size:13px">⚠ ${failed.length} campagne${failed.length > 1 ? 's' : ''} en erreur</span>
            <button onclick="watchdogDismissFailed()"
                style="background:none;border:none;color:#ef4444;cursor:pointer;font-size:16px;padding:0 2px">✕</button>
        </div>
        ${failed.slice(0, 3).map(f => `
            <div style="background:rgba(239,68,68,0.08);border-radius:8px;padding:8px 10px">
                <div style="font-weight:600;color:#fca5a5;font-size:11px">#${f.id} ${f.nom || 'Sans nom'}
                    <span style="opacity:.6;font-weight:400">${sourceLabels[f.source] || f.source || ''}</span>
                </div>
                <div style="font-size:10px;color:#f87171;margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:320px"
                     title="${(f.error_message || '').replace(/"/g, '&quot;')}">${f.error_message || 'Erreur inconnue'}</div>
            </div>
        `).join('')}
        <button onclick="nav('sources'); watchdogDismissFailed()"
            style="align-self:flex-end;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.3);color:#ef4444;padding:4px 12px;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer">
            Voir dans Sources →
        </button>
    `;
}

// ─── Auto-init au chargement ──────────────────────────────────────────────────

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', watchdogInit);
} else {
    watchdogInit();
}
