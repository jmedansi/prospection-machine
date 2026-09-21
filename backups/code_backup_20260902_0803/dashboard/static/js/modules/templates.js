/**
 * dashboard/static/js/modules/templates.js
 * Éditeur de templates email — lecture, édition, sauvegarde, preview
 */

let _tmCategories = [];
let _tmVariables = {};
let _tmCurrent = { category: null, filename: null, content: null, subject: null };

async function tmInit() {
    await tmLoadList();
}

async function tmLoadList() {
    try {
        const r = await fetch('/api/templates/');
        const d = await r.json();
        _tmCategories = d.categories;
        _tmVariables = d.variables;
        tmRenderCategories();
        tmRenderVariables();
    } catch (e) {
        console.error(e);
    }
}

function tmRenderCategories() {
    const container = document.getElementById('tm-categories');
    if (!container) return;
    container.innerHTML = _tmCategories.map(cat => `
        <div class="tm-cat-group">
            <div class="tm-cat-label">${cat.label}</div>
            ${cat.files.map(f => `
                <div class="tm-file-item" onclick="tmOpen('${cat.id}', '${f.name}')" id="tm-file-${cat.id}-${f.name}">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <span>${f.label}</span>
                </div>
            `).join('')}
        </div>
    `).join('');
}

function tmRenderVariables() {
    const container = document.getElementById('tm-variables');
    if (!container) return;
    const allVars = [...(_tmVariables.pipeline || []), ...(_tmVariables.sniper || [])];
    container.innerHTML = allVars.map(v => `<code style="color:var(--accent)">${v.var}</code> — ${v.desc}<br>`).join('');
}

async function tmOpen(category, filename) {
    document.getElementById('tm-filename').textContent = filename;
    document.getElementById('tm-editor').value = 'Chargement…';
    document.querySelectorAll('.tm-file-item').forEach(el => el.classList.remove('active'));
    const item = document.getElementById(`tm-file-${category}-${filename}`);
    if (item) item.classList.add('active');
    tmSwitchTab('content', document.querySelector('.tm-tab'));

    try {
        const r = await fetch(`/api/templates/${category}/${filename}`);
        const d = await r.json();

        const subjectMatch = d.content.match(/<title>(.*?)<\/title>/);
        _tmCurrent = {
            category,
            filename,
            content: d.content,
            subject: subjectMatch ? subjectMatch[1] : '',
        };
        tmSwitchTab('content', document.querySelector('.tm-tab'));
    } catch (e) {
        document.getElementById('tm-editor').value = 'Erreur de chargement';
    }
}

function tmSwitchTab(tab, el) {
    document.querySelectorAll('.tm-tab').forEach(t => t.classList.remove('active'));
    if (el) el.classList.add('active');
    const editor = document.getElementById('tm-editor');
    if (tab === 'subject') {
        editor.value = _tmCurrent.subject || '';
        editor.placeholder = 'Objet de l\'email…';
    } else {
        editor.value = _tmCurrent.content || '';
        editor.placeholder = 'Contenu HTML du template…';
    }
    editor._tab = tab;
}

async function tmSave() {
    if (!_tmCurrent.filename) return;
    const editor = document.getElementById('tm-editor');
    const tab = editor._tab || 'content';
    const btn = document.getElementById('tm-save-btn');
    btn.disabled = true;
    btn.textContent = '…';

    try {
        if (tab === 'subject') {
            const newSubject = editor.value.trim();
            const newContent = _tmCurrent.content.replace(
                /<title>.*?<\/title>/,
                `<title>${newSubject}</title>`
            );
            await fetch(`/api/templates/${_tmCurrent.category}/${_tmCurrent.filename}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: newContent }),
            });
            _tmCurrent.subject = newSubject;
            _tmCurrent.content = newContent;
        } else {
            await fetch(`/api/templates/${_tmCurrent.category}/${_tmCurrent.filename}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: editor.value }),
            });
            _tmCurrent.content = editor.value;
        }
        showToast('Template sauvegardé', 'success');
    } catch (e) {
        showToast('Erreur lors de la sauvegarde', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Enregistrer';
    }
}

async function tmPreview() {
    if (!_tmCurrent.filename) return;
    const frame = document.getElementById('tm-preview-frame');
    const modal = document.getElementById('tm-preview-modal');
    modal.style.display = 'flex';
    frame.srcdoc = _tmCurrent.content;
}

function tmClosePreview() {
    const modal = document.getElementById('tm-preview-modal');
    const frame = document.getElementById('tm-preview-frame');
    modal.style.display = 'none';
    frame.srcdoc = '';
}