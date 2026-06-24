/**
 * dashboard/js/modules/sniper.js — Module Sniper B2B
 *
 * Sources : ads · tech · jobs · bodacc
 * Dépend de : /api/sniper/*
 */

let _sniperPollInterval = null;

// ─── Init ────────────────────────────────────────────────────────────────────

function sniperInit() {
    if (typeof window.unifiedLeadsLoadLists === 'function') {
        window.unifiedLeadsLoadLists();
    }
    sniperLoadStats();
    sniperLoadLeads();
    sniperLoadStatus();
    _sniperLoadSettings();
    _sniperStartPollIfRunning();
}

// ─── Stats cards ──────────────────────────────────────────────────────────────

async function sniperLoadStats() {
    try {
        const r = await fetch('/api/sniper/stats');
        const d = await r.json();
        if (d.error) return;

        const set = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = (val ?? '—');
        };

        set('sniper-stat-leads',    d.total_leads    || 0);
        set('sniper-stat-emails',   d.emails_generes || 0);
        set('sniper-stat-envoyes',  d.step1_envoyes  || 0);
        set('sniper-stat-reponses', d.reponses       || 0);
        set('sniper-stat-step2',    d.step2_livres   || 0);
        set('sniper-stat-quota',    d.quota_remaining != null ? `${d.quota_remaining}/${d.daily_quota}` : '—');

        const src = d.by_source || {};
        set('sniper-src-ads',          src.ads          || 0);
        set('sniper-src-fb-ads',       src.fb_ads       || 0);
        set('sniper-src-transparency', src.transparency || 0);
        set('sniper-src-ecom',         (src.ecom || 0) + (src.tech || 0));  // tech = legacy
        set('sniper-src-jobs',   src.jobs   || 0);
        set('sniper-src-bodacc', src.bodacc || 0);

        const badge = document.getElementById('sniper-badge-replies');
        if (badge) {
            const replies = parseInt(d.reponses || 0);
            badge.textContent = replies;
            badge.style.display = replies > 0 ? 'inline-flex' : 'none';
        }
    } catch (e) {
        console.error('[sniper] stats error', e);
    }
}

// ─── Table leads ──────────────────────────────────────────────────────────────

async function sniperLoadLeads() {
    const tbody = document.getElementById('sniper-leads-tbody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:24px;color:var(--ink3)">Chargement…</td></tr>';

    try {
        const list_id = document.getElementById('sniper-filter-list')?.value || '';
        const source  = document.getElementById('sniper-filter-source')?.value  || '';
        const statut  = document.getElementById('sniper-filter-statut')?.value  || '';
        const tag     = document.getElementById('sniper-filter-tag')?.value     || '';
        const contact = document.getElementById('sniper-filter-contact')?.value || '';

        const params = new URLSearchParams({ limit: 200 });
        if (list_id) params.set('list_id', list_id);
        if (source)  params.set('source', source);
        if (statut)  params.set('statut_prospection', statut);
        if (tag)     params.set('tag_urgence', tag);
        if (contact) params.set('contact', contact);

        const r = await fetch(`/api/sniper/leads?${params}`);
        const d = await r.json();

        const countEl = document.getElementById('sniper-leads-count');
        if (countEl) countEl.textContent = d.total ? `${d.total} leads` : '';

        if (!d.leads || d.leads.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:24px;color:var(--ink3)">Aucun lead Sniper</td></tr>';
            return;
        }

        tbody.innerHTML = d.leads.map(lead => {
            const nom   = _sEsc(lead.nom      || '');
            const site  = _sEsc(lead.site_web || '');
            const ceo   = [lead.ceo_prenom, lead.ceo_nom].filter(Boolean).map(_sEsc).join(' ') || '<span style="color:var(--ink3)">—</span>';
            const email = (lead.email_valide && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(lead.email_valide)) ? lead.email_valide : (lead.email || '');
            const score = lead.mobile_score ? `${lead.mobile_score}/100` : '—';
            const scoreColor = !lead.mobile_score ? 'var(--ink3)' : lead.mobile_score < 50 ? 'var(--error)' : lead.mobile_score < 70 ? 'var(--orange)' : 'var(--green)';
            const contactBadge = _sContactBadge(email, lead.is_catch_all);

            return `<tr style="cursor:pointer" onclick="sniperOpenPanel(${lead.id})" title="Voir le détail">
                <td><span style="color:var(--ink1);font-weight:500">${nom.slice(0,22)}${nom.length>22?'…':''}</span><br><span style="font-size:10px;color:var(--ink3)">${site.replace(/^https?:\/\//,'').slice(0,25)}</span></td>
                <td>${_sSourceBadge(lead.source)}</td>
                <td style="font-size:12px">${ceo}</td>
                <td style="font-size:12px">${contactBadge}</td>
                <td>${_sTagBadge(lead.tag_urgence)}</td>
                <td style="font-size:13px;font-weight:700;color:${scoreColor}">${score}</td>
                <td>${_sStatutBadge(lead.statut_prospection)}</td>
                <td onclick="event.stopPropagation()">${_sActions(lead)}</td>
            </tr>`;
        }).join('');

    } catch (e) {
        console.error('[sniper] leads error', e);
        if (tbody) tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--error)">Erreur de chargement</td></tr>';
    }
}

// ─── Log pipeline ─────────────────────────────────────────────────────────────

async function sniperLoadStatus() {
    const logEl = document.getElementById('sniper-log');
    if (!logEl) return;
    try {
        const [s1, s2, s3, s4, s5] = await Promise.all([
            fetch('/api/sniper/status').then(r => r.json()).catch(() => ({})),
            fetch('/api/sniper/ecom-status').then(r => r.json()).catch(() => ({})),
            fetch('/api/sniper/jobs-status').then(r => r.json()).catch(() => ({})),
            fetch('/api/sniper/fb-ads-status').then(r => r.json()).catch(() => ({})),
            fetch('/api/sniper/transparency-status').then(r => r.json()).catch(() => ({})),
        ]);

        // Indicateurs "en cours" sur les cartes source
        _sSetRunningIndicator('sniper-btn-ads',          s1.running);
        _sSetRunningIndicator('sniper-btn-ecom',         s2.running);
        _sSetRunningIndicator('sniper-btn-jobs',         s3.running);
        _sSetRunningIndicator('sniper-btn-fb-ads',       s4.running);
        _sSetRunningIndicator('sniper-btn-transparency', s5.running);

        const anyRunning = s1.running || s2.running || s3.running || s4.running || s5.running;
        document.getElementById('sniper-running-badge')?.style && (
            document.getElementById('sniper-running-badge').style.display = anyRunning ? 'inline-flex' : 'none'
        );

        // Compteurs live
        const liveEl = document.getElementById('sniper-live-counters');
        if (liveEl) {
            const active = [s1, s2, s3, s4, s5].find(s => s.running);
            if (active) {
                liveEl.style.display = 'flex';
                const phaseLabels = {
                    extraction: 'Extraction', pre_filter: 'Pré-filtre',
                    enrichissement: 'Enrichissement', enrichissement_contact: 'Contact',
                    scoring: 'Scoring', generation: 'Génération emails', done: 'Terminé',
                };
                document.getElementById('sniper-live-kw').textContent      = active.current_kw || '—';
                document.getElementById('sniper-live-total').textContent    = active.total || 0;
                document.getElementById('sniper-live-accepted').textContent = active.accepted || 0;
                document.getElementById('sniper-live-emails').textContent   = active.emails_generes || 0;
                document.getElementById('sniper-live-phase').textContent    = phaseLabels[active.phase] || active.phase || '—';
            } else {
                liveEl.style.display = 'none';
            }
        }

        // Logs : dernier pipeline actif en priorité
        const activeLog = [s1, s2, s3, s4, s5].find(s => s.running) || s1;
        const logs = (activeLog.logs || []).slice(-30);
        if (logs.length === 0) {
            logEl.textContent = 'Aucun log récent.';
            return;
        }
        logEl.innerHTML = logs.map(l => {
            const color = l.includes('✓') || l.includes('OK') || l.includes('inséré') ? 'var(--green)'
                        : l.includes('✗') || l.includes('Erreur') || l.includes('error') ? 'var(--error)'
                        : l.includes('⚠') || l.includes('ignoré') ? 'var(--orange)'
                        : 'inherit';
            return `<div style="color:${color}">${_sEsc(l)}</div>`;
        }).join('');
        logEl.scrollTop = logEl.scrollHeight;

        return { anyRunning };
    } catch (e) {
        console.error('[sniper] status error', e);
    }
}

function _sSetRunningIndicator(btnId, running) {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    if (running) {
        btn.textContent = '⏳ En cours';
        btn.disabled = true;
        btn.style.opacity = '0.7';
    } else {
        // Restore original label based on button id
        const labels = { 'sniper-btn-ads': 'Lancer', 'sniper-btn-fb-ads': 'Lancer', 'sniper-btn-ecom': 'Lancer', 'sniper-btn-jobs': 'Lancer', 'sniper-btn-bodacc': 'Scanner' };
        btn.textContent = labels[btnId] || 'Lancer';
        btn.disabled = false;
        btn.style.opacity = '';
    }
}

// ─── Auto-poll quand un pipeline tourne ───────────────────────────────────────

async function _sniperStartPollIfRunning() {
    const statuses = await Promise.all([
        fetch('/api/sniper/status').then(r => r.json()).catch(() => ({})),
        fetch('/api/sniper/ecom-status').then(r => r.json()).catch(() => ({})),
        fetch('/api/sniper/jobs-status').then(r => r.json()).catch(() => ({})),
        fetch('/api/sniper/fb-ads-status').then(r => r.json()).catch(() => ({})),
        fetch('/api/sniper/transparency-status').then(r => r.json()).catch(() => ({})),
    ]);
    if (statuses.some(s => s.running)) _sniperPollStatus();
}

function _sniperPollStatus() {
    if (_sniperPollInterval) return;
    _sniperPollInterval = setInterval(async () => {
        const result = await sniperLoadStatus();
        if (!result?.anyRunning) {
            clearInterval(_sniperPollInterval);
            _sniperPollInterval = null;
            sniperLoadStats();
            sniperLoadLeads();
            if (typeof showToast === 'function') showToast('Pipeline terminé', 'success');
        }
    }, 3000);
}

// ─── Actions ──────────────────────────────────────────────────────────────────

async function sniperGenerateEmails() {
    if (typeof showConfirm === 'function') {
        const ok = await showConfirm('Générer les emails Sniper pour tous les leads sans email ?', { title: 'Générer emails', confirmText: 'Générer' });
        if (!ok) return;
    } else if (!confirm('Générer les emails Sniper ?')) return;

    const btn = document.querySelector('[onclick="sniperGenerateEmails()"]');
    const originalText = btn ? btn.textContent : 'Générer emails';
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Envoi…'; }
    
    try {
        const r = await fetch('/api/sniper/generate-emails', { method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}' });
        const d = await r.json();
        if (d.error) { 
            showToast('Erreur : ' + d.error, 'error'); 
            if (btn) { btn.disabled = false; btn.textContent = originalText; }
            return; 
        }
        
        const taskId = d.task_id;
        if (btn) btn.textContent = '⏳ Travail…';
        
        // Polling
        const poll = setInterval(async () => {
            try {
                const res = await fetch(`/api/tasks/status/${taskId}`);
                const status = await res.json();
                
                if (status.status === 'done') {
                    clearInterval(poll);
                    const res_data = status.result || {};
                    showToast(`${res_data.success || 0} emails générés · ${res_data.skipped || 0} ignorés · ${res_data.failed || 0} erreurs`, 'success');
                    sniperInit();
                    if (btn) { btn.disabled = false; btn.textContent = originalText; }
                } else if (status.status === 'failed') {
                    clearInterval(poll);
                    showToast('Erreur : ' + (status.error || 'inconnue'), 'error');
                    if (btn) { btn.disabled = false; btn.textContent = originalText; }
                }
            } catch (e) {
                console.error('[sniper] poll error', e);
            }
        }, 2000);
        
    } catch (e) {
        showToast('Erreur réseau', 'error');
        if (btn) { btn.disabled = false; btn.textContent = originalText; }
    }
}

async function sniperPollImap() {
    const btn = document.querySelector('[onclick="sniperPollImap()"]');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Vérification…'; }
    try {
        const r = await fetch('/api/sniper/poll-imap', { method: 'POST', headers: {'Content-Type':'application/json'}, body: '{"hours":48}' });
        const d = await r.json();
        if (d.error) { showToast('Erreur : ' + d.error, 'error'); return; }
        showToast(`IMAP : ${d.matched || 0} réponse(s) détectée(s)`, d.matched > 0 ? 'success' : 'info');
        sniperInit();
    } catch (e) {
        showToast('Erreur réseau', 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Vérifier réponses'; }
    }
}

async function sniperSendStep2(auditId) {
    const ok = typeof showConfirm === 'function'
        ? await showConfirm(`Envoyer le rapport (step 2) pour le lead #${auditId} ?`, { title: 'Step 2', confirmText: 'Envoyer' })
        : confirm(`Envoyer l'email step 2 pour le lead #${auditId} ?`);
    if (!ok) return;
    try {
        const r = await fetch('/api/sniper/send-step2', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ audit_id: auditId }),
        });
        const d = await r.json();
        if (d.ok) {
            showToast('Step 2 envoyé !', 'success');
            sniperInit();
        } else {
            showToast('Erreur : ' + (d.message || d.error || 'inconnue'), 'error');
        }
    } catch (e) {
        showToast('Erreur réseau', 'error');
    }
}

async function sniperSendStep1() {
    const quotaText = document.getElementById('sniper-stat-quota')?.textContent || '';
    const remaining = quotaText.split('/')[0] || '?';
    const ok = typeof showConfirm === 'function'
        ? await showConfirm(`Envoyer les step 1 dans la limite du quota (${remaining} restants aujourd'hui) ?`, { title: 'Envoyer Step 1', confirmText: 'Envoyer' })
        : confirm(`Envoyer les step 1 Sniper ? (${remaining} restants)`);
    if (!ok) return;

    const btn = document.querySelector('[onclick="sniperSendStep1()"]');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Envoi…'; }
    try {
        const r = await fetch('/api/sniper/send-step1', { method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}' });
        const d = await r.json();
        if (d.error) { showToast('Erreur : ' + d.error, 'error'); return; }
        if (d.message) { showToast(d.message, 'info'); return; }
        showToast(`Envoi : ${d.success || 0} succès · ${d.failed || 0} échecs`, 'success');
        sniperInit();
    } catch (e) {
        showToast('Erreur réseau', 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Envoyer step 1'; }
    }
}

async function sniperLaunchTech() {
    const vals = await _sniperInputModal('Lancer TechScraper', [
        { id: 'naf',  label: 'Codes NAF (virgule)', placeholder: 'Laisser vide = 18 codes par défaut' },
        { id: 'max',  label: 'Max leads',            placeholder: '50', value: '50', type: 'number' },
    ]);
    if (!vals) return;
    const btn = document.getElementById('sniper-btn-ecom');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ En cours'; }
    try {
        const body = { max_leads: parseInt(vals.max) || 50 };
        if (vals.naf.trim()) body.naf_codes = vals.naf.split(',').map(k => k.trim()).filter(Boolean);
        const r = await fetch('/api/sniper/ecom-scan', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
        const d = await r.json();
        if (d.error || !d.ok) { showToast('Erreur : ' + (d.error || d.message), 'error'); return; }
        showToast('TechScraper lancé', 'success');
        _sniperPollStatus();
        sniperLoadStatus();
    } catch (e) { showToast('Erreur réseau', 'error'); }
}

async function sniperLaunchJobs() {
    const vals = await _sniperInputModal('Lancer JobsScraper', [
        { id: 'kw',  label: 'Mots-clés RH (virgule)', placeholder: 'Laisser vide = 12 mots-clés par défaut' },
        { id: 'max', label: 'Max leads',               placeholder: '50', value: '50', type: 'number' },
    ]);
    if (!vals) return;
    const btn = document.getElementById('sniper-btn-jobs');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ En cours'; }
    try {
        const body = { max_leads: parseInt(vals.max) || 50, days_back: 7 };
        if (vals.kw.trim()) body.keywords = vals.kw.split(',').map(k => k.trim()).filter(Boolean);
        const r = await fetch('/api/sniper/jobs-scan', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
        const d = await r.json();
        if (d.error || !d.ok) { showToast('Erreur : ' + (d.error || d.message), 'error'); return; }
        showToast('JobsScraper lancé', 'success');
        _sniperPollStatus();
        sniperLoadStatus();
    } catch (e) { showToast('Erreur réseau', 'error'); }
}

async function sniperLaunchBodacc() {
    const vals = await _sniperInputModal('Scanner BODACC', [
        { id: 'date', label: 'Date (YYYY-MM-DD)', placeholder: 'Laisser vide = hier' },
    ]);
    if (!vals) return;
    const btn = document.getElementById('sniper-btn-bodacc');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Scan…'; }
    try {
        const body = vals.date.trim() ? { date: vals.date.trim() } : {};
        const r = await fetch('/api/sniper/bodacc-scan', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
        const d = await r.json();
        if (d.error) { showToast('Erreur : ' + d.error, 'error'); return; }
        showToast(`BODACC ${d.date} : ${d.inserted || 0} insérés · ${d.filtered || 0} filtrés`, 'success');
        sniperInit();
    } catch (e) {
        showToast('Erreur réseau', 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Scanner'; }
    }
}

async function sniperLaunchFbAds() {
    const vals = await _sniperInputModal('Lancer FB Ads (Meta Ad Library)', [
        { id: 'kw',      label: 'Mots-clés (virgule)',  placeholder: 'ex: restaurant, boutique mode', required: true },
        { id: 'country', label: 'Pays (ISO)',            placeholder: 'FR', value: 'FR' },
        { id: 'pages',   label: 'Max pages de résultats', placeholder: '5', value: '5', type: 'number' },
    ]);
    if (!vals || !vals.kw.trim()) { showToast('Mots-clés requis', 'warning'); return; }
    const btn = document.getElementById('sniper-btn-fb-ads');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ En cours'; }
    try {
        const body = {
            search_terms: vals.kw.split(',').map(k => k.trim()).filter(Boolean),
            country:      (vals.country || 'FR').toUpperCase(),
            max_pages:    parseInt(vals.pages) || 5,
        };
        const r = await fetch('/api/sniper/fb-ads-scan', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify(body),
        });
        const d = await r.json();
        if (d.error || !d.ok) { showToast('Erreur : ' + (d.error || d.message), 'error'); return; }
        showToast('FB Ads pipeline lancé', 'success');
        _sniperPollStatus();
        sniperLoadStatus();
    } catch (e) {
        showToast('Erreur réseau', 'error');
    }
}

async function sniperLaunchTransparency() {
    const vals = await _sniperInputModal('Lancer Google Ads Transparency', [
        { id: 'kw',     label: 'Mots-clés (virgule)',      placeholder: 'ex: serrurier paris, agence web lyon', required: true },
        { id: 'country',label: 'Pays (ISO)',                placeholder: 'FR', value: 'FR' },
        { id: 'max',    label: 'Max annonceurs / mot-clé', placeholder: '20', value: '20', type: 'number' },
    ]);
    if (!vals || !vals.kw.trim()) { showToast('Mots-clés requis', 'warning'); return; }
    const btn = document.getElementById('sniper-btn-transparency');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ En cours'; }
    try {
        const body = {
            keywords:   vals.kw.split(',').map(k => k.trim()).filter(Boolean),
            country:    (vals.country || 'FR').toUpperCase(),
            max_per_kw: parseInt(vals.max) || 20,
        };
        const r = await fetch('/api/sniper/transparency-scan', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify(body),
        });
        const d = await r.json();
        if (d.error) { showToast('Erreur : ' + d.error, 'error'); if (btn) { btn.disabled = false; btn.textContent = 'Lancer'; } return; }
        showToast('Google Transparency lancé', 'success');
        _sniperPollStatus();
        sniperLoadStatus();
    } catch (e) {
        showToast('Erreur réseau', 'error');
        if (btn) { btn.disabled = false; btn.textContent = 'Lancer'; }
    }
}

async function sniperToggleAutoScrape(enabled) {
    try {
        await fetch('/api/sniper/settings', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ sniper_ads_auto_scrape: enabled ? '1' : '0' }),
        });
        showToast(enabled ? 'Ads auto activé (9h chaque jour)' : 'Ads auto désactivé', 'success');
    } catch (e) {
        showToast('Erreur réseau', 'error');
    }
}

async function sniperToggleEcomScrape(enabled) {
    try {
        await fetch('/api/sniper/settings', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ sniper_ecom_auto_scrape: enabled ? '1' : '0' }),
        });
        showToast(enabled ? 'E-com auto activé (9h30 chaque jour)' : 'E-com auto désactivé', 'success');
    } catch (e) {
        showToast('Erreur réseau', 'error');
    }
}

async function sniperToggleMapsTopup(enabled) {
    try {
        await fetch('/api/sniper/settings', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ sniper_maps_topup_enabled: enabled ? '1' : '0' }),
        });
        showToast(enabled ? 'Maps Top-up auto activé' : 'Maps Top-up auto désactivé', 'success');
    } catch (e) {
        showToast('Erreur réseau', 'error');
    }
}

async function _sniperLoadSettings() {
    try {
        const d = await fetch('/api/sniper/settings').then(r => r.json());
        const cbAds = document.getElementById('sniper-auto-scrape-toggle');
        if (cbAds) cbAds.checked = d.sniper_ads_auto_scrape === '1';
        
        const cbAdsAuto = document.getElementById('src-toggle-ads-auto');
        if (cbAdsAuto) cbAdsAuto.checked = d.sniper_ads_auto_scrape === '1';

        const cbEcom = document.getElementById('sniper-ecom-scrape-toggle');
        if (cbEcom) cbEcom.checked = d.sniper_ecom_auto_scrape === '1';

        const cbEcomAuto = document.getElementById('src-toggle-ecom-auto');
        if (cbEcomAuto) cbEcomAuto.checked = d.sniper_ecom_auto_scrape === '1';

        const cbMapsTopup = document.getElementById('src-toggle-maps-auto');
        if (cbMapsTopup) cbMapsTopup.checked = d.sniper_maps_topup_enabled !== '0'; // default true
    } catch {}
}

async function sniperSetQuota() {
    const current = document.getElementById('sniper-stat-quota')?.textContent || '';
    const match = current.match(/\d+\/(\d+)/);
    const vals = await _sniperInputModal('Quota quotidien Sniper', [
        { id: 'quota', label: 'Emails par jour', placeholder: '20', value: match ? match[1] : '20', type: 'number' },
    ]);
    if (!vals) return;
    try {
        await fetch('/api/sniper/set-quota', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ daily_quota: parseInt(vals.quota) || 20 }),
        });
        showToast(`Quota mis à jour : ${vals.quota}/jour`, 'success');
        sniperLoadStats();
    } catch (e) { showToast('Erreur réseau', 'error'); }
}

async function showSniperLaunchModal() {
    const vals = await _sniperInputModal('Lancer Sniper Ads (Google)', [
        {
            id: 'sector',
            label: 'Niche / Secteur',
            type: 'select',
            value: 'artisan',
            options: [
                {value: 'artisan', label: 'Artisans / BTP'},
                {value: 'sante', label: 'Santé / Médical'},
                {value: 'juridique', label: 'Juridique / Finance'},
                {value: 'immobilier', label: 'Immobilier'},
                {value: 'beaute', label: 'Beauté / Bien-être'},
                {value: 'auto', label: 'Auto / Moto'},
                {value: 'sport', label: 'Sport / Loisirs'},
                {value: 'numerique', label: 'Numérique / Web'},
                {value: 'commerce', label: 'Commerce / Boutique'},
                {value: 'hotellerie', label: 'Hôtellerie / Restauration'}
            ]
        },
        { id: 'kw', label: 'Mot-clé métier', placeholder: 'ex: plombier, avocat', required: true },
        { id: 'city', label: 'Ville', placeholder: 'ex: Paris, Lyon', required: true },
        { id: 'country', label: 'Pays (ISO)', value: 'fr', placeholder: 'fr' }
    ]);

    if (!vals || !vals.kw.trim() || !vals.city.trim()) return;

    // Le backend Sniper Ads (via sniperLaunchPipeline) attend juste un champ `keywords`
    // On va donc lui passer [ "Mot-clé Ville" ] pour reproduire le comportement manuel
    const kwStr = `${vals.kw.trim()} ${vals.city.trim()}`;
    sniperLaunchPipeline([kwStr], vals.country || 'fr');
}

async function sniperLaunchTodayBatch() {
    try {
        const d = await fetch('/api/sniper/daily-batch').then(r => r.json());
        if (!d.keywords || !d.keywords.length) { showToast('Batch du jour vide', 'warning'); return; }
        const confirmed = confirm(`Lancer le batch du jour ?\n\n${d.keywords.join('\n')}\n\n${d.keywords.length} mots-clés · toutes pages`);
        if (!confirmed) return;
        sniperLaunchPipeline(d.keywords, 'fr');
    } catch (e) {
        showToast('Erreur réseau', 'error');
    }
}

async function sniperLaunchPipeline(keywords, country) {
    const btn = document.getElementById('sniper-btn-ads');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Lancement…'; }
    try {
        const r = await fetch('/api/sniper/launch', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ keywords, country }),
        });
        const d = await r.json();
        if (d.error) { showToast('Erreur : ' + d.error, 'error'); if (btn) { btn.disabled = false; btn.textContent = 'Lancer'; } return; }
        showToast(`Pipeline Ads lancé — ${keywords.length} mots-clés, toutes pages`, 'success');
        _sniperPollStatus();
        sniperLoadStatus();
    } catch (e) {
        showToast('Erreur réseau', 'error');
        if (btn) { btn.disabled = false; btn.textContent = 'Lancer'; }
    }
}

// ─── Modal générique à champs texte (remplace prompt()) ───────────────────────

function _sniperInputModal(title, fields) {
    return new Promise(resolve => {
        let m = document.getElementById('_sniper-input-modal');
        if (m) m.remove();

        const fieldsHtml = fields.map(f => {
            const commonStyle = 'width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:7px;background:var(--surface);color:var(--ink);font-size:13px;box-sizing:border-box';
            let input = '';
            if (f.type === 'textarea') {
                input = `<textarea id="_sinput-${f.id}" placeholder="${f.placeholder || ''}" rows="4" style="${commonStyle};resize:vertical">${f.value || ''}</textarea>`;
            } else if (f.type === 'select') {
                const optionsHtml = (f.options || []).map(o => `<option value="${o.value}" ${o.value === f.value ? 'selected' : ''}>${o.label}</option>`).join('');
                input = `<select id="_sinput-${f.id}" style="${commonStyle}">${optionsHtml}</select>`;
            } else {
                input = `<input id="_sinput-${f.id}" type="${f.type || 'text'}" placeholder="${f.placeholder || ''}" value="${f.value || ''}" style="${commonStyle}">`;
            }
            return `<div style="margin-bottom:14px">
                <label style="font-size:12px;color:var(--ink3);font-weight:600;display:block;margin-bottom:5px">${f.label}</label>
                ${input}
            </div>`;
        }).join('');

        m = document.createElement('div');
        m.id = '_sniper-input-modal';
        m.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.55);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center';
        m.innerHTML = `
            <div style="background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:26px;width:360px;max-width:90vw;box-shadow:0 24px 48px rgba(0,0,0,0.35)">
                <div style="font-size:15px;font-weight:700;margin-bottom:18px">${title}</div>
                ${fieldsHtml}
                <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:6px">
                    <button id="_sinput-cancel" style="padding:8px 18px;border-radius:8px;border:1px solid var(--border);background:transparent;color:var(--ink2);font-size:13px;cursor:pointer">Annuler</button>
                    <button id="_sinput-ok" style="padding:8px 20px;border-radius:8px;border:none;background:var(--accent,#3b82f6);color:#fff;font-size:13px;font-weight:600;cursor:pointer">Lancer</button>
                </div>
            </div>`;
        document.body.appendChild(m);

        const close = (val) => { m.remove(); resolve(val); };

        m.querySelector('#_sinput-cancel').onclick = () => close(null);
        m.onclick = e => { if (e.target === m) close(null); };
        m.querySelector('#_sinput-ok').onclick = () => {
            const result = {};
            fields.forEach(f => { result[f.id] = (m.querySelector(`#_sinput-${f.id}`)?.value || '').trim(); });
            close(result);
        };

        m.addEventListener('keydown', e => {
            // Entrée soumet sauf si le focus est dans une textarea
            if (e.key === 'Enter' && e.target.tagName !== 'TEXTAREA') m.querySelector('#_sinput-ok').click();
            if (e.key === 'Escape') close(null);
        });

        // Focus sur le premier champ
        setTimeout(() => (m.querySelector('textarea') || m.querySelector('input'))?.focus(), 50);
    });
}


// ─── Helpers UI ───────────────────────────────────────────────────────────────

function _sEsc(str) {
    return String(str)
        .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function _sSourceBadge(source) {
    const map = { ads:['#f97316','Ads'], fb_ads:['#1877f2','FB Ads'], transparency:['#4285f4','Google'], ecom:['#8b5cf6','E-COM'], tech:['#8b5cf6','E-COM'], jobs:['#06b6d4','Jobs'], bodacc:['#10b981','BODACC'] };
    const [color, label] = map[source] || ['#9ca3af', source || '?'];
    return `<span style="background:${color}20;color:${color};padding:2px 7px;border-radius:10px;font-size:10px;font-weight:700;letter-spacing:.04em">${label}</span>`;
}

function _sTagBadge(tag) {
    const map = { perf:['#3b82f6','Perf mobile'], securite:['#f59e0b','Sécurité'], 'perf+securite':['#ef4444','2 impacts'], creation:['#10b981','Création site'] };
    const [color, label] = map[tag] || ['#9ca3af', tag || '—'];
    if (!tag) return `<span style="color:var(--ink3);font-size:11px">—</span>`;
    return `<span style="background:${color}20;color:${color};padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700">${label}</span>`;
}

function _sStatutBadge(statut) {
    const map = {
        en_attente:      ['#9ca3af','À traiter'],
        a_contacter:     ['#6b7280','À contacter'],
        step1_envoye:    ['#3b82f6','Step 1 envoyé'],
        repondu:         ['#f59e0b','Répondu ✉'],
        lien_envoye:     ['#10b981','Rapport livré'],
        linkedin_envoye: ['#0077b5','LinkedIn'],
    };
    const [color, label] = map[statut] || ['#9ca3af', statut || '?'];
    return `<span style="background:${color}20;color:${color};padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600">${label}</span>`;
}

function _sContactBadge(email, isCatchAll) {
    if (!email) return `<span style="background:#ef444420;color:#ef4444;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:700">❌ Sans email</span>`;
    if (isCatchAll) return `<span style="background:#f59e0b20;color:#f59e0b;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:700" title="${_sEsc(email)}">⚠️ Catch-all</span>`;
    return `<span style="background:#10b98120;color:#10b981;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:700" title="${_sEsc(email)}">✅ ${_sEsc(email).slice(0,20)}</span>`;
}

// ─── Panel détail lead ────────────────────────────────────────────────────────

async function sniperOpenPanel(leadId) {
    const panel = document.getElementById('sniper-lead-panel');
    const body  = document.getElementById('sniper-panel-body');
    if (!panel || !body) return;

    panel.style.display = 'block';
    const overlay = document.getElementById('sniper-lead-panel-overlay');
    if (overlay) overlay.style.display = 'block';
    body.innerHTML = '<div style="color:var(--ink3);padding:20px 0">Chargement…</div>';

    try {
        const d = await fetch(`/api/sniper/lead/${leadId}`).then(r => r.json());
        if (d.error) { body.innerHTML = `<p style="color:var(--error)">${d.error}</p>`; return; }

        document.getElementById('sniper-panel-title').textContent = d.nom || `Lead #${leadId}`;

        const score = (label, val, max=100, warn=50, ok=70) => {
            if (val == null) return '';
            const color = val < warn ? '#ef4444' : val < ok ? '#f59e0b' : '#10b981';
            return `<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--border)">
                <span style="font-size:12px;color:var(--ink3)">${label}</span>
                <span style="font-size:13px;font-weight:700;color:${color}">${val}/${max}</span>
            </div>`;
        };
        const row = (label, val, mono=false) => {
            if (!val && val !== 0) return '';
            return `<div style="display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px solid var(--border)">
                <span style="font-size:12px;color:var(--ink3);flex-shrink:0">${label}</span>
                <span style="font-size:12px;text-align:right;${mono?'font-family:monospace':''};word-break:break-all">${_sEsc(String(val))}</span>
            </div>`;
        };
        const section = (title) => `<div style="font-size:11px;font-weight:700;color:var(--ink3);letter-spacing:.06em;margin:16px 0 6px;text-transform:uppercase">${title}</div>`;

        // Politique de contact
        let contactHtml = '';
        const hasEmail  = d.email_valide_audit && d.email_valide_audit !== '';
        const catchAll  = d.is_catch_all;
        const hasPhone  = d.telephone && d.telephone !== '';
        if (hasEmail && !catchAll)  contactHtml = `<div style="background:#10b98115;color:#10b981;padding:8px 12px;border-radius:8px;font-size:12px;font-weight:600;margin-bottom:12px">✅ Email valide — Envoi step 1 possible</div>`;
        else if (catchAll)          contactHtml = `<div style="background:#f59e0b15;color:#f59e0b;padding:8px 12px;border-radius:8px;font-size:12px;font-weight:600;margin-bottom:12px">⚠️ Catch-all — Bascule LinkedIn automatique</div>`;
        else if (hasPhone)          contactHtml = `<div style="background:#3b82f615;color:#3b82f6;padding:8px 12px;border-radius:8px;font-size:12px;font-weight:600;margin-bottom:12px">📞 Pas d'email — Contacter par téléphone</div>`;
        else                        contactHtml = `<div style="background:#ef444415;color:#ef4444;padding:8px 12px;border-radius:8px;font-size:12px;font-weight:600;margin-bottom:12px">❌ Aucun contact trouvé — Formulaire site ou LinkedIn manuel</div>`;

        const ratingHtml = d.rating ? (() => {
            const stars = Math.round(d.rating);
            const starsStr = '★'.repeat(stars) + '☆'.repeat(5 - stars);
            return `<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--border)">
                <span style="font-size:12px;color:var(--ink3)">Note Google</span>
                <span style="font-size:12px;font-weight:700">${starsStr} ${d.rating}/5${d.nb_avis ? ` (${d.nb_avis} avis)` : ''}</span>
            </div>`;
        })() : '';

        body.innerHTML = `
            ${contactHtml}
            ${section('Identité')}
            ${row('Nom / Entreprise', d.nom)}
            ${row('Adresse', d.adresse)}
            ${row('Ville', d.ville)}
            ${row('Catégorie', d.category)}
            ${row('Mot-clé', d.mot_cle)}
            ${row('Source', d.source)}
            ${ratingHtml}
            ${row('Scraping', d.date_scraping ? d.date_scraping.slice(0,10) : null)}
            ${section('Site web')}
            ${d.site_web ? `<div style="padding:6px 0;border-bottom:1px solid var(--border)"><a href="${_sEsc(d.site_web)}" target="_blank" style="font-size:12px;color:var(--accent);word-break:break-all">${_sEsc(d.site_web)}</a></div>` : ''}
            ${row('CMS détecté', d.cms_detected)}
            ${row('LCP (ms)', d.lcp_ms)}
            ${d.lien_maps ? `<div style="padding:6px 0;border-bottom:1px solid var(--border)"><a href="${_sEsc(d.lien_maps)}" target="_blank" style="font-size:12px;color:var(--ink3)">&#x1F4CD; Voir sur Google Maps</a></div>` : ''}
            ${section('Scores')}
            ${score('Mobile', d.mobile_score)}
            ${score('Desktop', d.desktop_score)}
            ${score('Performance', d.score_performance)}
            ${score('SEO', d.score_seo)}
            ${score('Score urgence', d.score_urgence, 10, 3, 6)}
            ${row('Tag urgence', d.tag_urgence)}
            ${row('Problème principal', d.probleme_principal)}
            ${row('Service suggéré', d.service_suggere)}
            ${section('Contact')}
            ${row('Gérant (scraping)', [d.prenom_gerant, d.nom_gerant].filter(Boolean).join(' '))}
            ${row('CEO (enrichi)', [d.ceo_prenom, d.ceo_nom].filter(Boolean).join(' '))}
            ${row('Email validé', d.email_valide_audit)}
            ${row('Email brut', d.email)}
            ${d.email_2 ? `<div style="display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px;color:var(--ink3);flex-shrink:0">Email 2</span><a href="mailto:${_sEsc(d.email_2)}" style="font-size:12px;color:var(--accent);word-break:break-all">${_sEsc(d.email_2)}</a></div>` : ''}
            ${row('Téléphone', d.telephone)}
            ${d.telephone_2 ? row('Téléphone 2', d.telephone_2) : ''}
            ${d.linkedin_url ? `<div style="padding:6px 0;border-bottom:1px solid var(--border)"><a href="${_sEsc(d.linkedin_url)}" target="_blank" style="font-size:12px;color:var(--accent)">LinkedIn</a></div>` : ''}
            ${row('Mode copywriting', d.copywriting_mode)}
            ${row('Catch-all', d.is_catch_all ? 'Oui' : null)}
            
            <!-- Section Plus d'infos (Scraper) -->
            ${(() => {
                try {
                    if (!d.donnees_audit) return '';
                    const audit = typeof d.donnees_audit === 'string' ? JSON.parse(d.donnees_audit) : d.donnees_audit;
                    if (!audit || Object.keys(audit).length === 0) return '';
                    
                    let metaHtml = '';
                    if (audit.tag) metaHtml += `<div style="margin-bottom:8px"><span style="color:var(--ink3);font-size:10px;text-transform:uppercase;display:block;margin-bottom:2px;letter-spacing:0.05em">Diagnostic :</span> <span style="font-weight:700;color:var(--ink1)">${_sEsc(audit.tag)}</span></div>`;
                    if (audit.reason) metaHtml += `<div style="margin-bottom:8px;font-size:12px;color:var(--ink2);line-height:1.4">${_sEsc(audit.reason)}</div>`;
                    
                    if (audit.ad_start) metaHtml += `<div style="margin-bottom:8px"><span style="color:var(--ink3)">Diffusion Ads :</span> ${_sEsc(audit.ad_start)}</div>`;
                    if (audit.fan_count) metaHtml += `<div style="margin-bottom:8px"><span style="color:var(--ink3)">Notoriété :</span> ${_sEsc(audit.fan_count)} abonnés</div>`;
                    if (audit.ad_body) {
                        metaHtml += `<div style="margin-top:12px">
                            <span style="color:var(--ink3);display:block;margin-bottom:4px;font-size:10px;text-transform:uppercase;letter-spacing:0.05em">Contenu de la publicité :</span>
                            <div style="font-style:italic;background:var(--surface2);padding:10px;border-radius:8px;border:1px solid var(--border);font-size:12px;line-height:1.4;color:var(--ink2)">${_sEsc(audit.ad_body)}</div>
                        </div>`;
                    }
                    
                    const fbUrl = audit.page_url || (audit.page_id ? `https://www.facebook.com/${audit.page_id}` : null);
                    if (fbUrl) {
                        metaHtml += `<div style="margin-top:12px"><a href="${_sEsc(fbUrl)}" target="_blank" style="color:#1877f2;text-decoration:none;font-size:12px;font-weight:600;display:flex;align-items:center;gap:6px">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M22 12c0-5.52-4.48-10-10-10S2 6.48 2 12c0 4.84 3.44 8.87 8 9.8V15H8v-3h2V9.5C10 7.57 11.57 6 13.5 6H16v3h-2c-.55 0-1 .45-1 1v2h3v3h-3v6.95c5.05-.5 9-4.76 9-9.95z"/></svg>
                            Voir la page Facebook →
                        </a></div>`;
                    }
                    
                    // Placeholder pour Capture d'écran
                    if (d.source === 'fb_ads' || d.source === 'ads') {
                        metaHtml += `<div style="margin-top:16px;padding-top:12px;border-top:1px dashed var(--border)">
                            <span style="color:var(--ink3);display:block;margin-bottom:6px;font-size:10px;text-transform:uppercase;letter-spacing:0.05em">Capture d'écran :</span>
                            <div style="width:100%;aspect-ratio:16/9;background:var(--surface2);border-radius:8px;display:flex;align-items:center;justify-content:center;color:var(--ink3);font-size:11px;font-style:italic;text-align:center;padding:20px;border:1px solid var(--border)">
                                Analyse visuelle en cours...<br>(Capture bientôt disponible)
                            </div>
                        </div>`;
                    }

                    if (audit.ad_id) {
                        const libUrl = `https://www.facebook.com/ads/library/?id=${audit.ad_id}`;
                        metaHtml += `<div style="margin-top:8px"><a href="${libUrl}" target="_blank" style="color:var(--ink2);text-decoration:none;font-size:12px;font-weight:600;display:flex;align-items:center;gap:6px">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
                            Voir dans l'Ad Library →
                        </a></div>`;
                    }

                    if (!metaHtml) return '';

                    return `
                    <div style="margin:20px 0;background:rgba(24,119,242,0.05);border:1px solid rgba(24,119,242,0.15);border-radius:12px;padding:16px">
                        <div style="font-size:11px;font-weight:800;color:#1877f2;margin-bottom:12px;text-transform:uppercase;letter-spacing:0.05em;display:flex;align-items:center;gap:6px">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>
                            Plus d'infos (Scraper)
                        </div>
                        <div style="font-size:12px;color:var(--ink1);line-height:1.4">
                            ${metaHtml}
                        </div>
                    </div>`;
                } catch(e) { return ''; }
            })()}
            
            ${section('Email généré')}
            ${d.email_objet ? `<div style="padding:6px 0;border-bottom:1px solid var(--border)"><span style="font-size:11px;color:var(--ink3)">Objet</span><br><span style="font-size:12px;font-weight:600">${_sEsc(d.email_objet)}</span></div>` : ''}
            ${d.email_corps ? `<div style="padding:8px 0"><div style="font-size:11px;color:var(--ink3);margin-bottom:4px">Corps</div><iframe id="sniper-email-preview" sandbox="allow-same-origin" style="width:100%;border:1px solid var(--border);border-radius:6px;min-height:200px;max-height:400px;background:#fff" scrolling="yes" frameborder="0"></iframe></div>` : ''}
            ${section('Statut prospection')}
            ${row('Statut', d.statut_prospection)}
            ${row('Date audit', d.date_generation ? d.date_generation.slice(0,10) : null)}
            ${section('Notes')}
            <div style="padding:8px 0">
                <textarea id="sniper-panel-notes" rows="4" style="width:100%;padding:9px 11px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--ink);font-size:13px;resize:vertical;box-sizing:border-box;font-family:inherit" placeholder="Notes privées sur ce lead…">${_sEsc(d.notes || '')}</textarea>
                <button onclick="sniperSaveNotes(${leadId})" style="margin-top:8px;width:100%;padding:9px;background:var(--accent,#3b82f6);color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer">&#128190; Sauvegarder les notes</button>
            </div>
            <div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap">
                <button class="btn" style="background:var(--accent);color:#fff;flex:1;justify-content:center;min-height:44px;font-size:15px;font-weight:600" onclick="sniperEditLead(${leadId})">Modifier</button>
                ${d.site_web ? `<a href="${_sEsc(d.site_web)}" target="_blank" class="btn" style="background:var(--surface2);color:var(--ink2);border:1px solid var(--border);flex:1;justify-content:center;min-height:44px;font-size:15px;font-weight:600">Voir site</a>` : ''}
                ${d.lien_rapport ? `<a href="${_sEsc(d.lien_rapport)}" target="_blank" class="btn" style="background:var(--surface2);color:var(--ink2);border:1px solid var(--border);flex:1;justify-content:center;min-height:44px;font-size:15px;font-weight:600">Voir rapport</a>` : ''}
            </div>
        `;

        if (d.email_corps) {
            const iframe = document.getElementById('sniper-email-preview');
            if (iframe) {
                const doc = iframe.contentDocument || iframe.contentWindow.document;
                doc.open();
                doc.write(d.email_corps);
                doc.close();
                iframe.style.height = Math.min(iframe.contentWindow.document.body.scrollHeight + 20, 400) + 'px';
            }
        }
    } catch (e) {
        body.innerHTML = `<p style="color:var(--error)">Erreur : ${e.message}</p>`;
    }
}


async function sniperSaveNotes(leadId) {
    const notes = document.getElementById('sniper-panel-notes')?.value || '';
    try {
        const r = await fetch(`/api/leads/${leadId}/edit`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ notes })
        });
        const d = await r.json();
        if (d.success) {
            if (typeof showToast === 'function') showToast('Notes sauvegardées ✓', 'success');
        } else {
            if (typeof showToast === 'function') showToast('Erreur : ' + (d.error || 'inconnue'), 'error');
        }
    } catch (e) {
        if (typeof showToast === 'function') showToast('Erreur réseau', 'error');
    }
}

function sniperClosePanel() {
    const panel = document.getElementById('sniper-lead-panel');
    if (panel) panel.style.display = 'none';
    const overlay = document.getElementById('sniper-lead-panel-overlay');
    if (overlay) overlay.style.display = 'none';
}

function sniperEditLead(leadId) {
    const panel = document.getElementById('sniper-lead-panel');
    const overlay = document.getElementById('sniper-lead-panel-overlay');
    if (panel) panel.style.display = 'none';
    if (overlay) overlay.style.display = 'none';
    
    fetch(`/api/sniper/lead/${leadId}`).then(r => r.json()).then(d => {
        document.getElementById('edit-lead-id').value = leadId;
        document.getElementById('edit-lead-nom').value = d.nom || '';
        document.getElementById('edit-lead-email').value = d.email_valide_audit || d.email || '';
        document.getElementById('edit-lead-tel').value = d.telephone || '';
        document.getElementById('edit-lead-site').value = d.site_web || '';
        document.getElementById('edit-lead-sector').value = d.category || '';
        document.getElementById('edit-lead-ville').value = d.ville || '';
        document.getElementById('modal-edit-lead').style.display = 'flex';
    });
}

function _sActions(lead) {
    const btns = [];
    if (lead.statut_prospection === 'repondu') {
        btns.push(`<button class="btn bp1 sm" onclick="sniperSendStep2(${lead.audit_id})" style="font-size:11px;padding:4px 10px">Envoyer rapport</button>`);
    }
    if (lead.lien_rapport) {
        btns.push(`<a href="${_sEsc(lead.lien_rapport)}" target="_blank" class="btn bg1 sm" style="font-size:11px;padding:4px 10px">Rapport</a>`);
    }
    return btns.join(' ') || '<span style="color:var(--ink3);font-size:11px">—</span>';
}

// ─── Arrêt d'urgence des scrapers ────────────────────────────────────────────

async function sniperStop(source) {
    const sourceNames = {
        'ads': 'Pipeline Ads',
        'fb_ads': 'FB Ads Scraper',
        'tech': 'EcomScraper',
        'jobs': 'JobsScraper',
        'bodacc': 'BODACC Scanner'
    };
    
    const confirmed = confirm(`Arrêter ${sourceNames[source] || source} ?\n\nLe scraper s'arrêtera proprement à la prochaine étape.`);
    if (!confirmed) return;
    
    try {
        const endpoints = {
            'ads': '/api/sniper/stop',
            'fb_ads': '/api/sniper/fb-ads-stop',
            'tech': '/api/sniper/ecom-stop',
            'jobs': '/api/sniper/jobs-stop',
            'bodacc': '/api/sniper/bodacc-stop'
        };
        
        const r = await fetch(endpoints[source], { method: 'POST' });
        const d = await r.json();
        
        if (d.ok) {
            showToast(`${sourceNames[source]} : arrêt demandé`, 'success');
        } else {
            showToast(`Erreur : ${d.error || 'Échec de l\'arrêt'}`, 'error');
        }
    } catch (e) {
        showToast('Erreur réseau', 'error');
    }
}
