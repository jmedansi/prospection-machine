/**
 * dashboard/js/modules/crm.js — Emailing, Suivi et CRM
 */

async function loadEmails() {
    try {
        const url = '/api/emails' + _globalFilters();
        const r = await fetch(url);
        const d = await r.json();
        if (d.error) return;
        _emailsData = d.emails || [];

        const rows = _emailsData.map((e, i) => `
            <tr style="cursor:pointer" class="${i === _currentIndex ? 'active' : ''}" onclick="showEmailPreview(${i})">
                <td><strong>${typeof escHtml === 'function' ? escHtml(e.nom) : e.nom}</strong><div style="font-size:10px;color:var(--ink3)">${typeof escHtml === 'function' ? escHtml(e.email) : e.email}</div></td>
                <td style="font-size:11px;max-width:160px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${typeof escHtml === 'function' ? escHtml(e.objet) : e.objet}</td>
                <td>${typeof pillUrgence === 'function' ? pillUrgence(e.score_urgence) : e.score_urgence}</td>
                <td>
                    <div class="tg ${e.approuve ? 'on' : ''}" onclick="event.stopPropagation();toggleApprove(this,'${typeof escHtml === 'function' ? escHtml(e.nom) : e.nom}')"></div>
                </td>
                <td><button class="btn bg1 sm" onclick="event.stopPropagation();showEmailPreview(${i})">Voir</button></td>
            </tr>`).join('');
        setInner('tbody-emails', rows || '<tr><td colspan="5" style="text-align:center;padding:1rem">Aucun email généré</td></tr>');
        if (_emailsData.length > 0) showEmailPreview(_currentIndex);
    } catch (e) { console.error('loadEmails:', e); }
}

function showEmailPreview(i) {
    _currentIndex = i;
    const e = _emailsData[i];
    if (!e) return;
    if (typeof setText === 'function') {
        setText('PN', e.nom);
        setText('PE', e.email);
        setText('PS', 'Objet : ' + e.objet);
    }
    const bodyEl = document.getElementById('PB');
    if (bodyEl) bodyEl.srcdoc = e.corps || '—';

    const bApp = document.getElementById('btn-approve-current');
    const bRej = document.getElementById('btn-reject-current');
    const previewDiv = document.querySelector('.ep');

    if (bApp) bApp.onclick = () => toggleApprove(null, e.nom, true);
    if (bRej) bRej.onclick = () => toggleApprove(null, e.nom, false);

    if (previewDiv) {
        const ex = document.getElementById('edit-pv-btn');
        if (ex) ex.remove();

        const eBtn = document.createElement('button');
        eBtn.id = 'edit-pv-btn';
        eBtn.className = 'btn bg1 sm';
        eBtn.style.position = 'absolute';
        eBtn.style.top = '10px';
        eBtn.style.right = '15px';
        eBtn.style.zIndex = '10';
        eBtn.style.boxShadow = 'var(--sh-md)';
        eBtn.textContent = '✏️ Éditer texte';
        previewDiv.style.position = 'relative';
        previewDiv.appendChild(eBtn);

        eBtn.onclick = (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            openEditEmail(_currentIndex);
        };
    }
}

async function regenerateCurrentEmail() {
    if (!_emailsData[_currentIndex]) return;
    const nom = _emailsData[_currentIndex].nom;

    try {
        const r = await fetch('/api/email/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lead_nom: nom })
        });
        const d = await r.json();
        if (d.error) {
            if (typeof showToast === 'function') showToast('Erreur: ' + d.error, 'error');
        } else {
            if (typeof showToast === 'function') showToast('✅ Email régénéré avec succès!');
            loadEmails();
        }
    } catch (e) {
        if (typeof showToast === 'function') showToast('Erreur lors de la régénération', 'error');
    }
}

function editCurrentEmail() {
    if (!_emailsData[_currentIndex]) return;
    openEditEmail(_currentIndex);
}

function viewCurrentAudit() {
    if (!_emailsData[_currentIndex]) return;
    const e = _emailsData[_currentIndex];
    const lien = e.lien_rapport;
    if (lien) window.open(lien, '_blank');
    else showToast("Aucun rapport d'audit disponible pour ce prospect", 'info');
}

function openEditEmail(index) {
    const e = _emailsData[index];
    if (!e) return;
    document.getElementById('edit-email-nom').value = e.nom;
    document.getElementById('edit-email-objet').value = e.objet || '';
    document.getElementById('edit-email-corps').value = e.corps || '';
    if (typeof openModal === 'function') openModal('modal-edit-email');
}

function openEditEmailByNom(nom) {
    let e = _emailsData.find(x => x.nom === nom);
    if (!e) e = _allLeads.find(x => x.nom === nom);
    if (!e) return;
    document.getElementById('edit-email-nom').value = e.nom;
    document.getElementById('edit-email-objet').value = e.objet || e.email_objet || '';
    document.getElementById('edit-email-corps').value = e.corps || e.email_corps || '';
    if (typeof openModal === 'function') openModal('modal-edit-email');
}

async function openCRMEdit(emailId) {
    try {
        const r = await fetch('/api/emails/' + emailId);
        const e = await r.json();
        if (e.error) { showToast(e.error, 'error'); return; }

        if (typeof setText === 'function') {
            setText('crm-prospect-nom', e.prospect_nom || '—');
            setText('crm-prospect-email', e.prospect_email || '—');
            setText('crm-dest-reelle', e.email_destinataire || '—');
        }
        
        const statutEl = document.getElementById('crm-statut');
        if (statutEl) {
            if (e.bounce) { statutEl.className = 'b br'; statutEl.textContent = 'BOUNCE'; }
            else if (e.spam) { statutEl.className = 'b br'; statutEl.textContent = 'SPAM'; }
            else if (e.statut_envoi === 'delivré' || e.statut_envoi === 'envoye') { statutEl.className = 'b bg'; statutEl.textContent = 'DELIVRÉ'; }
            else { statutEl.className = 'b bb'; statutEl.textContent = e.statut_envoi || '—'; }
        }
        
        if (typeof setText === 'function') {
            setText('crm-ouvert', e.ouvert ? '✅ Oui' : '❌ Non');
            setText('crm-clic', e.clique ? '✅ Oui' : '❌ Non');
            setText('crm-objet', e.email_objet || '(pas d\'objet)');
        }
        
        const oEl = document.getElementById('crm-ouvert');
        if (oEl) oEl.style.color = e.ouvert ? 'var(--green)' : 'var(--ink3)';
        const cEl = document.getElementById('crm-clic');
        if (cEl) cEl.style.color = e.clique ? 'var(--green)' : 'var(--ink3)';
        
        const crmBody = document.getElementById('crm-corps');
        if (crmBody) crmBody.srcdoc = e.email_corps || '(pas de corps)';
        document.getElementById('crm-notes').value = e.notes || '';
        document.getElementById('crm-email-id').value = e.id;

        const title = document.getElementById('crm-title');
        if (title) title.textContent = "Détails — " + (e.prospect_nom || 'Prospect');

        if (typeof openModal === 'function') openModal('modal-crm-details');
    } catch (err) {
        console.error("openCRMEdit error:", err);
        showToast("Erreur lors du chargement des détails", 'error');
    }
}

async function saveCRMNotes() {
    const id = document.getElementById('crm-email-id').value;
    const notes = document.getElementById('crm-notes').value;
    try {
        const r = await fetch('/api/crm/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email_id: id, notes: notes })
        });
        if (r.ok) { 
            if (typeof showToast === 'function') showToast('✅ Note sauvegardée');
            if (typeof loadCRM === 'function') loadCRM();
        } else showToast("Erreur de sauvegarde de la note", 'error');
    } catch (e) { console.error(e); }
}

function editCurrentEmailCRM() {
    const nom = document.getElementById('crm-prospect-nom')?.textContent;
    if (!nom || nom === '—') return;
    if (typeof closeModal === 'function') closeModal('modal-crm-details');
    openEditEmailByNom(nom);
}

async function saveEmail() {
    const nom = document.getElementById('edit-email-nom').value;
    const data = {
        lead_id: nom,
        email_objet: document.getElementById('edit-email-objet').value,
        email_corps: document.getElementById('edit-email-corps').value
    };
    try {
        const r = await fetch('/api/email/update', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data)
        });
        if (r.ok) { 
            if (typeof closeModal === 'function') closeModal('modal-edit-email'); 
            loadEmails(); 
            if (typeof loadLeads === 'function') loadLeads(); 
        }
        else showToast("Erreur de sauvegarde de l'email", 'error');
    } catch (e) { console.error(e); }
}

async function toggleApprove(el, nom, forceState = null) {
    let approved;
    if (forceState !== null) {
        approved = forceState;
    } else if (el) {
        el.classList.toggle('on');
        approved = el.classList.contains('on');
    } else {
        return;
    }

    try {
        const r = await fetch('/api/email/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lead_id: nom, approved })
        });
        if (forceState !== null) loadEmails();
    } catch (e) { console.error('approve:', e); }
}

let _emailInterval = null;

function showEmailProgress(current, total, success, failed) {
    const el = document.getElementById('sidebar-email');
    if (!el) return;
    
    el.style.display = 'block';
    
    const pct = total > 0 ? Math.round((current / total) * 100) : 0;
    const barEl = document.getElementById('sidebar-email-bar');
    const textEl = document.getElementById('sidebar-email-text');
    const pctEl = document.getElementById('sidebar-email-pct');
    
    if (barEl) barEl.style.width = pct + '%';
    if (pctEl) pctEl.innerHTML = pct + '%';
    if (textEl) {
        textEl.innerHTML = `<strong>${current}</strong>/${total}` + (failed ? ` · <span style="color:var(--red)">${failed} ❌</span>` : '') + (success ? ` · <span style="color:var(--green)">${success} ✓</span>` : '');
    }
}

function hideEmailProgress() {
    const el = document.getElementById('sidebar-email');
    if (el) {
        el.style.display = 'none';
    }
}

async function pollEmailStatus() {
    try {
        const r = await fetch('/api/email/status');
        const d = await r.json();
        if (!d.running) {
            if (_emailInterval) clearInterval(_emailInterval);
            _emailInterval = null;
            hideEmailProgress();
            if (d.current > 0 && typeof showToast === 'function') {
                showToast(`✅ Envoi terminé : ${d.success}/${d.total} emails envoyés`, 'success');
            }
            if (typeof refreshAll === 'function') refreshAll();
            const btn = document.getElementById('btn-send-approved');
            if (btn) { btn.textContent = 'Envoyer approuvés'; btn.disabled = false; }
        } else {
            showEmailProgress(d.current, d.total, d.success, d.failed);
        }
    } catch (e) { 
        if (_emailInterval) clearInterval(_emailInterval);
        _emailInterval = null;
    }
}

async function sendApproved() {
    const btn = document.getElementById('btn-send-approved');
    if (btn) { btn.textContent = 'Lancement...'; btn.disabled = true; }
    try {
        const r = await fetch('/api/email/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lead_ids: [] })
        });
        const d = await r.json();
        if (d.statut === 'lance' || d.total > 0) {
            if (typeof showToast === 'function') showToast(`🚀 Envoi en cours pour ${d.total} emails...`);
            if (_emailInterval) clearInterval(_emailInterval);
            _emailInterval = setInterval(pollEmailStatus, 3000);
        } else if (d.error) {
            if (typeof showToast === 'function') showToast('❌ Erreur: ' + d.error, 'error');
            if (btn) { btn.textContent = 'Envoyer approuvés'; btn.disabled = false; }
        }
    } catch (e) {
        showToast('Erreur réseau: ' + e.message, 'error');
        if (btn) { btn.textContent = 'Envoyer approuvés'; btn.disabled = false; }
    }
}

async function approveAll() {
    if (!await showConfirm('Approuver tous les emails générés pour envoi ?', { title: 'Approuver tout', confirmText: 'Approuver' })) return;
    const promises = _emailsData.map(e => fetch('/api/email/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lead_id: e.nom, approved: true })
    }));
    await Promise.all(promises);
    loadEmails();
}

async function sendToMe() {
    const btn = document.getElementById('btn-send-to-me');
    if (btn) { btn.textContent = 'Envoi...'; btn.disabled = true; }

    const e = _emailsData[_currentIndex];
    if (!e) { 
        if (typeof showToast === 'function') showToast('Aucun email sélectionné', 'error'); 
        if (btn) { btn.textContent = '📤 M\'envoyer le test'; btn.disabled = false; } 
        return; 
    }

    try {
        const r = await fetch('/api/email/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                objet: e.objet || e.email_objet,
                corps: e.corps || e.email_corps,
                lead_id: e.lead_id || null
            })
        });
        const d = await r.json();
        if (d.success) {
            if (typeof showToast === 'function') showToast(`✅ Test envoyé à ${d.sent_to}`);
            setTimeout(() => { 
                if (typeof loadCRM === 'function') loadCRM(); 
                if (typeof loadTracking === 'function') loadTracking(); 
            }, 1500);
        } else {
            if (typeof showToast === 'function') showToast('❌ Erreur: ' + (d.error || 'Inconnue'), 'error');
        }
    } catch (err) { 
        if (typeof showToast === 'function') showToast('❌ Erreur réseau', 'error'); 
    }
    finally { if (btn) { btn.textContent = '📤 M\'envoyer le test'; btn.disabled = false; } }
}
// --- Fonctions de Suivi (Tracking) ---
async function loadTracking() {
    try {
        const url = '/api/tracking' + _globalFilters();
        const r = await fetch(url);
        const d = await r.json();
        if (d.error) return;

        const rows = (d.events || []).map(ev => `
            <tr>
                <td style="padding:4px 8px"><strong>${typeof escHtml === 'function' ? escHtml(ev.nom) : ev.nom}</strong></td>
                <td style="padding:4px 8px">${typeof escHtml === 'function' ? escHtml(ev.event) : ev.event}</td>
                <td style="padding:4px 8px;color:var(--ink3)">${ev.date ? ev.date.split(' ')[1] || ev.date : '—'}</td>
            </tr>
        `).join('');
        
        // Update both cockpit and campaign tracking
        setInner('tbody-tracking', rows || '<tr><td colspan="3" style="text-align:center;color:var(--ink3);padding:10px">Aucune activité récente</td></tr>');
        setInner('tbody-tracking-campagnes', rows || '<tr><td colspan="3" style="text-align:center;color:var(--ink3);padding:10px">Aucun envoi récent</td></tr>');
    } catch (e) { console.error('loadTracking error:', e); }
}

let _activeCRMFilter = 'tous';

async function loadCRMCounts() {
    try {
        const url = '/api/crm/counts' + _globalFilters();
        const r = await fetch(url);
        const d = await r.json();
        if (d.error) return;
        
        const filters = ['tous', 'ouverts', 'cliques', 'repondus', 'positifs', 'bounces', 'spam'];
        filters.forEach(f => {
            const btn = document.querySelector(`#crm-filters button[onclick*="'${f}'"]`);
            if (btn) {
                const label = btn.textContent.replace(/\s*\(\d+\)$/, '');
                btn.textContent = `${label} (${d[f] || 0})`;
            }
        });
    } catch (e) { console.error('loadCRMCounts:', e); }
}

function setCRMFilter(f, el) {
    _activeCRMFilter = f;
    const parent = document.getElementById('crm-filters');
    if (parent) {
        parent.querySelectorAll('button').forEach(b => b.classList.remove('active'));
    }
    if (el) el.classList.add('active');
    loadCRM();
    loadCRMCounts();
}

// --- Fonctions de Pipeline CRM ---
async function loadCRM() {
    try {
        const url = '/api/crm' + _globalFilters({ filter: _activeCRMFilter });
        const r = await fetch(url);
        const d = await r.json();
        if (d.error) return;

        const rows = (d.crm || []).map(item => {
            const date = item.date_envoi ? item.date_envoi.split(' ')[0] : '—';
            const tracking = `
                <div style="font-size:10px">
                    ${item.ouvert ? '<span style="color:var(--green)">✓ Ouvert</span>' : '<span style="color:var(--ink3)">Non ouvert</span>'}<br>
                    ${item.clique ? '<span style="color:var(--green)">✓ Cliqué</span>' : ''}
                </div>`;
            const rdv = item.rdv_confirme ? '<span class="b bg">OUI</span>' : '—';
            const reponseBadge = item.repondu ? `<span class="b ${item.type_reponse === 'positive' ? 'bg' : 'bb'}">${item.type_reponse || 'REÇUE'}</span>` : '—';

            return `
            <tr style="cursor:pointer" onclick="openCRMEdit(${item.email_id || item.id})">
                <td>
                    <strong>${typeof escHtml === 'function' ? escHtml(item.nom) : item.nom}</strong>
                    <div style="font-size:10px;color:var(--ink3)">${typeof escHtml === 'function' ? escHtml(item.prospect_email || item.email) : (item.prospect_email || item.email)}</div>
                </td>
                <td>${date}</td>
                <td>${tracking}</td>
                <td>${reponseBadge}</td>
                <td>${rdv}</td>
                <td style="text-align:right">
                    <button class="btn bg1 sm" onclick="event.stopPropagation();openCRMEdit(${item.email_id || item.id})">Détails</button>
                </td>
            </tr>`;
        }).join('');
        setInner('tbody-crm', rows || '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--ink3)">Aucun envoi à suivre pour le moment</td></tr>');
    } catch (e) { console.error('loadCRM error:', e); }
}

async function loadRoiData() {
    try {
        const [funnelRes, nichesRes] = await Promise.all([
            fetch('/api/stats/funnel'),
            fetch('/api/stats/niches')
        ]);
        
        const funnel = await funnelRes.json();
        const niches = await nichesRes.json();
        
        const sent = funnel.total_sent || 0;
        const clicked = funnel.total_clicked || 0;
        const replied = funnel.total_replied || 0;
        const rdv = funnel.total_rdv || 0;
        
        const ctr = sent > 0 ? ((clicked / sent) * 100).toFixed(1) : 0;
        const replyRate = sent > 0 ? ((replied / sent) * 100).toFixed(1) : 0;
        
        setInner('roi-ctr', ctr + '%');
        setInner('roi-reply', replyRate + '%');
        setInner('roi-rdv', rdv);
        setInner('roi-sent', sent);
        
        setInner('roi-scraped', funnel.total_scraped || 0);
        setInner('roi-audited', funnel.total_audited || 0);
        setInner('roi-sent2', sent);
        setInner('roi-clicked', clicked);
        setInner('roi-replied', replied);
        
        const nicheRows = niches.slice(0, 10).map(n => `
            <tr>
                <td>${n.category || '—'}</td>
                <td>${n.ville || '—'}</td>
                <td>${n.envois}</td>
                <td>${n.clics}</td>
                <td style="font-weight:600;color:var(--accent)">${(n.taux_clic || 0).toFixed(1)}%</td>
            </tr>
        `).join('');
        setInner('tbody-niches', nicheRows || '<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--ink3)">Aucune donnée</td></tr>');
        
    } catch (e) { console.error('loadRoiData error:', e); }
}
