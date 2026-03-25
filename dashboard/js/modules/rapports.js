/**
 * dashboard/js/modules/rapports.js — Rapports PDF et Previews local-first
 */

async function loadReports() {
    try {
        if (typeof _globalFilters !== 'function') return;
        
        // Load both reports and previews
        const [r, r2] = await Promise.all([
            fetch('/api/rapports' + _globalFilters()),
            fetch('/api/previews')
        ]);
        const d = await r.json();
        const dp = await r2.json();
        
        const previews = dp.previews || [];
        const previewMap = {};
        previews.forEach(p => { previewMap[p.slug] = p; });
        
        console.log("  [Reports] API Response:", d);
        if (d.error || !d.rapports) {
            setInner('tbody-reports', '<tr><td colspan="7" style="text-align:center;padding:1rem">Aucun rapport disponible</td></tr>');
            return;
        }

        const rows = d.rapports.map(rp => {
            // Extract slug from lien_rapport
            let slug = '';
            let status = 'non_genere';
            let previewUrl = '';
            
            if (rp.lien_rapport) {
                if (rp.lien_rapport.startsWith('local://')) {
                    slug = rp.lien_rapport.replace('local://', '').replace('/', '');
                    status = 'local';
                    previewUrl = '/previews/' + slug + '/';
                } else if (rp.lien_rapport.startsWith('https://')) {
                    slug = rp.lien_rapport.split('/').filter(s => s).pop();
                    status = 'publie';
                    previewUrl = rp.lien_rapport;
                }
            }
            
            const statusLabel = status === 'local' ? '<span class="b" style="background:var(--orange);color:white;padding:2px 6px;border-radius:3px;font-size:10px">LOCAL</span>' : 
                               status === 'publie' ? '<span class="b" style="background:var(--green);color:white;padding:2px 6px;border-radius:3px;font-size:10px">PUBLIÉ</span>' : 
                               '<span class="b" style="background:var(--gray);color:white;padding:2px 6px;border-radius:3px;font-size:10px">—</span>';
            
            const previewBtn = status === 'local' ? 
                `<button class="btn bp1 sm" onclick="previewReport('${slug}')" title="Prévisualiser">👁</button>` :
                (status === 'publie' ? 
                `<a href="${previewUrl}" target="_blank" class="btn bg1 sm" title="Voir en ligne">👁</a>` : 
                `<button class="btn bg2 sm" disabled title="Non généré">—</button>`);
            
            const pushBtn = status === 'local' ? 
                `<button class="btn bp1 sm" onclick="pushReport('${slug}')" title="Pusher sur GitHub">☁️</button>` :
                `<button class="btn bg2 sm" disabled title="Déjà publié">✓</button>`;
            
            return `
            <tr>
                <td><strong>${typeof escHtml === 'function' ? escHtml(rp.nom) : rp.nom}</strong></td>
                <td>${typeof escHtml === 'function' ? escHtml(rp.secteur || rp.category || '—') : (rp.secteur || rp.category || '—')}</td>
                <td>${typeof pillUrgence === 'function' ? pillUrgence(rp.score || rp.score_urgence || 0) : (rp.score || rp.score_urgence || 0)}</td>
                <td>${statusLabel}</td>
                <td>${rp.date_audit ? rp.date_audit.split(' ')[0] : '—'}</td>
                <td style="display:flex;gap:4px">
                    ${previewBtn}
                    ${pushBtn}
                </td>
                <td>
                    ${status === 'publie' ? 
                        `<a href="${rp.lien_rapport || rp.lien_pdf || '#'}" target="_blank" class="btn bg1 sm">📄</a>` : 
                        `<button class="btn bg2 sm" disabled>📄</button>`}
                    <button class="btn bg2 sm" style="margin-left:5px" onclick="auditLead('${typeof escHtml === 'function' ? escHtml(rp.nom) : rp.nom}')" title="Relancer l'audit">🔄</button>
                </td>
            </tr>
        `}).join('');
        setInner('tbody-reports', rows || '<tr><td colspan="7" style="text-align:center;padding:1rem">Aucun rapport généré</td></tr>');
    } catch (e) { console.error("loadReports:", e); }
}

async function previewReport(slug) {
    window.open('/previews/' + slug + '/', '_blank');
}

async function pushReport(slug) {
    if (!confirm('Publier ce rapport sur GitHub ?')) return;
    
    try {
        const r = await fetch('/api/previews/push', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ slugs: [slug] })
        });
        const d = await r.json();
        
        if (d.results && d.results[0].status === 'published') {
            showToast('✅ Rapport publié: ' + d.results[0].url, 'success');
            loadReports();
        } else {
            showToast('❌ Erreur: ' + (d.results ? d.results[0].message : 'Erreur inconnue'), 'error');
        }
    } catch (e) {
        showToast('❌ Erreur: ' + e, 'error');
    }
}

async function pushAllReports() {
    // Get all local reports
    try {
        const r = await fetch('/api/previews');
        const d = await r.json();
        const locals = d.previews.filter(p => p.local && !p.published);
        
        if (locals.length === 0) {
            showToast('Aucun rapport local à publier', 'info');
            return;
        }
        
        if (!confirm(`Publier les ${locals.length} rapports locaux sur GitHub ?`)) return;
        
        const slugs = locals.map(p => p.slug);
        const r2 = await fetch('/api/previews/push', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ slugs: slugs })
        });
        const d2 = await r2.json();
        
        const published = d2.results.filter(r => r.status === 'published').length;
        showToast(`✅ ${published}/${slugs.length} rapports publiés`, 'success');
        loadReports();
    } catch (e) {
        showToast('❌ Erreur: ' + e, 'error');
    }
}
