/**
 * dashboard/js/modules/sources.js — Hub des sources de leads
 *
 * Une seule page pour gérer tous les scrapers.
 * Chaque source ouvre un panneau slide-in dédié.
 *
 * Sources : maps | ads | fb_ads | tech | jobs | bodacc
 */

// ─── Définitions des sources ──────────────────────────────────────────────────

const _SOURCES = {
    maps: {
        label:       'Google Maps',
        description: 'PME locales via Google Maps & GMB',
        icon:        '🗺',
        color:       '#4285f4',
        statusApi:   null,  // pas de statut temps réel (agent externe)
    },
    ads: {
        label:       'Google Ads',
        description: 'Annonceurs actifs sur Google',
        icon:        '📢',
        color:       '#f97316',
        statusApi:   '/api/sniper/status',
    },
    fb_ads: {
        label:       'Facebook Ads',
        description: 'Annonceurs actifs sur Meta',
        icon:        '📘',
        color:       '#1877f2',
        statusApi:   '/api/sniper/fb-ads-status',
    },
    tech: {
        label:       'Tech / E-com',
        description: 'Sites e-commerce et stacks techniques ciblées',
        icon:        '⚙️',
        color:       '#8b5cf6',
        statusApi:   '/api/sniper/tech-status',
    },
    jobs: {
        label:       'Offres d\'emploi',
        description: 'Entreprises qui recrutent (signal de croissance)',
        icon:        '💼',
        color:       '#06b6d4',
        statusApi:   '/api/sniper/jobs-status',
    },
    bodacc: {
        label:       'BODACC',
        description: 'Nouvelles nominations de dirigeants',
        icon:        '🏛',
        color:       '#10b981',
        statusApi:   null,
    },
};

// ─── État ─────────────────────────────────────────────────────────────────────

const _srcState = {
    activePanel:   null,
    pollIntervals: {},
    stats:         {},
};

let _loadedCampaigns = [];

// ─── Init ─────────────────────────────────────────────────────────────────────

function sourcesInit() {
    sourcesLoadStats();
    sourcesCheckRunning();
    sourcesLoadAutoSettings();
    sourcesLoadCampaigns();
}

// ─── Automatisation ───────────────────────────────────────────────────────────

async function sourcesLoadAutoSettings() {
    try {
        const r = await fetch('/api/settings/sources');
        const d = await r.json();
        if (d.error) return;
        
        const sources = ['maps', 'ads', 'ecom'];
        sources.forEach(s => {
            const toggle = document.getElementById(`src-toggle-${s}-auto`);
            const quota = document.getElementById(`src-quota-${s}`);
            
            if (toggle) toggle.checked = d[`${s}_auto_scrape`] === '1';
            if (quota) quota.value = d[`${s}_daily_quota`] || (s === 'maps' ? 50 : 20);
        });
    } catch (e) { console.error('[sources] load settings error', e); }
}

async function sourcesToggleAuto(source, enabled) {
    try {
        const key = `${source}_auto_scrape`;
        await fetch('/api/settings/sources', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ [key]: enabled ? '1' : '0' }),
        });
        showToast(`${source.toUpperCase()} auto ${enabled ? 'activé' : 'désactivé'}`, 'success');
    } catch (e) { showToast('Erreur réseau', 'error'); }
}

async function sourcesSaveQuota(source, value) {
    try {
        const key = `${source}_daily_quota`;
        await fetch('/api/settings/sources', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ [key]: value }),
        });
        showToast(`Quota ${source.toUpperCase()} mis à jour : ${value}`, 'info');
    } catch (e) { showToast('Erreur réseau', 'error'); }
}

// ─── Chargement des stats (compteurs leads par source) ────────────────────────

async function sourcesLoadStats() {
    try {
        let url = '/api/sources/stats';
        if (typeof _activeCampaignId !== 'undefined' && _activeCampaignId) {
            url += `?campaign_id=${_activeCampaignId}`;
        }
        const r = await fetch(url);
        const d = await r.json();
        if (d.error) return;
        _srcState.stats = d.stats || {};
        _renderSourceCards();
    } catch (e) {
        console.error('[sources] stats error', e);
    }
}

function _renderSourceCards() {
    Object.keys(_SOURCES).forEach(key => {
        const countEl = document.getElementById(`src-count-${key}`);
        if (countEl) {
            const n = _srcState.stats[key] || 0;
            countEl.textContent = `${n} lead${n !== 1 ? 's' : ''}`;
        }
    });
}

// ─── Vérification des scrapers en cours au chargement ─────────────────────────

async function sourcesCheckRunning() {
    const sniperSources = ['ads', 'fb_ads', 'tech', 'jobs'];
    for (const src of sniperSources) {
        const api = _SOURCES[src].statusApi;
        if (!api) continue;
        try {
            const r = await fetch(api);
            const d = await r.json();
            if (d.running) _setSourceRunning(src, true);
        } catch (e) { /* silencieux */ }
    }
}

// ─── Panneau slide-in ─────────────────────────────────────────────────────────

function sourcesOpenPanel(sourceKey) {
    const panel      = document.getElementById('sources-panel');
    const content    = document.getElementById('sources-panel-content');
    const titleEl    = document.getElementById('sources-panel-title');
    const src        = _SOURCES[sourceKey];
    if (!panel || !content || !src) return;

    _srcState.activePanel = sourceKey;

    if (titleEl) titleEl.textContent = src.label;

    content.innerHTML = _renderPanelForm(sourceKey);

    panel.style.transform = 'translateX(0)';
    const overlay = document.getElementById('sources-panel-overlay');
    if (overlay) { overlay.style.display = 'block'; }
}

function sourcesClosePanel() {
    const panel = document.getElementById('sources-panel');
    if (panel) panel.style.transform = 'translateX(100%)';
    const overlay = document.getElementById('sources-panel-overlay');
    if (overlay) { overlay.style.display = 'none'; }
    _srcState.activePanel = null;
}

// ─── Rendu du formulaire par source ──────────────────────────────────────────

function _renderPanelForm(key) {
    const forms = {
        maps:    _formMaps,
        ads:     _formAds,
        fb_ads:  _formFbAds,
        tech:    _formTech,
        jobs:    _formJobs,
        bodacc:  _formBodacc,
    };
    return (forms[key] || (() => '<p>Formulaire non disponible</p>'))();
}

function _renderSectorSelect(prefix, targetKwInputId) {
    const onchangeAttr = targetKwInputId ? `onchange="const sel=this.options[this.selectedIndex]; const kwIn=document.getElementById('${targetKwInputId}'); if(kwIn && sel.dataset.kw) { kwIn.value=sel.dataset.kw; }"` : "";
    return `
        <select id="sf-${prefix}-sector" ${onchangeAttr} style="width:100%; padding:8px 10px; border:1px solid var(--border); border-radius:6px; font-size:13px; background:var(--surface); color:var(--ink)">
            <option value="" data-kw="">— Choisir un secteur —</option>
            <optgroup label="⚒ Artisans / BTP">
                <option value="Plombier" data-kw="plombier">Plombier</option>
                <option value="Électricien" data-kw="électricien">Électricien</option>
                <option value="Menuisier" data-kw="menuisier">Menuisier</option>
                <option value="Peintre" data-kw="peintre bâtiment">Peintre en bâtiment</option>
                <option value="Maçon" data-kw="maçon">Maçon</option>
                <option value="Couvreur" data-kw="couvreur">Couvreur</option>
                <option value="Carreleur" data-kw="carreleur">Carreleur</option>
                <option value="Chauffagiste" data-kw="chauffagiste">Chauffagiste</option>
                <option value="Serrurier" data-kw="serrurier">Serrurier</option>
                <option value="Architecte" data-kw="architecte">Architecte</option>
                <option value="Paysagiste" data-kw="paysagiste">Paysagiste / Jardinier</option>
                <option value="Climatisation" data-kw="climatisation installation">Climatisation / Froid</option>
            </optgroup>
            <optgroup label="🏥 Santé / Bien-être">
                <option value="Kinésithérapeute" data-kw="kinésithérapeute">Kinésithérapeute</option>
                <option value="Ostéopathe" data-kw="ostéopathe">Ostéopathe</option>
                <option value="Naturopathe" data-kw="naturopathe">Naturopathe</option>
                <option value="Psychologue" data-kw="psychologue">Psychologue</option>
                <option value="Dentiste" data-kw="dentiste">Dentiste</option>
                <option value="Infirmier" data-kw="infirmier libéral">Infirmier libéral</option>
                <option value="Médecin" data-kw="médecin généraliste">Médecin généraliste</option>
                <option value="Podologue" data-kw="podologue">Podologue</option>
            </optgroup>
            <optgroup label="💅 Beauté / Coiffure">
                <option value="Coiffeur" data-kw="coiffeur">Coiffeur / Salon de coiffure</option>
                <option value="Esthéticienne" data-kw="esthéticienne">Esthéticienne</option>
                <option value="Massage" data-kw="salon massage">Salon de massage</option>
                <option value="Onglerie" data-kw="onglerie nail art">Onglerie</option>
                <option value="Barbier" data-kw="barbier">Barbier</option>
            </optgroup>
            <optgroup label="⚖️ Professions libérales">
                <option value="Avocat" data-kw="avocat">Avocat</option>
                <option value="Expert-comptable" data-kw="expert-comptable">Expert-comptable</option>
                <option value="Notaire" data-kw="notaire">Notaire</option>
                <option value="Huissier" data-kw="huissier de justice">Huissier de justice</option>
                <option value="Conseiller financier" data-kw="conseiller financier">Conseiller financier</option>
            </optgroup>
            <optgroup label="📣 Services aux entreprises">
                <option value="Agence communication" data-kw="agence communication">Agence de communication</option>
                <option value="Agence immobilière" data-kw="agence immobilière">Agence immobilière</option>
                <option value="Consultant" data-kw="consultant">Consultant</option>
                <option value="Coach" data-kw="coach professionnel">Coach</option>
                <option value="Formation" data-kw="centre de formation">Organisme de formation</option>
                <option value="Traducteur" data-kw="traducteur interprète">Traducteur</option>
                <option value="Comptable" data-kw="cabinet comptable">Cabinet comptable</option>
            </optgroup>
            <optgroup label="🚗 Auto / Transport">
                <option value="Garagiste" data-kw="garage automobile">Garagiste</option>
                <option value="Carrossier" data-kw="carrosserie auto">Carrossier</option>
                <option value="Auto-école" data-kw="auto-école">Auto-école</option>
                <option value="Déménageur" data-kw="déménageur">Déménageur</option>
                <option value="Taxi" data-kw="taxi vtc">Taxi / VTC</option>
            </optgroup>
            <optgroup label="📸 Numérique / Créatif">
                <option value="Photographe" data-kw="photographe">Photographe</option>
                <option value="Vidéaste" data-kw="vidéaste">Vidéaste</option>
                <option value="Graphiste" data-kw="graphiste">Graphiste</option>
                <option value="Web designer" data-kw="web designer">Web designer</option>
            </optgroup>
            <optgroup label="🎓 Éducation / Sport">
                <option value="Auto-école" data-kw="auto-école">Auto-école</option>
                <option value="Soutien scolaire" data-kw="soutien scolaire">Soutien scolaire</option>
                <option value="Salle de sport" data-kw="salle de sport fitness">Salle de sport / Fitness</option>
                <option value="Coach sportif" data-kw="coach sportif">Coach sportif</option>
                <option value="Yoga" data-kw="yoga pilates">Yoga / Pilates</option>
                <option value="École de danse" data-kw="école de danse">École de danse</option>
            </optgroup>
            <optgroup label="🛒 Commerce local">
                <option value="Fleuriste" data-kw="fleuriste">Fleuriste</option>
                <option value="Bijouterie" data-kw="bijouterie">Bijouterie</option>
                <option value="Boulangerie" data-kw="boulangerie pâtisserie">Boulangerie / Pâtisserie</option>
                <option value="Traiteur" data-kw="traiteur">Traiteur</option>
                <option value="Opticien" data-kw="opticien">Opticien</option>
                <option value="Librairie" data-kw="librairie">Librairie</option>
            </optgroup>
            <option value="Autre" data-kw="">Autre (saisir manuellement)</option>
        </select>
    `;
}

function _formMaps() {
    return `
    <div class="src-form">
        <div class="src-form-row">
            <label>Secteur / Niche</label>
            ${_renderSectorSelect('maps', 'sf-maps-kw')}
        </div>
        <div class="src-form-row">
            <label>Mot-clé Google Maps</label>
            <input id="sf-maps-kw" type="text" placeholder="hôtel, restaurant, salon..." class="inp">
        </div>
        <div class="src-form-row">
            <label>Ville</label>
            <input id="sf-maps-city" type="text" placeholder="Cotonou, Porto-Novo, Paris..." class="inp">
        </div>
        <div class="src-form-row" style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div>
                <label>Nombre de leads</label>
                <input id="sf-maps-limit" type="number" value="20" min="1" max="200" class="inp">
            </div>
            <div>
                <label>Emails min.</label>
                <input id="sf-maps-min-emails" type="number" value="5" min="0" class="inp">
            </div>
        </div>
        <div class="src-form-row" style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div>
                <label>Pays</label>
                <select id="sf-maps-country" class="inp" onchange="_mapsCountryChange(this.value)">
                    <option value="fr">🇫🇷 France</option>
                    <option value="bj">🇧🇯 Bénin</option>
                </select>
            </div>
            <div>
                <label>Nb. passes max</label>
                <input id="sf-maps-max-passes" type="number" value="30" min="5" max="100" class="inp">
            </div>
        </div>
        <div style="display:flex;gap:12px;margin-top:4px;flex-wrap:wrap">
            <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer">
                <input type="checkbox" id="sf-maps-multi" checked> Multi-zones
            </label>
            <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer">
                <input type="checkbox" id="sf-maps-require-contact" checked> Avec tél. ou email uniquement
            </label>
            <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer">
                <input type="checkbox" id="sf-maps-variants" checked> Variantes LLM (mots-clés)
            </label>
        </div>
        <div class="src-form-row" style="margin-top:8px">
            <label>Filtrer par site web</label>
            <select id="sf-maps-site-filter" class="inp">
                <option value="all">Tous (avec et sans site)</option>
                <option value="without_site" selected>Sans site uniquement</option>
                <option value="with_site">Avec site uniquement</option>
            </select>
        </div>
        <div id="sf-maps-log" class="src-log" style="display:none"></div>
        <div class="src-form-actions">
            <button class="btn accent" onclick="sourcesLaunch('maps')">Lancer Maps</button>
        </div>
    </div>`;
}

function _formAds() {
    return `
    <div class="src-form">
        <div class="src-form-row">
            <label>Secteur / Niche</label>
            ${_renderSectorSelect('ads', 'sf-ads-kw')}
        </div>
        <div class="src-form-row">
            <label>Mots-clés (un par ligne ou séparés par virgule)</label>
            <textarea id="sf-ads-kw" rows="4" class="inp" placeholder="avocat paris\nplombier lyon\nclimatisation installation"></textarea>
        </div>
        <div class="src-form-row">
            <label>Ville ciblée (Optionnelle — s'ajoute automatiquement au mot-clé)</label>
            <input id="sf-ads-city" type="text" class="inp" placeholder="Paris, Lyon, Marseille...">
        </div>
        <div class="src-form-row" style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div>
                <label>Pays</label>
                <select id="sf-ads-country" class="inp">
                    <option value="fr">France</option>
                    <option value="be">Belgique</option>
                    <option value="ch">Suisse</option>
                    <option value="lu">Luxembourg</option>
                </select>
            </div>
            <div>
                <label>Max leads / mot-clé</label>
                <input id="sf-ads-max" type="number" value="50" min="5" max="200" class="inp">
            </div>
        </div>
        <div class="src-form-row">
            <label style="display:flex;align-items:center;gap:8px;font-size:12px;cursor:pointer">
                <input type="checkbox" id="sf-ads-batch">
                Utiliser le batch du jour (mots-clés pré-sélectionnés)
            </label>
        </div>
        <div class="src-form-row" style="background:var(--surface2,#1e1e2e);border-radius:8px;padding:10px 12px">
            <label style="display:flex;align-items:center;gap:8px;font-size:12px;cursor:pointer;margin-bottom:0">
                <input type="checkbox" id="sf-ads-rotation" onchange="_adsRotationToggle(this.checked)">
                <span>🔄 Rotation de villes <span style="font-weight:400;color:var(--ink3)">(continue sur d'autres villes jusqu'au quota)</span></span>
            </label>
            <div id="sf-ads-rotation-opts" style="display:none;margin-top:8px">
                <label style="font-size:11px;color:var(--ink3);margin-bottom:3px;display:block">Leads min. à atteindre</label>
                <input id="sf-ads-min-leads" type="number" value="20" min="1" max="500" class="inp" style="width:110px">
            </div>
        </div>
        <div id="sf-ads-log" class="src-log" style="display:none"></div>
        <div class="src-form-actions">
            <button class="btn accent" onclick="sourcesLaunch('ads')">Lancer Ads</button>
            <button class="btn bg2 sm" onclick="sniperStop('ads')" style="color:#ef4444">⏹ Stop</button>
        </div>
    </div>`;
}

function _adsRotationToggle(enabled) {
    const opts = document.getElementById('sf-ads-rotation-opts');
    if (opts) opts.style.display = enabled ? 'block' : 'none';
}

function _formFbAds() {
    return `
    <div class="src-form">
        <div class="src-form-row">
            <label>Secteur / Niche</label>
            ${_renderSectorSelect('fb_ads', 'sf-fb_ads-terms')}
        </div>
        <div class="src-form-row">
            <label>Termes de recherche <span style="font-weight:400;color:var(--ink3)">(un par ligne)</span></label>
            <textarea id="sf-fb_ads-terms" rows="4" class="inp"
                placeholder="agence immobilière\ncoach sportif\nplombier paris"></textarea>
        </div>
        <div class="src-form-row">
            <label>Ville ciblée <span style="font-weight:400;color:var(--ink3)">(optionnelle)</span></label>
            <input id="sf-fb_ads-city" type="text" class="inp" placeholder="Paris, Lyon, Marseille...">
        </div>
        <div class="src-form-row" style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div>
                <label>Pays</label>
                <select id="sf-fb_ads-country" class="inp">
                    <option value="FR">🇫🇷 France</option>
                    <option value="BE">🇧🇪 Belgique</option>
                    <option value="CH">🇨🇭 Suisse</option>
                    <option value="CA">🇨🇦 Canada (FR)</option>
                    <option value="LU">🇱🇺 Luxembourg</option>
                </select>
            </div>
            <div>
                <label>Pages max / mot-clé</label>
                <input id="sf-fb_ads-pages" type="number" value="3" min="1" max="20" class="inp">
            </div>
        </div>
        <div id="sf-fb_ads-log" class="src-log" style="display:none"></div>
        <div class="src-form-actions">
            <button class="btn accent" onclick="sourcesLaunch('fb_ads')"
                    style="background:#1877f2;border-color:#1877f2">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style="vertical-align:-1px;margin-right:4px"><path d="M5 3l14 9-14 9V3z"/></svg>
                Lancer FB Ads
            </button>
            <button class="btn bg2 sm" onclick="sniperStop('fb_ads')" style="color:#ef4444">⏹ Stop</button>
        </div>
    </div>`;
}

function _formTech() {
    return `
    <div class="src-form">
        <div class="src-form-row">
            <label>Secteur / Niche</label>
            ${_renderSectorSelect('tech', 'sf-tech-kw')}
        </div>
        <div class="src-form-row">
            <label>Mots-clés E-commerce (séparés par virgule, vide = défaut)</label>
            <textarea id="sf-tech-kw" rows="3" class="inp" placeholder="boutique vêtements, bijoux fantaisie..."></textarea>
        </div>
        <div class="src-form-row">
            <label>Ville ciblée (Optionnel — permet d'avoir des résultats locaux sans VPN)</label>
            <input id="sf-tech-city" type="text" class="inp" placeholder="Paris, Lyon, Marseille...">
        </div>
        <div class="src-form-row">
            <label>Max leads à insérer</label>
            <input id="sf-tech-max" type="number" value="50" min="5" max="300" class="inp">
        </div>
        <div id="sf-tech-log" class="src-log" style="display:none"></div>
        <div class="src-form-actions">
            <button class="btn accent" onclick="sourcesLaunch('tech')">Lancer Tech/E-com</button>
            <button class="btn bg2 sm" onclick="sniperStop('tech')" style="color:#ef4444">⏹ Stop</button>
        </div>
    </div>`;
}

function _formJobs() {
    return `
    <div class="src-form">
        <div class="src-form-row">
            <label>Secteur / Niche</label>
            ${_renderSectorSelect('jobs', 'sf-jobs-kw')}
        </div>
        <div class="src-form-row">
            <label>Mots-clés RH (optionnel — vide = 12 par défaut)</label>
            <textarea id="sf-jobs-kw" rows="3" class="inp" placeholder="développeur web\nresponsable marketing"></textarea>
        </div>
        <div class="src-form-row">
            <label>Ville ciblée (Optionnelle — s'ajoute automatiquement au mot-clé)</label>
            <input id="sf-jobs-city" type="text" class="inp" placeholder="Paris, Lyon, Marseille...">
        </div>
        <div class="src-form-row" style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div>
                <label>Jours en arrière</label>
                <input id="sf-jobs-days" type="number" value="7" min="1" max="30" class="inp">
            </div>
            <div>
                <label>Max leads</label>
                <input id="sf-jobs-max" type="number" value="50" min="5" max="200" class="inp">
            </div>
        </div>
        <div id="sf-jobs-log" class="src-log" style="display:none"></div>
        <div class="src-form-actions">
            <button class="btn accent" onclick="sourcesLaunch('jobs')">Lancer Jobs</button>
            <button class="btn bg2 sm" onclick="sniperStop('jobs')" style="color:#ef4444">⏹ Stop</button>
        </div>
    </div>`;
}

function _formBodacc() {
    const yesterday = new Date(Date.now() - 864e5).toISOString().split('T')[0];
    return `
    <div class="src-form">
        <div class="src-form-row">
            <label>Date à scanner (vide = hier)</label>
            <input id="sf-bodacc-date" type="date" value="${yesterday}" class="inp">
        </div>
        <p style="font-size:12px;color:var(--ink3);margin:4px 0 12px">
            Scanne les nominations de dirigeants publiées au BODACC (Journal officiel des annonces commerciales).
        </p>
        <div id="sf-bodacc-log" class="src-log" style="display:none"></div>
        <div class="src-form-actions">
            <button class="btn accent" onclick="sourcesLaunch('bodacc')">Scanner BODACC</button>
        </div>
    </div>`;
}

// ─── Lancement ────────────────────────────────────────────────────────────────

async function sourcesLaunch(key) {
    const launchers = {
        maps:   _launchMaps,
        ads:    _launchAds,
        fb_ads: _launchFbAds,
        tech:   _launchTech,
        jobs:   _launchJobs,
        bodacc: _launchBodacc,
    };
    const fn = launchers[key];
    if (!fn) return;
    _srcLog(key, 'Lancement en cours…');
    _setSourceRunning(key, true);
    try {
        await fn();
    } catch (e) {
        _srcLog(key, `Erreur : ${e.message}`);
        _setSourceRunning(key, false);
    }
}

async function _launchMaps() {
    const kw      = document.getElementById('sf-maps-kw')?.value?.trim();
    const city    = document.getElementById('sf-maps-city')?.value?.trim() || '';
    const sector  = document.getElementById('sf-maps-sector')?.value || '';
    const limit   = parseInt(document.getElementById('sf-maps-limit')?.value) || 20;
    const minMails= parseInt(document.getElementById('sf-maps-min-emails')?.value) || 0;
    const country = document.getElementById('sf-maps-country')?.value || 'fr';
    const requireContact = document.getElementById('sf-maps-require-contact')?.checked || false;
    const keywordVariants = document.getElementById('sf-maps-variants')?.checked || false;
    const multiZone = document.getElementById('sf-maps-multi')?.checked || false;
    const siteFilter = document.getElementById('sf-maps-site-filter')?.value || 'all';
    if (!kw) { _srcLog('maps', '⚠ Mot-clé requis'); _setSourceRunning('maps', false); return; }

    const r = await fetch('/api/scraper/launch', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ keyword: kw, city, sector, limit, min_emails: minMails, country, require_contact: requireContact, keyword_variants: keywordVariants, multi_zone: multiZone, site_filter: siteFilter }),
    });
    const d = await r.json();
    if (d.error) { _srcLog('maps', `✗ ${d.error}`); _setSourceRunning('maps', false); return; }
    _srcLog('maps', `✓ Campagne #${d.campaign_id} lancée — ${kw} · ${city} · ${country === 'bj' ? 'Bénin' : 'France'}`);
    _srcPollUntilDone('maps', '/api/scraper/status');
}

async function _launchAds() {
    const useBatch   = document.getElementById('sf-ads-batch')?.checked;
    const country    = document.getElementById('sf-ads-country')?.value || 'fr';
    const maxPer     = parseInt(document.getElementById('sf-ads-max')?.value) || 50;
    const city       = document.getElementById('sf-ads-city')?.value || '';
    const rotation   = document.getElementById('sf-ads-rotation')?.checked || false;
    const minLeads   = rotation ? (parseInt(document.getElementById('sf-ads-min-leads')?.value) || maxPer) : 0;
    const secteur    = document.getElementById('sf-ads-sector')?.value || '';
    let   keywords   = [];

    if (useBatch) {
        const r = await fetch(`/api/sniper/daily-batch?n=10`);
        const d = await r.json();
        keywords = d.keywords || [];
    } else {
        const raw = document.getElementById('sf-ads-kw')?.value || '';
        keywords  = raw.split(/[\n,]+/).map(k => k.trim()).filter(Boolean);
    }
    if (!keywords.length) { _srcLog('ads', '⚠ Entrer au moins un mot-clé'); _setSourceRunning('ads', false); return; }

    const body = { keywords, country, max_per_kw: maxPer, min_leads: minLeads, secteur };
    if (city.trim()) body.city = city.trim();

    if (rotation) {
        _srcLog('ads', `🔄 Rotation de villes activée — objectif ${minLeads} leads`);
    }

    const r = await fetch('/api/sniper/launch', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    const d = await r.json();
    if (d.error) { _srcLog('ads', `✗ ${d.error}`); _setSourceRunning('ads', false); return; }
    _srcLog('ads', `✓ Pipeline lancé — ${keywords.length} mot(s)-clé(s)${rotation ? ` · rotation villes (min ${minLeads})` : ''}`);
    _srcPollUntilDone('ads', '/api/sniper/status');
}

async function _launchFbAds() {
    const raw     = document.getElementById('sf-fb_ads-terms')?.value || '';
    const terms   = raw.split(/[\n,]+/).map(k => k.trim()).filter(Boolean);
    const country = document.getElementById('sf-fb_ads-country')?.value || 'FR';
    const city    = document.getElementById('sf-fb_ads-city')?.value?.trim() || '';
    const pages   = parseInt(document.getElementById('sf-fb_ads-pages')?.value) || 3;
    const secteur = document.getElementById('sf-fb_ads-sector')?.value || '';

    if (!terms.length) {
        _srcLog('fb_ads', '⚠ Entrer au moins un terme de recherche');
        _setSourceRunning('fb_ads', false);
        return;
    }

    // Ajouter la ville aux termes si renseignée
    const search_terms = city
        ? terms.map(t => `${t} ${city}`)
        : terms;

    const r = await fetch('/api/sniper/fb-ads-scan', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ search_terms, country, max_pages: pages, secteur }),
    });
    const d = await r.json();
    if (d.error) {
        _srcLog('fb_ads', `✗ ${d.error}`);
        _setSourceRunning('fb_ads', false);
        return;
    }
    _srcLog('fb_ads', `✓ FB Ads lancé — ${search_terms.length} terme(s), pays=${country}`);
    _srcPollUntilDone('fb_ads', '/api/sniper/fb-ads-status');
}

async function _launchTech() {
    const rawKw   = document.getElementById('sf-tech-kw')?.value || '';
    const city    = document.getElementById('sf-tech-city')?.value || '';
    const maxL    = parseInt(document.getElementById('sf-tech-max')?.value) || 50;
    const secteur = document.getElementById('sf-tech-sector')?.value || '';
    const body    = { max_leads: maxL, secteur };
    
    if (rawKw.trim()) {
        body.keywords = rawKw.split(/[\n,]+/).map(k => k.trim()).filter(Boolean);
    }
    if (city.trim()) {
        body.city = city.trim();
    }

    const r = await fetch('/api/sniper/tech-scan', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    const d = await r.json();
    if (d.error || !d.ok) { _srcLog('tech', `✗ ${d.error || d.message}`); _setSourceRunning('tech', false); return; }
    _srcLog('tech', `✓ Tech/E-com lancé — max ${maxL} leads`);
    _srcPollUntilDone('tech', '/api/sniper/tech-status');
}

async function _launchJobs() {
    const raw   = document.getElementById('sf-jobs-kw')?.value || '';
    const city  = document.getElementById('sf-jobs-city')?.value || '';
    const days  = parseInt(document.getElementById('sf-jobs-days')?.value) || 7;
    const maxL  = parseInt(document.getElementById('sf-jobs-max')?.value) || 50;
    const secteur = document.getElementById('sf-jobs-sector')?.value || '';
    const body  = { max_leads: maxL, days_back: days, secteur };
    
    if (raw.trim()) body.keywords = raw.split(/[\n,]+/).map(k => k.trim()).filter(Boolean);
    if (city.trim()) body.city = city.trim();

    const r = await fetch('/api/sniper/jobs-scan', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    const d = await r.json();
    if (d.error || !d.ok) { _srcLog('jobs', `✗ ${d.error || d.message}`); _setSourceRunning('jobs', false); return; }
    _srcLog('jobs', `✓ Jobs lancé — ${days}j en arrière, max ${maxL} leads`);
    _srcPollUntilDone('jobs', '/api/sniper/jobs-status');
}

async function _launchBodacc() {
    const date = document.getElementById('sf-bodacc-date')?.value || '';
    const body = date ? { date } : {};

    const r = await fetch('/api/sniper/bodacc-scan', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    const d = await r.json();
    if (d.error) { _srcLog('bodacc', `✗ ${d.error}`); _setSourceRunning('bodacc', false); return; }
    _srcLog('bodacc', `✓ Scan terminé (${d.date}) — ${d.inserted || 0} nouveaux leads`);
    _setSourceRunning('bodacc', false);
    sourcesLoadStats();
}

// ─── Polling statut ───────────────────────────────────────────────────────────

function _srcPollUntilDone(key, statusApi) {
    if (_srcState.pollIntervals[key]) clearInterval(_srcState.pollIntervals[key]);
    _srcState.pollIntervals[key] = setInterval(async () => {
        try {
            const r = await fetch(statusApi);
            const d = await r.json();
            if (d.logs) {
                const last3 = (d.logs || []).slice(-3).join('\n');
                _srcLog(key, last3, false);
            }
            if (!d.running) {
                clearInterval(_srcState.pollIntervals[key]);
                delete _srcState.pollIntervals[key];
                _setSourceRunning(key, false);
                _srcLog(key, '✓ Terminé');
                sourcesLoadStats();
            }
        } catch (e) {
            clearInterval(_srcState.pollIntervals[key]);
            _setSourceRunning(key, false);
        }
    }, 3000);
}

// ─── Helpers UI ───────────────────────────────────────────────────────────────

function _setSourceRunning(key, running) {
    const badge  = document.getElementById(`src-badge-${key}`);
    const dot    = document.getElementById(`src-dot-${key}`);
    if (badge) {
        badge.textContent = running ? 'En cours' : 'Inactif';
        badge.style.color = running ? '#f59e0b' : 'var(--ink3)';
    }
    if (dot) dot.style.background = running ? '#f59e0b' : '#9ca3af';
}

function _srcLog(key, msg, append = true) {
    // Les IDs suivent la convention sf-{key}-log (underscores préservés dans la clé)
    const logEl = document.getElementById(`sf-${key}-log`);
    if (!logEl) return;
    logEl.style.display = 'block';
    if (append) {
        logEl.textContent += (logEl.textContent ? '\n' : '') + msg;
    } else {
        logEl.textContent = msg;
    }
    logEl.scrollTop = logEl.scrollHeight;
}
async function sourcesLoadCampaigns() {
    const tbody = document.getElementById('sources-campaigns-tbody');
    if (!tbody) return;
    try {
        const r = await fetch('/api/campaigns');
        const d = await r.json();
        if (d.error) {
            tbody.innerHTML = `<tr><td colspan="7" style="padding:20px;text-align:center;color:#ef4444">${d.error}</td></tr>`;
            return;
        }
        const campaigns = Array.isArray(d) ? d : (d.campaigns || []);
        _loadedCampaigns = campaigns;
        const filtered = (typeof _activeCampaignId !== 'undefined' && _activeCampaignId)
            ? campaigns.filter(c => c.id == _activeCampaignId)
            : campaigns;
        if (!filtered.length) {
            tbody.innerHTML = `<tr><td colspan="7" style="padding:40px;text-align:center;color:var(--ink3)">Aucune campagne trouvée.</td></tr>`;
            return;
        }
        tbody.innerHTML = filtered.map(c => {
            const dateStr = c.date_creation ? new Date(c.date_creation).toLocaleDateString('fr-FR', {
                day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
            }) : '—';
            
            // Map source to nice badges
            const sourceMap = {
                'ads':      '<span class="badge sm" style="background:rgba(249,115,22,0.15);color:#f97316">Google ADS</span>',
                'fb_ads':   '<span class="badge sm" style="background:rgba(24,119,242,0.15);color:#1877f2">FB ads</span>',
                'tech':     '<span class="badge sm" style="background:rgba(139,92,246,0.15);color:#8b5cf6">Tech / E-com</span>',
                'ecom':     '<span class="badge sm" style="background:rgba(139,92,246,0.15);color:#8b5cf6">E-com</span>',
                'jobs':     '<span class="badge sm" style="background:rgba(6,182,212,0.15);color:#06b6d4">Jobs</span>',
                'bodacc':   '<span class="badge sm" style="background:rgba(16,185,129,0.15);color:#10b981">BODACC</span>',
                'maps':     '<span class="badge sm" style="background:rgba(66,133,244,0.15);color:#4285f4">Google Maps</span>'
            };
            const sourceBadge = sourceMap[c.source] || sourceMap[c.secteur] || `<span class="badge sm bg2">${c.source || c.secteur || '—'}</span>`;

            // ── Status badge ──
            const statusBadge = _campaignStatusBadge(c);

            // ── Actions ──
            const actions = _campaignActions(c);

            return `
                <tr style="border-bottom:1px solid var(--border);cursor:pointer;transition:background 0.2s" onmouseover="this.style.background='var(--surface2)'" onmouseout="this.style.background=''" onclick="openCampaignModal(${c.id})">
                    <td style="padding:12px 20px;font-weight:700">#${c.id}</td>
                    <td style="padding:12px 20px">
                        <div style="font-weight:600">${c.nom || 'Sans nom'}</div>
                        ${c.error_message ? `<div style="font-size:10px;color:#ef4444;margin-top:2px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${(c.error_message || '').replace(/"/g,'&quot;')}">${c.error_message}</div>` : ''}
                    </td>
                    <td style="padding:12px 20px">${sourceBadge}</td>
                    <td style="padding:12px 20px;color:var(--ink3);font-size:11px">${dateStr}</td>
                    <td style="padding:12px 20px;font-weight:700">${c.leads_total || 0}</td>
                    <td style="padding:12px 20px">${statusBadge}</td>
                    <td style="padding:12px 20px;text-align:right;white-space:nowrap" onclick="event.stopPropagation()">${actions}</td>
                </tr>
            `;
        }).join('');
    } catch (e) {
        console.error('[sources] campaigns load error', e);
        tbody.innerHTML = `<tr><td colspan="7" style="padding:20px;text-align:center;color:#ef4444">Erreur de chargement des campagnes.</td></tr>`;
    }
}

function _campaignStatusBadge(c) {
    const phase = c.phase || 'pending';
    const map = {
        'pending':     { bg: 'rgba(156,163,175,0.15)', color: '#9ca3af', icon: '⏳', label: 'En attente' },
        'scraping':    { bg: 'rgba(249,115,22,0.15)',   color: '#f97316', icon: '⚙️', label: 'Scraping' },
        'enrichment':  { bg: 'rgba(139,92,246,0.15)',   color: '#8b5cf6', icon: '🔍', label: 'Enrichissement' },
        'audit':       { bg: 'rgba(59,130,246,0.15)',    color: '#3b82f6', icon: '📋', label: 'Audit' },
        'email_gen':   { bg: 'rgba(6,182,212,0.15)',     color: '#06b6d4', icon: '✉️', label: 'Emails' },
        'done':        { bg: 'rgba(16,185,129,0.15)',    color: '#10b981', icon: '✅', label: 'Terminé' },
        'failed':      { bg: 'rgba(239,68,68,0.15)',     color: '#ef4444', icon: '❌', label: 'Erreur' },
        'stopped':     { bg: 'rgba(245,158,11,0.15)',    color: '#f59e0b', icon: '⏸', label: 'Arrêté' },
    };
    const s = map[phase] || map['pending'];
    let label = s.label;
    // Ajouter le détail de la phase où ça s'est arrêté
    if ((phase === 'failed' || phase === 'stopped') && c.error_message) {
        const phaseMatch = c.error_message.match(/^\[(\w+)\]/);
        if (phaseMatch) {
            const phaseLabels = { scraping: 'Scraping', enrichment: 'Enrichissement', audit: 'Audit', email_gen: 'Emails' };
            label += ` · ${phaseLabels[phaseMatch[1]] || phaseMatch[1]}`;
        }
    }
    return `<span style="display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;background:${s.bg};color:${s.color}">${s.icon} ${label}</span>`;
}

function _campaignActions(c) {
    const phase = c.phase || 'done';
    const btns = [];

    if (phase === 'failed' || phase === 'stopped') {
        btns.push(`<button class="btn sm" style="background:rgba(16,185,129,0.15);color:#10b981;border:1px solid rgba(16,185,129,0.3);font-size:11px;padding:4px 10px;border-radius:6px;cursor:pointer;font-weight:600" onclick="campaignResume(${c.id})" title="Reprendre là où ça s'est arrêté">▶ Continuer</button>`);
        btns.push(`<button class="btn sm" style="background:rgba(59,130,246,0.15);color:#3b82f6;border:1px solid rgba(59,130,246,0.3);font-size:11px;padding:4px 10px;border-radius:6px;cursor:pointer;font-weight:600" onclick="campaignRestart(${c.id})" title="Relancer de zéro">🔄</button>`);
        btns.push(`<button class="btn sm" style="background:rgba(239,68,68,0.1);color:#ef4444;border:1px solid rgba(239,68,68,0.25);font-size:11px;padding:4px 10px;border-radius:6px;cursor:pointer;font-weight:600" onclick="campaignAbandon(${c.id})" title="Abandonner définitivement">❌</button>`);
    }

    if (phase === 'done' || phase === 'stopped') {
        btns.push(`<button class="btn sm" style="background:rgba(239,68,68,0.08);color:#ef4444;border:1px solid rgba(239,68,68,0.2);font-size:11px;padding:4px 8px;border-radius:6px;cursor:pointer" onclick="campaignDelete(${c.id})" title="Supprimer la campagne">🗑</button>`);
    }

    return btns.join(' ') || '<span style="color:var(--ink3);font-size:11px">—</span>';
}

async function campaignResume(id) {
    if (!await showConfirm('Reprendre cette campagne là où elle s\'est arrêtée ?', { title: 'Reprise campagne' })) return;
    try {
        const r = await fetch(`/api/campaigns/${id}/resume`, { method: 'POST' });
        const d = await r.json();
        if (d.error) { showToast(d.error, 'error'); return; }
        showToast('Campagne reprise !', 'success');
        sourcesLoadCampaigns();
    } catch (e) { showToast('Erreur réseau', 'error'); }
}

async function campaignRestart(id) {
    if (!await showConfirm('Relancer cette campagne de zéro ? Les leads existants seront supprimés.', { title: 'Relance campagne', danger: true })) return;
    try {
        const r = await fetch(`/api/campaigns/${id}/restart`, { method: 'POST' });
        const d = await r.json();
        if (d.error) { showToast(d.error, 'error'); return; }
        showToast('Campagne relancée de zéro !', 'success');
        sourcesLoadCampaigns();
    } catch (e) { showToast('Erreur réseau', 'error'); }
}

async function campaignAbandon(id) {
    if (!await showConfirm('Abandonner définitivement cette campagne ?', { title: 'Abandon', danger: true })) return;
    try {
        const r = await fetch(`/api/campaigns/${id}/abandon`, { method: 'POST' });
        const d = await r.json();
        if (d.error) { showToast(d.error, 'error'); return; }
        showToast('Campagne abandonnée', 'info');
        sourcesLoadCampaigns();
    } catch (e) { showToast('Erreur réseau', 'error'); }
}

async function campaignDelete(id) {
    if (!await showConfirm('Supprimer cette campagne ? Les leads ne seront pas supprimés.', { title: 'Suppression', danger: true })) return;
    try {
        const r = await fetch(`/api/campaigns/${id}`, { method: 'DELETE' });
        const d = await r.json();
        if (d.error) { showToast(d.error, 'error'); return; }
        showToast('Campagne supprimée', 'info');
        sourcesLoadCampaigns();
    } catch (e) { showToast('Erreur réseau', 'error'); }
}

// ─── Modal de Campagne (Récapitulatif) ────────────────────────────────────────

function openCampaignModal(id) {
    const c = _loadedCampaigns.find(camp => camp.id === id);
    if (!c) return;

    document.getElementById('campaign-modal-title').textContent = `Campagne #${c.id} - ${c.nom || 'Sans nom'}`;
    
    let progressHtml = '';
    if (c.progress && Object.keys(c.progress).length > 0) {
        progressHtml = `
            <div style="margin-top:15px;padding:12px;background:var(--bg);border-radius:8px;font-family:monospace;font-size:12px;color:var(--ink2);">
                <div><strong>Leads:</strong> ${c.progress.processed || c.leads_total || 0} / ${c.progress.total || c.nb_demande || 0}</div>
                <div><strong>Emails:</strong> ${c.progress.emails_found || c.leads_with_email || 0}</div>
                ${c.progress.phase_detail ? `<div style="margin-top:8px;color:var(--primary)">${c.progress.phase_detail}</div>` : ''}
            </div>
        `;
    }

    const sourceMapText = {
        'ads': 'Google ADS',
        'fb_ads': 'FB ads',
        'tech': 'Tech / E-com',
        'ecom': 'E-com',
        'jobs': 'Jobs',
        'bodacc': 'BODACC',
        'maps': 'Google Maps',
        'sniper_ads': 'Google ADS',
        'sniper_fb': 'FB ads',
        'sniper_ecom': 'E-com',
    };
    const realSource = sourceMapText[c.source] || sourceMapText[c.secteur] || c.source || c.secteur || 'Inconnu';

    document.getElementById('campaign-modal-content').innerHTML = `
        <div style="display:flex;flex-direction:column;gap:12px;font-size:13px;">
            <div style="display:flex;gap:10px;">
                <div style="flex:1"><strong>Source:</strong> ${realSource}</div>
                <div style="flex:1"><strong>Statut:</strong> ${_campaignStatusBadge(c)}</div>
            </div>
            <div style="display:flex;gap:10px;">
                <div style="flex:1"><strong>Secteur/Mot-clé:</strong> ${c.secteur || '—'}</div>
                <div style="flex:1"><strong>Ville:</strong> ${c.ville || '—'}</div>
            </div>
            
            <div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--border);display:grid;grid-template-columns:repeat(2, 1fr);gap:10px;">
                <div><strong>Demande:</strong> ${c.nb_demande || 0} leads</div>
                <div><strong>Leads récoltés:</strong> ${c.leads_total || 0}</div>
                <div><strong>Leads avec Email:</strong> ${c.leads_with_email || 0}</div>
                <div><strong>Leads audités:</strong> ${c.nb_audites || 0}</div>
                <div><strong>Emails envoyés:</strong> ${c.emails_envoyes || 0}</div>
            </div>
            
            ${c.error_message ? `<div style="margin-top:10px;padding:10px;background:rgba(239,68,68,0.1);color:#ef4444;border-radius:8px;font-size:12px;"><strong>Erreur:</strong> ${c.error_message}</div>` : ''}
            ${progressHtml}
        </div>
        <div style="margin-top:20px;display:flex;gap:10px;justify-content:flex-end;">
            ${_campaignActions(c)}
        </div>
    `;

    document.getElementById('campaign-modal-overlay').style.display = 'block';
    document.getElementById('campaign-modal').style.display = 'flex';
}

function closeCampaignModal() {
    document.getElementById('campaign-modal-overlay').style.display = 'none';
    document.getElementById('campaign-modal').style.display = 'none';
}

