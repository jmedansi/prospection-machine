/**
 * dashboard/js/modules/planificateur.js — Planificateur de campagnes
 */

// ─── Chargement de la file d'attente ──────────────────────────────────────────

async function loadPlanning() {
    try {
        const r = await fetch('/api/planning');
        const d = await r.json();
        if (d.error) return;

        const tbody = document.getElementById('tbody-planning');
        if (!tbody) return;

        const items = d.campaigns || [];

        // Mise à jour du badge nav
        const badge = document.getElementById('nav-badge-planning');
        if (badge) badge.textContent = items.filter(i => i.statut === 'planned').length;

        if (items.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;padding:2rem;color:var(--ink3)">Aucune campagne planifiée</td></tr>';
            return;
        }

        tbody.innerHTML = items.map((item, idx) => {
            const statusBadge = _planningStatusBadge(item.statut);
            const safeKeyword = typeof escHtml === 'function' ? escHtml(item.keyword || '') : (item.keyword || '');
            const safeSector  = typeof escHtml === 'function' ? escHtml(item.sector  || '') : (item.sector  || '');
            const safeCity    = typeof escHtml === 'function' ? escHtml(item.city    || '') : (item.city    || '');

            return `
            <tr>
                <td style="color:var(--ink3);font-size:12px">${idx + 1}</td>
                <td><strong>${safeSector}</strong></td>
                <td style="color:var(--ink3)">${safeKeyword}</td>
                <td>${safeCity}</td>
                <td>${item.leads || 50}</td>
                <td>${item.date || '—'}</td>
                <td>${item.heure || '—'}</td>
                <td>${statusBadge}</td>
                <td style="text-align:right;white-space:nowrap">
                    ${item.statut === 'planned' ? `
                    <button class="btn bp1 sm" onclick="launchPlannedNow(${item.id})" title="Lancer maintenant">
                        ▶ Lancer
                    </button>` : ''}
                    <button class="btn bg-error sm" style="margin-left:4px" onclick="deletePlannedCampaign(${item.id})" title="Supprimer">
                        🗑️
                    </button>
                </td>
            </tr>`;
        }).join('');
    } catch (e) {
        console.error('loadPlanning:', e);
    }
}

function _planningStatusBadge(statut) {
    const map = {
        planned:   { bg: 'var(--surface2)',                  color: 'var(--ink3)',    label: 'Planifié'  },
        running:   { bg: 'rgba(249,115,22,0.15)',            color: 'var(--orange)',  label: 'En cours'  },
        done:      { bg: 'rgba(16,185,129,0.15)',            color: 'var(--green)',   label: 'Terminé'   },
        cancelled: { bg: 'rgba(239,68,68,0.15)',             color: 'var(--red)',     label: 'Annulé'    },
    };
    const s = map[statut] || map.planned;
    return `<span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;background:${s.bg};color:${s.color}">${s.label}</span>`;
}

// ─── Ajout d'une campagne planifiée ───────────────────────────────────────────

async function addPlannedCampaign() {
    const sector  = document.getElementById('plan-sector')?.value?.trim()  || '';
    const keyword = document.getElementById('plan-keyword')?.value?.trim() || '';
    const city    = document.getElementById('plan-city')?.value?.trim()    || '';
    const leads   = parseInt(document.getElementById('plan-leads')?.value)  || 50;
    const date    = document.getElementById('plan-date')?.value            || '';
    const heure   = document.getElementById('plan-heure')?.value           || '09:00';

    if (!keyword) { if (typeof showToast === 'function') showToast('Saisir un mot-clé', 'warning'); return; }
    if (!city)    { if (typeof showToast === 'function') showToast('Saisir une ville', 'warning'); return; }
    if (!date)    { if (typeof showToast === 'function') showToast('Choisir une date', 'warning'); return; }

    try {
        const r = await fetch('/api/planning', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sector, keyword, city, leads, date, heure, statut: 'planned' })
        });
        const d = await r.json();
        if (d.error) {
            if (typeof showToast === 'function') showToast('Erreur : ' + d.error, 'error');
            return;
        }
        if (typeof showToast === 'function') showToast('Campagne ajoutée à la file', 'success');
        // Réinitialiser le formulaire
        const cityEl = document.getElementById('plan-city');
        if (cityEl) cityEl.value = '';
        await loadPlanning();
    } catch (e) {
        if (typeof showToast === 'function') showToast('Erreur réseau : ' + e.message, 'error');
    }
}

// ─── Lancer immédiatement ─────────────────────────────────────────────────────

async function launchPlannedNow(id) {
    try {
        const r = await fetch(`/api/planning/${id}/launch`, { method: 'POST' });
        const d = await r.json();
        if (d.error) {
            if (typeof showToast === 'function') showToast('Erreur : ' + d.error, 'error');
            return;
        }
        if (typeof showToast === 'function') showToast('Campagne lancée !', 'success');
        await loadPlanning();
    } catch (e) {
        if (typeof showToast === 'function') showToast('Erreur réseau : ' + e.message, 'error');
    }
}

// ─── Supprimer une campagne planifiée ─────────────────────────────────────────

async function deletePlannedCampaign(id) {
    try {
        const r = await fetch(`/api/planning/${id}`, { method: 'DELETE' });
        if (r.ok) {
            if (typeof showToast === 'function') showToast('Campagne supprimée');
            await loadPlanning();
        } else {
            if (typeof showToast === 'function') showToast('Erreur lors de la suppression', 'error');
        }
    } catch (e) {
        if (typeof showToast === 'function') showToast('Erreur réseau', 'error');
    }
}

// ─── Quota du jour ────────────────────────────────────────────────────────────

async function loadQuota() {
    try {
        const r = await fetch('/api/planning/quota');
        const d = await r.json();
        if (d.error) return;

        const sent  = d.sent  || 0;
        const limit = d.limit || 100;
        const pct   = limit > 0 ? Math.min(100, Math.round(sent * 100 / limit)) : 0;

        const bar  = document.getElementById('quota-progress');
        const text = document.getElementById('quota-text');
        if (bar)  bar.style.width = pct + '%';
        if (text) text.textContent = `${sent} / ${limit}`;

        // Couleur selon remplissage
        if (bar) {
            if (pct >= 90)      bar.style.background = 'var(--red)';
            else if (pct >= 70) bar.style.background = 'var(--orange)';
            else                bar.style.background = 'var(--green)';
        }
    } catch (e) {
        console.error('loadQuota:', e);
    }
}

// ─── Stats par niche ──────────────────────────────────────────────────────────

async function loadNicheStats() {
    try {
        const r = await fetch('/api/planning/niche-stats');
        const d = await r.json();
        if (d.error) return;

        const tbody = document.getElementById('tbody-niche-stats');
        if (!tbody) return;

        const stats = d.stats || [];
        if (stats.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:1.5rem;color:var(--ink3)">Aucune donnée disponible</td></tr>';
            return;
        }

        tbody.innerHTML = stats.map(s => {
            const taux = s.emails_envoyes > 0
                ? Math.round(s.nb_reponses * 100 / s.emails_envoyes) + '%'
                : '—';
            const safeNiche = typeof escHtml === 'function' ? escHtml(s.niche || '') : (s.niche || '');
            return `
            <tr>
                <td><strong>${safeNiche}</strong></td>
                <td>${s.campagnes || 0}</td>
                <td>${s.leads_scrapes || 0}</td>
                <td>${s.emails_envoyes || 0}</td>
                <td><span style="font-weight:600;color:${s.nb_reponses > 0 ? 'var(--green)' : 'var(--ink3)'}">${taux}</span></td>
            </tr>`;
        }).join('');
    } catch (e) {
        console.error('loadNicheStats:', e);
    }
}

// ─── Changement de secteur dans le formulaire planning ────────────────────────

function onPlanSectorChange(sel) {
    const kw     = sel.options[sel.selectedIndex]?.dataset?.kw || '';
    const kwInput = document.getElementById('plan-keyword');
    if (!kwInput) return;
    if (kw) kwInput.value = kw;
    kwInput.readOnly = (sel.value !== 'Autre' && kw !== '');
}

// ─── Initialisation ───────────────────────────────────────────────────────────

async function initPlanificateur() {
    // Valeur par défaut : aujourd'hui
    const today = new Date().toISOString().split('T')[0];
    const dateEl = document.getElementById('plan-date');
    if (dateEl && !dateEl.value) dateEl.value = today;

    await Promise.all([loadPlanning(), loadQuota(), loadNicheStats()]);
}
