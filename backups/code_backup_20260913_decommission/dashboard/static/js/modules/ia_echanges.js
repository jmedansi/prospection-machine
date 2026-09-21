/**
 * dashboard/js/modules/ia_echanges.js — Passerelle IA ⇄ Dashboard
 *
 * Consomme les endpoints /api/ia/* de dashboard/routes/ia_echanges.py.
 * Pile mince : export → IA, scan ← IA, listing maquettes, log d'écarts.
 */

function iaEchangesLoadStatus() {
    fetch('/api/ia/status')
        .then(r => r.json())
        .then(d => {
            const lists = d.liste || [];
            const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v ?? '—'; };
            set('ia-stat-listes', lists.length);
            set('ia-stat-csv', lists.filter(l => l.csv_existe).length);
            set('ia-stat-maquettes', lists.reduce((s, l) => s + (l.maquettes || 0), 0));
            set('ia-stat-ecarts', lists.reduce((s, l) => s + (l.ecarts || []).length, 0));
            document.getElementById('ia-maquettes-browser').innerHTML =
                lists.map(l =>
                    `<div style="padding:8px 0;border-bottom:1px solid var(--surface2)">
                        <button class="btn sm" onclick="iaThis('${l.liste.replace(/'/g, "\\'")}')">${l.liste}</button>
                        <span style="margin-left:10px;color:var(--ink3)">CSV: ${l.csv_existe ? '✓' : '—'} · Maquettes: ${l.maquettes}</span>
                     </div>`
                ).join('') || '<span>Aucune liste d\'échange pour l\'instant.</span>';
        })
        .catch(e => console.error('iaEchangesLoadStatus', e));
}

function iaThis(liste) {
    document.getElementById('ia-scan-liste').value = liste;
    document.getElementById('ia-export-liste').value = liste;
    iaEchangesLoadMaquettes(liste);
}

function iaEchangesExport() {
    const liste = document.getElementById('ia-export-liste').value || 'leads';
    const objectif = document.getElementById('ia-export-objectif').value;
    const out = document.getElementById('ia-export-result');
    out.textContent = 'Export en cours…';
    fetch('/api/ia/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ liste, objectif })
    })
        .then(r => r.json())
        .then(d => {
            if (d.ok) {
                fetch('/api/ia/maquettes/' + encodeURIComponent(liste))
                    .then(r => r.json()).then(() => {});
                document.getElementById('ia-scan-liste').value = liste;
                out.innerHTML = `<span style="color:var(--green)">${d.exportes} lead(s) exporté(s) → ${d.csv}</span>`;
                iaEchangesLoadStatus();
            } else {
                out.textContent = (d.error || 'Erreur export');
            }
        })
        .catch(e => { out.textContent = 'Erreur renvoi : ' + e; });
}

function iaEchangesScan() {
    const liste = document.getElementById('ia-scan-liste').value || 'leads';
    const out = document.getElementById('ia-scan-result');
    out.textContent = 'Lecture en cours…';
    fetch('/api/ia/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ liste })
    })
        .then(r => r.json().then(d => ({ ok: r.ok, d })))
        .then(({ ok, d }) => {
            if (ok && d.ok) {
                out.innerHTML = `<span style="color:var(--green)">${d.qualifies || 0} qualifié(s), ${d.emails || 0} email(s) rédigé(s), ${d.ecarts || 0} écart(s).</span>`;
                iaEchangesLog();
                iaEchangesLoadStatus();
            } else {
                out.textContent = (d.error || 'Erreur scan');
            }
        })
        .catch(e => { out.textContent = 'Erreur renvoi : ' + e; });
}

function iaEchangesLoadMaquettes(listeArg) {
    let liste = listeArg || document.getElementById('ia-export-liste').value || 'leads';
    if (!listeArg) document.getElementById('ia-scan-liste').value = liste;
    const box = document.getElementById('ia-maquettes-browser');
    box.textContent = 'Chargement…';
    fetch('/api/ia/maquettes/' + encodeURIComponent(liste))
        .then(r => r.json())
        .then(d => {
            const items = d.maquettes || [];
            if (!items.length) { box.textContent = 'Aucune maquette dans cette liste.'; return; }
            box.innerHTML = items.map(m =>
                `<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--surface2)">
                    <strong>#${m.IdLead}</strong>
                    <span style="color:var(--ink3)">index.html: ${m.a_index ? '✓' : '—'} · capture.png: ${m.a_capture ? '✓' : '—'}</span>
                    <span>
                        ${m.a_capture ? `<a class="btn sm" style="text-decoration:none" href="/api/ia/maquettes/${encodeURIComponent(d.liste)}/${m.IdLead}/capture.png" target="_blank">Capture</a>` : ''}
                        ${m.a_index ? `<a class="btn sm" style="text-decoration:none" href="/api/ia/maquettes/${encodeURIComponent(d.liste)}/${m.IdLead}/index.html" target="_blank">Ouvrir</a>` : ''}
                    </span>
                 </div>`
            ).join('');
        })
        .catch(e => { box.textContent = 'Erreur chargement maquettes : ' + e; });
}

function iaEchangesLog() {
    fetch('/api/ia/status')
        .then(r => r.json())
        .then(d => {
            const all = (d.liste || []).flatMap(l => l.ecarts || []);
            document.getElementById('ia-ecarts-log').textContent =
                all.length ? all.join('\n') : 'Aucun écart enregistré.';
        })
        .catch(() => {});
}