        // Global variables
        let _selectedLeadId = null;
        let _campaignData = [];
        let _trackingBoardFilter = 'tous';
        let _trackingBoardSearchResults = [];
        let _trackingBoardSelectedLeadId = null;
        let _trackingBoardSelectedLeadName = null;
        
        // Mobile sidebar toggle
        function toggleSidebar() {
            document.querySelector('.sb').classList.toggle('open');
            document.querySelector('.sb-overlay').classList.toggle('open');
        }
        
        // Navigation with localStorage persistence
        function nav(page, el) {
            console.log('Nav to:', page);

            // Handle subtab aliases
            let subtab = null;
            if (['sources', 'leads'].includes(page)) {
                subtab = page;
                page = 'campagne';
            } else if (['suivi', 'roi'].includes(page)) {
                subtab = page;
                page = 'tracking';
            }

            localStorage.setItem('pm_current_page', page);
            
            // Sync UI Active States
            document.querySelectorAll('.ni, .mobile-nav-item').forEach(n => n.classList.remove('active'));
            
            // Use subtab if available for UI highlighting, or the main page
            const highlightId = subtab || page;
            const desktopNav = document.getElementById('nav-' + highlightId) || document.getElementById('nav-' + page);
            if(desktopNav) desktopNav.classList.add('active');
            
            const mobileNavEl = document.getElementById('nav-' + highlightId + '-m') || document.getElementById('nav-' + page + '-m');
            if(mobileNavEl) mobileNavEl.classList.add('active');

            // Switch Section
            document.querySelectorAll('.v-section').forEach(s => s.classList.remove('active'));
            const target = document.getElementById('section-' + page);
            if(target) {
                target.classList.add('active');
                
                // If we have a subtab, activate it
                if (subtab) {
                    const tabBtn = target.querySelector(`.section-tab[onclick*="'${subtab}'"]`);
                    if (tabBtn) switchSectionTab(subtab, tabBtn);
                    else _loadDataForSection(page);
                } else {
                    _loadDataForSection(page);
                }
            }
            
            const titles = {
                cockpit: 'Cockpit', campagne: 'Campagnes', tracking: 'Tracking',
                planificateur: 'Planning', settings: 'Paramètres', sniper: 'Sniper B2B'
            };
            const displayTitle = (subtab === 'sources' ? 'Sources' : (titles[page] || page));
            document.getElementById('PT').textContent = displayTitle;
        }

        function _loadDataForSection(page) {
            if (page === 'cockpit') {
                if(typeof loadStats === 'function') loadStats();
                if(typeof loadCampaigns === 'function') loadCampaigns();
            } else if (page === 'campagne') {
                const activeTab = document.querySelector('#section-campagne .section-tab.active');
                if (activeTab) {
                    const tabName = activeTab.getAttribute('onclick').match(/'([^']+)'/)[1];
                    _loadDataForSubTab(tabName);
                }
            } else if (page === 'tracking') {
                const activeTab = document.querySelector('#section-tracking .section-tab.active');
                if (activeTab) {
                    const tabName = activeTab.getAttribute('onclick').match(/'([^']+)'/)[1];
                    _loadDataForSubTab(tabName);
                }
            } else if (page === 'settings') {
                const activeTab = document.querySelector('#section-settings .section-tab.active');
                if (activeTab) {
                    const tabName = activeTab.getAttribute('onclick').match(/'([^']+)'/)[1];
                    _loadDataForSubTab(tabName);
                }
            } else if (page === 'planificateur') {
                if (typeof initPlanificateur === 'function') initPlanificateur();
            } else if (page === 'sniper') {
                if (typeof sniperInit === 'function') sniperInit();
            }
        }

        function switchSectionTab(tabName, el) {
            const tabsContainer = el.closest('.section-tabs');
            const parentSection = tabsContainer.parentElement;
            
            // Update tabs UI
            tabsContainer.querySelectorAll('.section-tab').forEach(t => t.classList.remove('active'));
            el.classList.add('active');
            
            // Update content UI - Only hide direct child subtabs of the same parent
            // This allows nested tabs to work without hiding their own parent containers
            Array.from(parentSection.children).forEach(child => {
                if (child.classList.contains('subtab-content')) {
                    child.style.display = 'none';
                }
            });

            const targetContent = document.getElementById('subtab-' + tabName);
            if (targetContent) {
                targetContent.style.display = 'block';
                // Load data for the sub-tab
                _loadDataForSubTab(tabName);
            }
        }

        function _loadDataForSubTab(tabName) {
            console.log('Loading data for subtab:', tabName);
            if (tabName === 'leads') {
                if(typeof unifiedLeadsInit === 'function') unifiedLeadsInit();
                if (window.ActionsModule) ActionsModule.init();
            }
            if (tabName === 'sources') {
                if(typeof sourcesInit === 'function') sourcesInit();
            }
            if (['setting_profil', 'setting_api', 'setting_system'].includes(tabName)) {
                if(typeof loadSettings === 'function') loadSettings();
            }
            if (tabName === 'leads_unified') {
                if(typeof unifiedLeadsInit === 'function') unifiedLeadsInit();
                if (window.ActionsModule) ActionsModule.init();
            }
            if (tabName === 'suivi') {
                if(typeof loadCRM === 'function') loadCRM();
            }
            if (tabName === 'roi') {
                if(typeof loadRoiData === 'function') loadRoiData();
            }
            if (tabName === 'board') {
                if(typeof loadTrackingBoard === 'function') loadTrackingBoard();
                if(typeof searchTrackingLead === 'function') searchTrackingLead();
            }
            if (tabName === 'health') {
                if(typeof runHealthCheck === 'function') runHealthCheck();
            }
            // Templates doesn't always need init unless it's the first time
            if (tabName === 'templates') {
                if(typeof tmInit === 'function') tmInit();
            }
            if (tabName === 'logs') {
                if(typeof loadLogs === 'function') loadLogs();
            }
        }

        function setTrackingBoardFilter(filter, el) {
            _trackingBoardFilter = filter;
            document.querySelectorAll('#tracking-board-filters .btn').forEach(btn => {
                btn.classList.toggle('btn-primary', btn.dataset.filter === filter);
                btn.classList.toggle('btn-ghost', btn.dataset.filter !== filter);
            });
            loadTrackingBoard();
        }

        function searchTrackingLead() {
            const query = document.getElementById('tracking-lead-search')?.value.trim();
            const tbody = document.getElementById('tbody-tracking-search');
            const selectedLabel = document.getElementById('tracking-selected-lead');
            if (selectedLabel) selectedLabel.textContent = _trackingBoardSelectedLeadName ? `Lead sélectionné : ${_trackingBoardSelectedLeadName}` : 'Aucun lead sélectionné.';

            if (!query) {
                _trackingBoardSearchResults = [];
                if (tbody) tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:2rem">Saisissez un nom de lead pour commencer.</td></tr>';
                return;
            }

            if (tbody) tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:2rem">Recherche en cours...</td></tr>';
            fetch('/api/leads/all?search=' + encodeURIComponent(query) + '&limit=20')
                .then(r => r.json())
                .then(data => {
                    const leads = data.leads || [];
                    _trackingBoardSearchResults = leads;
                    if (tbody) tbody.innerHTML = leads.length ? leads.map(lead => `
                        <tr data-id="${lead.id}" class="${lead.id === _trackingBoardSelectedLeadId ? 'selected' : ''}" onclick="selectTrackingLead(${lead.id}, ${JSON.stringify(lead.nom || '')})" style="cursor:pointer">
                            <td>${escHtml(lead.nom || '—')}</td>
                            <td>${escHtml(lead.email || '—')}</td>
                            <td>${escHtml(lead.secteur || lead.category || '—')}</td>
                            <td>${escHtml(lead.statut || '—')}</td>
                        </tr>
                    `).join('') : '<tr><td colspan="4" style="text-align:center;padding:2rem">Aucun lead trouvé.</td></tr>';
                })
                .catch(error => {
                    console.error('Recherche lead impossible :', error);
                    if (tbody) tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:2rem;color:var(--red)">Erreur de recherche.</td></tr>';
                });
        }

        function selectTrackingLead(id, name) {
            _trackingBoardSelectedLeadId = id;
            _trackingBoardSelectedLeadName = name;
            const selectedLabel = document.getElementById('tracking-selected-lead');
            if (selectedLabel) selectedLabel.textContent = `Lead sélectionné : ${name}`;
            document.querySelectorAll('#tbody-tracking-search tr').forEach(row => {
                row.classList.toggle('selected', row.dataset.id === String(id));
            });
        }

        async function saveTrackingContact() {
            if (!_trackingBoardSelectedLeadId) {
                return showToast('Sélectionne d’abord un lead dans la liste.', 'error');
            }
            const channel = document.getElementById('tracking-channel-select')?.value || 'Email';
            const payload = { lead_id: _trackingBoardSelectedLeadId, channel };
            try {
                const response = await fetch('/api/crm/manual_contact', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || 'Erreur lors de l’enregistrement');
                }
                showToast('Contact manuel enregistré.', 'success');
                _trackingBoardSelectedLeadId = null;
                _trackingBoardSelectedLeadName = null;
                document.getElementById('tracking-selected-lead').textContent = 'Aucun lead sélectionné.';
                if (document.getElementById('tracking-lead-search')) document.getElementById('tracking-lead-search').value = '';
                searchTrackingLead();
                loadTrackingBoard();
            } catch (error) {
                console.error('saveTrackingContact:', error);
                showToast('Impossible d’enregistrer le contact : ' + error.message, 'error');
            }
        }

        function loadTrackingBoard(silent = false) {
            const statsSent = document.getElementById('board-stat-sent');
            const statsOpen = document.getElementById('board-stat-open');
            const statsClick = document.getElementById('board-stat-click');
            const statsReply = document.getElementById('board-stat-reply');
            const statsRdv = document.getElementById('board-stat-rdv');
            const tbody = document.getElementById('tbody-tracking-board');

            if (tbody && !silent) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem">Chargement...</td></tr>';
            }
            if (statsSent) statsSent.textContent = '—';
            if (statsOpen) statsOpen.textContent = '—';
            if (statsClick) statsClick.textContent = '—';
            if (statsReply) statsReply.textContent = '—';
            if (statsRdv) statsRdv.textContent = '—';

            const statusMap = {
                tous: '',
                ouverts: 'opened',
                cliques: 'clicked',
                repondus: 'replied',
                bounce: 'bounce',
                spam: 'spam'
            };

            const emailUrl = '/api/emails?limit=50' + (statusMap[_trackingBoardFilter] ? '&statut=' + statusMap[_trackingBoardFilter] : '');

            fetch('/api/crm/counts')
                .then(r => r.json())
                .then(counts => {
                    if (counts && !counts.error) {
                        if (statsSent) statsSent.textContent = counts.total_envoyes || 0;
                        if (statsOpen) statsOpen.textContent = counts.total_ouverts || 0;
                        if (statsClick) statsClick.textContent = counts.total_cliques || 0;
                        if (statsReply) statsReply.textContent = counts.total_repondus || 0;
                        if (statsRdv) statsRdv.textContent = counts.total_rdv || 0;
                    }
                })
                .catch(error => {
                    console.error('Erreur loading tracking counts:', error);
                });

            fetch(emailUrl)
                .then(r => r.json())
                .then(data => {
                    if (!data || data.error) {
                        if (tbody) {
                            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--red)">' + (data?.error || 'Erreur de chargement') + '</td></tr>';
                        }
                        return;
                    }
                    renderTrackingBoard(data.emails || []);
                })
                .catch(error => {
                    console.error('Erreur loading tracking board:', error);
                    if (tbody) {
                        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--red)">Erreur de chargement</td></tr>';
                    }
                });
        }

        function renderTrackingBoard(rows) {
            const tbody = document.getElementById('tbody-tracking-board');
            if (!tbody) return;
            if (!rows || rows.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--ink3)">Aucun email trouvé pour ce filtre.</td></tr>';
                return;
            }

            tbody.innerHTML = rows.map(item => {
                const prospect = item.nom || '—';
                const email = item.email_destinataire || '—';
                const objet = item.email_objet || '—';
                const date = formatDateShort(item.date_envoi);
                const tracking = [];
                if (item.ouvert) tracking.push('Ouvert');
                if (item.clique) tracking.push('Cliqué');
                if (item.repondu) tracking.push('Répondu');
                if (item.bounce) tracking.push('Bounce');
                if (item.spam) tracking.push('Spam');
                if (item.rdv_confirme) tracking.push('RDV');
                const channel = item.statut_envoi || '—';
                const trackingText = tracking.length ? tracking.join(' · ') : (channel && channel.toLowerCase() !== 'envoye' ? `Contact : ${channel}` : 'Envoyé');
                const rdv = item.rdv_confirme ? 'Oui' : 'Non';

                return `
                    <tr>
                        <td>${escHtml(prospect)}</td>
                        <td>${escHtml(email)}</td>
                        <td>${escHtml(objet)}</td>
                        <td>${escHtml(channel)}</td>
                        <td>${escHtml(trackingText)}</td>
                        <td>${escHtml(date)}</td>
                        <td>${escHtml(rdv)}</td>
                    </tr>`;
            }).join('');
        }

        function formatDateShort(dateString) {
            if (!dateString) return '—';
            const d = new Date(dateString);
            if (Number.isNaN(d.getTime())) return dateString;
            return d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: '2-digit' });
        }

        function getSavedPage() {
            const p = localStorage.getItem('pm_current_page') || 'cockpit';
            // Migrer les anciens onglets vers leurs nouveaux parents si besoin
            if (p === 'sources' || p === 'leads') return 'campagne';
            if (p === 'suivi' || p === 'roi') return 'tracking';
            return p;
        }
        
        function _resetAndLoad() { _campPage = 1; loadCampaignTable(); }

        // Campaign Table Functions
        let _campPage = 1;
        let _campTotalPages = 1;

        function changeCampaignPage(delta) {
            const newPage = _campPage + delta;
            if (newPage >= 1 && newPage <= _campTotalPages) {
                _campPage = newPage;
                loadCampaignTable();
            }
        }

        function goToCampaignPage(p) {
            _campPage = parseInt(p) || 1;
            loadCampaignTable();
        }

        function _updateCampaignPagination(page, totalPages, total) {
            _campPage = page;
            _campTotalPages = totalPages;
            
            const stats = document.getElementById('page-info-stats');
            if (stats) stats.textContent = `${total.toLocaleString()} leads`;
            
            const cur = document.getElementById('page-current-num');
            if (cur) cur.textContent = page;
            
            const tot = document.getElementById('page-total-num');
            if (tot) tot.textContent = totalPages;

            const prev = document.getElementById('btn-prev-page');
            const next = document.getElementById('btn-next-page');
            if (prev) prev.disabled = page <= 1;
            if (next) next.disabled = page >= totalPages;
            const sel = document.getElementById('page-select');
            if (sel) {
                sel.innerHTML = '';
                for (let i = 1; i <= Math.min(totalPages, 50); i++) {
                    const opt = document.createElement('option');
                    opt.value = i; opt.textContent = i;
                    if (i === page) opt.selected = true;
                    sel.appendChild(opt);
                }
            }
        }

        async function loadCampaignTable(silent=false) {
            try {
                const params = new URLSearchParams();
                const statutEl = document.getElementById('filter-statut');
                const siteEl = document.getElementById('filter-site');
                const emailEl = document.getElementById('filter-email');
                const campaignEl = document.getElementById('global-campaign-select');

                const sectorEl = document.getElementById('filter-sector');
                const sourceEl = document.getElementById('filter-source');
                const tagEl    = document.getElementById('filter-tag');

                params.set('statut', statutEl ? statutEl.value : 'tous');
                params.set('site', siteEl ? siteEl.value : 'tous');
                params.set('source', sourceEl && sourceEl.value !== 'tous' ? sourceEl.value : '');
                params.set('tag', tagEl ? tagEl.value : '');

                if (sectorEl && sectorEl.value && sectorEl.value !== 'tous') {
                    params.set('sector', sectorEl.value);
                }
                
                const searchEl = document.getElementById('search-lead');
                if (searchEl && searchEl.value.trim() !== '') {
                    params.set('search', searchEl.value.trim());
                }

                params.set('limit', '50');
                params.set('page', _campPage);

                const url = '/api/leads/all?' + params.toString();
                
                // Skeleton pendant le chargement (sauf si mode silencieux)
                const tbody = document.getElementById('tbody-campaign');
                if (!silent && tbody && typeof skeletonTable === 'function') tbody.innerHTML = skeletonTable(6);

                const r = await fetch(url, { cache: 'no-store' });
                const d = await r.json();

                if(d.leads && d.leads.length > 0) {
                    _campaignData = d.leads;
                    syncAllLeads();
                    renderCampaignTable(d.leads);
                    const total = d.total || 0;
                    const countEl = document.getElementById('campaign-count');
                    if (countEl) countEl.textContent = total + ' leads';
                    _updateCampaignPagination(d.page || 1, d.total_pages || 1, total);
                    // Populate sector filter
                    if (typeof loadSectorFilter === 'function') loadSectorFilter();
                } else {
                    const tbody2 = document.getElementById('tbody-campaign');
                    if (tbody2) tbody2.innerHTML = '<tr><td colspan="9"><div class="empty-state">' +
                        '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>' +
                        '<h3>Aucun lead trouvé</h3><p>Lance un scraping pour collecter des prospects, ou ajuste les filtres.</p>' +
                        '</div></td></tr>';
                    if (document.getElementById('campaign-count')) document.getElementById('campaign-count').textContent = '0 leads';
                    _updateCampaignPagination(1, 1, 0);
                }
            } catch(e) { console.error('loadCampaignTable:', e); }
        }
        
        function renderCampaignTable(leads) {
            const searchInput = document.getElementById('search-lead');
            const search = searchInput ? searchInput.value.toLowerCase() : '';
            let filtered = leads;
            if(search) {
                filtered = leads.filter(l => 
                    (l.nom || '').toLowerCase().includes(search) || 
                    (l.email || '').toLowerCase().includes(search)
                );
            }
            
            const rows = filtered.map(l => {
                const siteIcon = l.site_web 
                    ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m22 4-10 10-3-3"/></svg>'
                    : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg>';
                const emailIcon = l.email 
                    ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>'
                    : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg>';
                const statusBadge = getStatusBadge(l.statut_display || l.statut);
                const initial = (l.nom || '?').charAt(0).toUpperCase();
                
                // Source badge small
                const srcMap = { maps: '#6b7280', ads: '#f97316', fb_ads: '#1877f2', tech: '#8b5cf6', ecom: '#8b5cf6', jobs: '#06b6d4', bodacc: '#10b981' };
                const srcCol = srcMap[l.source] || '#9ca3af';
                const srcBadge = `<span style="background:${srcCol}15;color:${srcCol};padding:1px 5px;border-radius:4px;font-size:9px;font-weight:700;text-transform:uppercase;margin-right:5px">${l.source}</span>`;

                return `
                <tr class="${l.id === _selectedLeadId ? 'selected' : ''}" onclick="selectLead(${l.id})" style="cursor:pointer">
                    <td class="col-cb" onclick="event.stopPropagation()"><input type="checkbox" class="lead-cb" data-id="${l.id}"></td>
                    <td class="col-name">
                        <div class="lead-avatar">${initial}</div>
                        <div class="lead-info">
                            <strong class="lead-name">${escHtml(l.nom || '—')}</strong>
                            <div class="lead-meta">${srcBadge}${escHtml(l.ville || 'FR')} · ${escHtml(l.category || l.secteur || 'Prospect')}</div>
                        </div>
                    </td>
                    <td data-label="Ville" class="col-hide-m" style="font-size:11px;color:var(--ink3)">${escHtml(l.ville || '—')}</td>
                    <td data-label="Note" class="col-hide-m" style="font-size:11px">${l.rating || l.note ? (l.rating || l.note) + ' ★' : '—'}</td>
                    <td data-label="Site" class="col-hide-m" style="text-align:center">${siteIcon}</td>
                    <td data-label="Email" class="col-hide-m" style="text-align:center">${emailIcon}</td>
                    <td data-label="Score" class="col-hide-m" style="font-size:11px;font-weight:600">${l.score_urgence || '—'}</td>
                    <td data-label="Statut" class="col-status">${statusBadge}</td>
                    <td onclick="event.stopPropagation()" class="col-hide-m">
                        <button class="action-btn" onclick="openLeadPanel(${l.id}, 'audit')" title="Voir audit">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18"/></svg>
                        </button>
                    </td>
                </tr>`;
            }).join('');
            
            const tbody = document.getElementById('tbody-campaign');
            if (tbody) tbody.innerHTML = rows || '<tr><td colspan="9" style="text-align:center;padding:2rem">Aucun lead</td></tr>';
            // Le total est géré par loadCampaignTable pour éviter les dupplications
        }
        
        function getStatusBadge(statut) {
            // Support pour l'objet statut_display de l'API unifiée
            if (statut && typeof statut === 'object' && statut.label) {
                const c = statut.color || '#9ca3af';
                return `<span class="status-badge" style="background:${c}15;color:${c};border-color:${c}30">${statut.label}</span>`;
            }

            const badges = {
                'en_attente': '<span class="status-badge pending">À traiter</span>',
                'scraped': '<span class="status-badge scraped">Scrapé</span>',
                'audite': '<span class="status-badge audited">Audité</span>',
                'email_genere': '<span class="status-badge email-ready">Email prêt</span>',
                'envoye': '<span class="status-badge sent">Envoyé</span>',
                'repondu': '<span class="status-badge replied">Répondu</span>',
                'audit_echoue': '<span class="status-badge failed" style="background:rgba(239,68,68,0.1);color:var(--red);border-color:rgba(239,68,68,0.2)">❌ Échec</span>'
            };
            return badges[statut] || '<span class="status-badge pending">—</span>';
        }
        
        function selectLead(id) {
            _selectedLeadId = id;
            renderCampaignTable(_campaignData);
            
            // Skeleton immédiat pendant le chargement
            const content = document.getElementById('panel-content');
            if (content) content.innerHTML = typeof skeletonPanel === 'function' ? skeletonPanel() : '';

            // Open panel
            _openPanelWithOverlay();
            
            // Toujours forcer l'onglet "audit" actif
            document.querySelectorAll('.side-panel-tab').forEach(t => {
                t.classList.toggle('active', t.dataset.tab === 'audit');
            });
            
            // Charger immédiatement
            loadPanelContent(id, 'audit');
        }
        
        // Fonction centralisée pour ouvrir le panel avec overlay
        function _openPanelWithOverlay() {
            const _sp = document.getElementById('lead-details-panel') || document.getElementById('side-panel');
            if (_sp) _sp.classList.add('open');
            const mc = document.querySelector('.main-content');
            if (mc) mc.classList.add('with-panel');
            const overlay = document.getElementById('panel-overlay');
            if (overlay) overlay.style.display = 'block';
        }
        
        // Side Panel Functions
        function openLeadPanel(leadId, tab = 'audit') {
            _selectedLeadId = leadId;
            
            // Skeleton immédiat pendant le chargement
            const content = document.getElementById('panel-content');
            if (content) content.innerHTML = typeof skeletonPanel === 'function' ? skeletonPanel() : '';

            _openPanelWithOverlay();
            
            // Activer l'onglet sélectionné
            document.querySelectorAll('.side-panel-tab').forEach(t => {
                t.classList.toggle('active', t.dataset.tab === tab);
            });
            
            // Charger le contenu
            loadPanelContent(leadId, tab);
        }
        
        function closeSidePanel() {
            const _sp2 = document.getElementById('lead-details-panel') || document.getElementById('side-panel');
            if (_sp2) _sp2.classList.remove('open');
            const mc = document.querySelector('.main-content');
            if (mc) mc.classList.remove('with-panel');
            const overlay = document.getElementById('panel-overlay');
            if (overlay) overlay.style.display = 'none';
            // Réinitialiser l'état de sélection
            _selectedLeadId = null;
            // Vider le contenu pour la prochaine ouverture
            const content = document.getElementById('panel-content');
            if (content) content.innerHTML = '';
        }
        
        function switchPanelTab(tab, el) {
            document.querySelectorAll('.side-panel-tab').forEach(t => t.classList.remove('active'));
            el.classList.add('active');
            if(_selectedLeadId) {
                // Vider immédiatement, puis recharger
                const content = document.getElementById('panel-content');
                if (content) content.innerHTML = typeof skeletonPanel === 'function' ? skeletonPanel() : '';
                loadPanelContent(_selectedLeadId, tab);
            } else {
                // Panel ouvert sans prospect sélectionné : fermer
                closeSidePanel();
            }
        }
        
        async function loadPanelContent(leadId, tab) {
            const content = document.getElementById('panel-content');
            if (!content) return;
            
            // Garder la référence du prospect courant pour éviter les données croisées
            const currentLeadId = leadId;
            const leadIdNum = Number(leadId);
            
            // Utiliser d'abord les données en cache pour affichage immédiat
            let leadFromCache = _campaignData.find(l => l.id === leadIdNum || l.id == leadId);
            if (leadFromCache) {
                const titleEl = document.getElementById('panel-title');
                if (titleEl) titleEl.textContent = leadFromCache.nom || 'Détails';
                if (tab === 'audit') content.innerHTML = renderAuditPanel(leadFromCache);
                else if (tab === 'email') { content.innerHTML = renderEmailPanel(leadFromCache); _setEmailPreviewSrc(leadFromCache); }
                else if (tab === 'suivi') content.innerHTML = renderSuiviPanel(leadFromCache);
            }
            
            // Rafraîchir depuis l'API pour avoir les données à jour
            try {
                const r = await fetch('/api/leads/' + leadIdNum, { cache: 'no-store' });
                let lead = null;
                
                if (r.ok) {
                    const d = await r.json();
                    lead = d.lead || d;
                }
                
                // Si l'endpoint individuel n'existe pas, fallback sur la liste
                if (!lead || lead.error) {
                    const r2 = await fetch('/api/leads?statut=tous&limit=500', { cache: 'no-store' });
                    const d2 = await r2.json();
                    if (d2.leads) {
                        lead = d2.leads.find(l => l.id === leadIdNum || l.id == leadId) || null;
                    }
                }
                
                // Vérifier qu'on n'a pas changé de prospect entre temps
                if (_selectedLeadId != currentLeadId) return;
                
                if (!lead) {
                    if (!leadFromCache) content.innerHTML = '<p style="color:var(--ink3);padding:1rem">Lead non trouvé</p>';
                    return;
                }
                
                // Mettre à jour le cache
                const idx = _campaignData.findIndex(l => l.id === leadIdNum || l.id == leadId);
                if (idx >= 0) _campaignData[idx] = lead;
                
                const titleEl = document.getElementById('panel-title');
                if (titleEl) titleEl.textContent = lead.nom || 'Détails';
                
                // Rendre le contenu final
                if (tab === 'audit') content.innerHTML = renderAuditPanel(lead);
                else if (tab === 'email') { content.innerHTML = renderEmailPanel(lead); _setEmailPreviewSrc(lead); }
                else if (tab === 'suivi') content.innerHTML = renderSuiviPanel(lead);
            } catch (e) {
                if (!leadFromCache) content.innerHTML = '<p style="color:var(--red);padding:1rem">Erreur: ' + e.message + '</p>';
            }
        }
        
        function _scoreBar(label, val, max, unit, inv) {
            if (val === null || val === undefined || val === 0 && unit === 's') return '';
            const pct = Math.min(100, Math.round((val / max) * 100));
            const good = inv ? pct < 50 : pct >= 70;
            const warn = inv ? pct < 70 : pct >= 40;
            const color = good ? '#10b981' : warn ? '#f59e0b' : '#ef4444';
            const display = unit === 's' ? parseFloat(val).toFixed(1) + 's' : val + unit;
            return '<div style="margin-bottom:14px">'
                + '<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:6px">'
                + '<span style="color:#64748b;font-weight:500">' + label + '</span><span style="font-weight:700;color:#0f172a">' + display + '</span></div>'
                + '<div style="height:6px;background:#f1f5f9;border-radius:4px;overflow:hidden">'
                + '<div style="width:' + pct + '%;height:100%;background:' + color + ';border-radius:4px;transition:width 0.5s ease"></div>'
                + '</div></div>';
        }

        function _renderScoreBars(lead) {
            return '<div style="margin-bottom:20px;padding:16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px">'
                + _scoreBar('Performance', parseInt(lead.score_perf) || 0, 100, '', false)
                + _scoreBar('SEO', parseInt(lead.score_seo) || 0, 100, '', false)
                + _scoreBar('Urgence', parseFloat(lead.score_urgence) || 0, 10, '/10', true)
                + (lead.lcp ? _scoreBar('LCP', parseFloat(lead.lcp) / 1000, 5, 's', true) : '')
                + '</div>';
        }

        function _srcBadge(source) {
            const cfg = {
                maps:   ['#64748b','Maps'],   ads:    ['#f97316','Ads'],
                fb_ads: ['#3b82f6','FB Ads'], tech:   ['#8b5cf6','Tech'],
                ecom:   ['#8b5cf6','E-com'],  jobs:   ['#06b6d4','Jobs'],
                bodacc: ['#10b981','BODACC'],
            };
            const [c,l] = cfg[source] || ['#94a3b8', source || '?'];
            return `<span style="background:${c}15;color:${c};padding:4px 8px;border-radius:6px;font-size:11px;font-weight:600">${l}</span>`;
        }

        function _prospBadge(s) {
            const cfg = {
                a_contacter:      ['#64748b','À contacter'],
                email_genere:     ['#6366f1','Email prêt'],
                step1_envoye:     ['#3b82f6','Step 1 ✓'],
                repondu:          ['#f59e0b','Répondu'],
                lien_envoye:      ['#10b981','Rapport livré'],
                linkedin_envoye:  ['#0077b5','LinkedIn'],
                formulaire_envoye:['#6366f1','Formulaire'],
            };
            const [c,l] = cfg[s] || ['#94a3b8', s||'—'];
            return `<span style="background:${c}15;color:${c};padding:4px 8px;border-radius:6px;font-size:11px;font-weight:600">${l}</span>`;
        }

        function _row(label, content) {
            if (!content) return '';
            return `<div style="display:flex;gap:16px;padding:12px 0;border-bottom:1px solid #f1f5f9;align-items:center">
                <dt style="color:#64748b;font-size:12px;width:90px;flex-shrink:0;font-weight:500;margin:0;text-transform:uppercase;letter-spacing:0.05em">${label}</dt>
                <dd style="color:#0f172a;font-size:13px;font-weight:500;margin:0;flex:1;word-break:break-word">${content}</dd>
            </div>`;
        }

        function renderAuditPanel(lead) {
            const hasAudit  = !!(lead.score_perf || lead.score_seo || lead.lcp || lead.lien_rapport);
            const isSniper  = lead.source && lead.source !== 'maps';
            const ceoName   = [lead.ceo_prenom, lead.ceo_nom].filter(Boolean).join(' ');
            const _isEmail = v => v && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
            const email     = _isEmail(lead.email_valide_audit) ? lead.email_valide_audit : (_isEmail(lead.email_valide) ? lead.email_valide : (lead.email || ''));
            const tel       = lead.telephone_sniper || lead.telephone || '';
            const lcp       = lead.lcp ? (parseFloat(lead.lcp)/1000).toFixed(1) + 's' : null;
            const mode      = lead.copywriting_mode;

            // Politique de contact (Migré de Sniper)
            let contactHtml = '';
            const hasEmailValide = !!lead.email_valide_audit;
            const catchAll = !!lead.is_catch_all;
            const hasPhone = !!(lead.telephone || lead.telephone_sniper);
            
            if (hasEmailValide && !catchAll) {
                contactHtml = `<div style="background:#dcfce7;color:#166534;padding:12px 16px;border-radius:12px;font-size:13px;font-weight:600;margin-bottom:20px;border:1px solid #bbf7d0;display:flex;align-items:center;gap:10px">
                    <span style="font-size:18px">✅</span> <span>Email valide — Envoi step 1 recommandé</span>
                </div>`;
            } else if (catchAll) {
                contactHtml = `<div style="background:#fef3c7;color:#92400e;padding:12px 16px;border-radius:12px;font-size:13px;font-weight:600;margin-bottom:20px;border:1px solid #fde68a;display:flex;align-items:center;gap:10px">
                    <span style="font-size:18px">⚠️</span> <span>Catch-all — Approche LinkedIn ou téléphone</span>
                </div>`;
            } else if (hasPhone) {
                contactHtml = `<div style="background:#dbeafe;color:#1e40af;padding:12px 16px;border-radius:12px;font-size:13px;font-weight:600;margin-bottom:20px;border:1px solid #bfdbfe;display:flex;align-items:center;gap:10px">
                    <span style="font-size:18px">📞</span> <span>Pas d'email — Contacter par téléphone</span>
                </div>`;
            } else {
                contactHtml = `<div style="background:#fee2e2;color:#991b1b;padding:12px 16px;border-radius:12px;font-size:13px;font-weight:600;margin-bottom:20px;border:1px solid #fecaca;display:flex;align-items:center;gap:10px">
                    <span style="font-size:18px">❌</span> <span>Aucun contact — Formulaire site ou LinkedIn manuel</span>
                </div>`;
            }

            return `
            ${contactHtml}
            <div class="panel-section" style="margin-bottom:24px">
                <div style="display:flex;align-items:center;gap:16px;background:#f8fafc;padding:20px;border-radius:12px;border:1px solid #e2e8f0">
                    <div style="width:52px;height:52px;background:linear-gradient(135deg, #10b981, #059669);color:#fff;border-radius:12px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:20px;flex-shrink:0;box-shadow:0 4px 12px rgba(16,185,129,0.2)">${(lead.nom||'').charAt(0).toUpperCase()}</div>
                    <div style="flex:1;min-width:0">
                        <div style="font-weight:800;font-size:18px;color:#0f172a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;letter-spacing:-0.3px">${escHtml(lead.nom||'—')}</div>
                        <div style="font-size:13px;color:#64748b;margin-top:2px;font-weight:500">${[lead.ville,lead.category||lead.secteur].filter(Boolean).map(escHtml).join(' · ')||'—'}</div>
                        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:10px">
                            ${_srcBadge(lead.source)}
                            ${lead.statut_prospection ? _prospBadge(lead.statut_prospection) : ''}
                            ${lead.tag_urgence ? `<span style="background:#f1f5f9;color:#475569;padding:4px 8px;border-radius:6px;font-size:11px;font-weight:600">${lead.tag_urgence}</span>` : ''}
                        </div>
                    </div>
                    <button class="leads-btn" onclick="openEditLeadFromPanel(${lead.id})" title="Modifier" style="padding:10px">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
                    </button>
                </div>
            </div>

            <div class="panel-section" style="margin-bottom:32px">
                <h4 style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:12px">Coordonnées</h4>
                <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:0 20px">
                    <dl style="margin:0">
                        ${_row('Décideur', ceoName ? `<strong>${escHtml(ceoName)}</strong>${lead.ceo_source?` <span style="color:#94a3b8;font-size:11px;font-weight:400">(${lead.ceo_source})</span>`:''}` : '')}
                        ${email ? `<div style="display:flex;gap:16px;padding:12px 0;border-bottom:1px solid #f1f5f9;align-items:center">
                            <dt style="color:#64748b;font-size:12px;width:90px;flex-shrink:0;font-weight:500;margin:0;text-transform:uppercase;letter-spacing:0.05em">Email</dt>
                            <dd style="margin:0;flex:1;min-width:0;font-weight:500"><a href="mailto:${escHtml(email)}" style="color:#10b981;text-decoration:none;font-size:13px;word-break:break-all">${escHtml(email)}</a>${lead.email_valide_audit?` <span style="color:#10b981;font-size:11px">✓ Validé</span>`:''}</dd>
                        </div>` : ''}
                        ${lead.email_2 ? `<div style="display:flex;gap:16px;padding:12px 0;border-bottom:1px solid #f1f5f9;align-items:center">
                            <dt style="color:#64748b;font-size:12px;width:90px;flex-shrink:0;font-weight:500;margin:0;text-transform:uppercase;letter-spacing:0.05em">Email 2</dt>
                            <dd style="margin:0;flex:1;min-width:0;font-weight:500"><a href="mailto:${escHtml(lead.email_2)}" style="color:#10b981;text-decoration:none;font-size:13px;word-break:break-all">${escHtml(lead.email_2)}</a></dd>
                        </div>` : ''}
                        ${_row('Téléphone', tel ? `<a href="tel:${escHtml(tel)}" style="color:#0f172a;text-decoration:none">${escHtml(tel)}</a>` : '')}
                        ${lead.phone_2 ? _row('Téléphone 2', `<a href="tel:${escHtml(lead.phone_2)}" style="color:#0f172a;text-decoration:none">${escHtml(lead.phone_2)}</a>`) : ''}
                        ${mode ? _row('Mode', `<span style="color:${mode==='direct'?'#10b981':'#f59e0b'};font-weight:600">${mode==='direct'?'🎯 Approche Directe':'📤 Approche Transfert'}</span>`) : ''}
                        ${lead.site_web ? `<div style="display:flex;gap:16px;padding:12px 0;align-items:center">
                            <dt style="color:#64748b;font-size:12px;width:90px;flex-shrink:0;font-weight:500;margin:0;text-transform:uppercase;letter-spacing:0.05em">Site web</dt>
                            <dd style="margin:0;flex:1;min-width:0;font-weight:500"><a href="${escHtml(lead.site_web)}" target="_blank" style="color:#10b981;text-decoration:none;font-size:13px;word-break:break-all">${escHtml(lead.site_web.replace(/^https?:\/\//,''))}</a></dd>
                        </div>` : ''}
                        <div style="display:flex;gap:16px;padding:12px 0;border-top:1px solid #f1f5f9">
                            <dt style="color:#64748b;font-size:12px;width:90px;flex-shrink:0;font-weight:500;margin:0;text-transform:uppercase;letter-spacing:0.05em;padding-top:8px">Notes</dt>
                            <dd style="margin:0;flex:1;min-width:0;">
                                <textarea onblur="saveCoreNotes(${lead.id}, this.value)" style="width:100%;height:60px;resize:vertical;border:1px solid #e2e8f0;border-radius:6px;padding:8px;font-size:13px;font-family:inherit" placeholder="Ajouter une note (sauvegarde auto)...">${escHtml(lead.notes || '')}</textarea>
                            </dd>
                        </div>
                    </dl>
                </div>
            </div>

            <div class="panel-section" style="margin-bottom:32px">
                <h4 style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:12px">Scores d'Audit</h4>
                ${lead.cms_detected ? `<div style="display:inline-block;padding:6px 12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;font-size:12px;color:#475569;font-weight:600;margin-bottom:16px">Technologie : <span style="color:#0f172a">${escHtml(lead.cms_detected)}</span></div>` : ''}
                ${lead.statut==='audit_echoue'
                    ? `<div style="background:#fef2f2;border:1px solid #fecaca;padding:16px;border-radius:12px;display:flex;align-items:flex-start;gap:12px"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2" style="flex-shrink:0;margin-top:2px"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg><div><p style="color:#ef4444;font-weight:700;margin:0 0 4px;font-size:14px">Échec de l'audit</p><p style="font-size:13px;color:#7f1d1d;margin:0">${escHtml(lead.probleme_principal||'Raison technique inconnue')}</p></div></div>`
                    : hasAudit ? _renderScoreBars(lead)
                    : `<div style="padding:24px;text-align:center;background:#f8fafc;border:1px dashed #cbd5e1;border-radius:12px"><p style="font-size:13px;color:#64748b;font-weight:500;margin:0">L'audit n'a pas encore été généré pour ce prospect.</p></div>`}
            </div>
            
            <!-- Section Plus d'infos -->
            ${(() => {
                try {
                    // Données de base disponibles pour TOUS les leads
                    let baseHtml = '';
                    if (lead.rating) baseHtml += `<div style="margin-bottom:8px"><span style="color:#64748b">Note Google :</span> <span style="font-weight:600">${parseFloat(lead.rating).toFixed(1)} ⭐</span></div>`;
                    if (lead.nb_avis) baseHtml += `<div style="margin-bottom:8px"><span style="color:#64748b">Avis Google :</span> <span style="font-weight:600">${lead.nb_avis} avis</span></div>`;
                    if (lead.mot_cle) baseHtml += `<div style="margin-bottom:8px"><span style="color:#64748b">Mot-clé :</span> <span style="font-weight:600;background:#f1f5f9;padding:2px 7px;border-radius:6px">${escHtml(lead.mot_cle)}</span></div>`;
                    if (lead.date_scraping) baseHtml += `<div style="margin-bottom:8px"><span style="color:#64748b">Détecté le :</span> <span style="font-weight:600">${new Date(lead.date_scraping).toLocaleDateString('fr-FR')}</span></div>`;

                    // Données de donnees_audit (si présentes)
                    let metaHtml = '';
                    if (lead.donnees_audit) {
                        let audit = null;
                        try {
                            audit = typeof lead.donnees_audit === 'string' ? JSON.parse(lead.donnees_audit) : lead.donnees_audit;
                        } catch(e) {
                            try {
                                const cleaned = lead.donnees_audit.replace(/[\u0000-\u001F\u007F-\u009F]/g, "");
                                audit = JSON.parse(cleaned);
                            } catch(e2) { audit = null; }
                        }

                        if (audit && Object.keys(audit).length > 0) {
                            if (audit.tag && audit.tag !== 'score_ok') {
                                metaHtml += `<div style="margin-bottom:12px;padding:10px;background:#fff;border:1px solid #fee2e2;border-radius:8px">
                                    <span style="color:#b91c1c;font-size:10px;text-transform:uppercase;display:block;margin-bottom:2px;font-weight:800">Analyse Technique :</span>
                                    <span style="font-weight:700;color:#991b1b;font-size:13px">${escHtml(audit.tag)}</span>
                                    ${audit.reason ? `<p style="margin:4px 0 0;font-size:12px;color:#7f1d1d;line-height:1.4">${escHtml(audit.reason)}</p>` : ''}
                                </div>`;
                            } else if (audit.reason) {
                                metaHtml += `<div style="margin-bottom:12px;font-size:12px;color:#475569;line-height:1.4">${escHtml(audit.reason)}</div>`;
                            }
                            if (audit.ad_start) metaHtml += `<div style="margin-bottom:8px"><span style="color:#64748b">Diffusion Ads :</span> <span style="font-weight:600">${escHtml(audit.ad_start)}</span></div>`;
                            if (audit.fan_count) metaHtml += `<div style="margin-bottom:8px"><span style="color:#64748b">Notoriété :</span> <span style="font-weight:600">${escHtml(String(audit.fan_count))} abonnés</span></div>`;
                            if (audit.cms || audit.cms_detected) metaHtml += `<div style="margin-bottom:8px"><span style="color:#64748b">Technologie :</span> <span style="font-weight:600">${escHtml(audit.cms || audit.cms_detected)}</span></div>`;
                            if (audit.ad_body) {
                                metaHtml += `<div style="margin-top:12px">
                                    <span style="color:#64748b;display:block;margin-bottom:4px;font-size:11px;text-transform:uppercase;font-weight:700">Contenu de la publicité :</span>
                                    <div style="font-style:italic;background:#f8fafc;padding:12px;border-radius:8px;border:1px solid #e2e8f0;font-size:12px;line-height:1.5;color:#475569;max-height:150px;overflow-y:auto">${escHtml(audit.ad_body)}</div>
                                </div>`;
                            }
                            const fbUrl = audit.page_url || (audit.page_id ? `https://www.facebook.com/${audit.page_id}` : null);
                            if (fbUrl) {
                                metaHtml += `<div style="margin-top:12px"><a href="${escHtml(fbUrl)}" target="_blank" style="color:#1877f2;text-decoration:none;font-size:12px;font-weight:700;display:flex;align-items:center;gap:6px">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M22 12c0-5.52-4.48-10-10-10S2 6.48 2 12c0 4.84 3.44 8.87 8 9.8V15H8v-3h2V9.5C10 7.57 11.57 6 13.5 6H16v3h-2c-.55 0-1 .45-1 1v2h3v3h-3v6.95c5.05-.5 9-4.76 9-9.95z"/></svg>
                                    Voir la page Facebook →
                                </a></div>`;
                            }
                            if (audit.ad_id) {
                                metaHtml += `<div style="margin-top:8px"><a href="https://www.facebook.com/ads/library/?id=${audit.ad_id}" target="_blank" style="color:#64748b;text-decoration:none;font-size:12px;font-weight:700;display:flex;align-items:center;gap:6px">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
                                    Voir dans l'Ad Library →
                                </a></div>`;
                            }
                            if (lead.source === 'fb_ads' || lead.source === 'ads') {
                                metaHtml += `<div style="margin-top:16px;padding-top:12px;border-top:1px dashed #cbd5e1">
                                    <span style="color:#64748b;display:block;margin-bottom:6px;font-size:10px;text-transform:uppercase;font-weight:700">Capture d'écran :</span>
                                    <div style="width:100%;aspect-ratio:16/9;background:#f1f5f9;border-radius:10px;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#94a3b8;font-size:11px;font-style:italic;text-align:center;padding:20px;border:1px solid #e2e8f0">
                                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-bottom:8px;opacity:0.5"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                                        Capture bientôt disponible
                                    </div>
                                </div>`;
                            }
                        }
                    }

                    const fullHtml = baseHtml + metaHtml;
                    if (!fullHtml) return '';

                    return `
                    <div class="panel-section" id="section-meta-scraper" style="margin-bottom:32px;animation: fadeIn 0.3s ease">
                        <div style="background:linear-gradient(to bottom, rgba(16,185,129,0.03), rgba(16,185,129,0.07));border:1px solid rgba(16,185,129,0.2);border-radius:16px;padding:20px;box-shadow:0 4px 12px rgba(16,185,129,0.05)">
                            <h4 style="font-size:11px;font-weight:900;color:#059669;margin-bottom:14px;text-transform:uppercase;letter-spacing:0.1em;display:flex;align-items:center;gap:8px">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>
                                Plus d'infos
                            </h4>
                            <div style="font-size:13px;color:#1e293b;line-height:1.8">
                                ${fullHtml}
                            </div>
                        </div>
                    </div>`;
                } catch(e) { console.error("Plus d'infos render error:", e); return ''; }
            })()}
            
            
            <div class="panel-section" style="margin-top:auto;padding-top:24px;border-top:1px solid #e2e8f0">
                <div style="display:flex;gap:10px;flex-wrap:wrap">
                    ${hasAudit ? `
                        <button class="leads-btn" style="flex:1;justify-content:center" onclick="regenerateAudit(${lead.id})">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/></svg>
                            Relancer
                        </button>
                        <button class="leads-btn" style="flex:1;justify-content:center" onclick="previewReport(${lead.id})">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
                            Voir Rapport
                        </button>
                        <button class="leads-btn-primary" style="flex:1;justify-content:center" onclick="pushReport(${lead.id})">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M22 2 11 13"/><path d="M22 2-9 19l-5-5"/></svg>
                            Publier
                        </button>
                        ${(lead.lien_rapport && lead.lien_rapport.startsWith('http')) ? `
                        <a href="${lead.lien_rapport}" target="_blank" class="leads-btn" style="width:100%;justify-content:center;margin-top:6px;background:#f8fafc">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                            Ouvrir le lien public
                        </a>
                        ` : ''}
                    ` : `
                        <button class="leads-btn-primary" style="width:100%;justify-content:center" onclick="regenerateAudit(${lead.id})">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/></svg>
                            Lancer l'Audit Automatique
                        </button>
                    `}
                </div>
            </div>
            `;
        }
        
        function renderEmailPanel(lead) {
            const hasEmail = lead.email_corps && lead.email_corps.length > 0;
            // Extract subject from email HTML title tag
            let emailSubject = lead.email_objet || 'Objet non défini';
            if (!lead.email_objet && lead.email_corps) {
                const titleMatch = lead.email_corps.match(/<title>([^<]+)<\/title>/i);
                if (titleMatch) emailSubject = titleMatch[1];
            }
            // Use profile field from API, or extract from email_objet
            let profil = lead.profile || '';
            if(!profil) {
                const profilMatch = lead.email_objet ? lead.email_objet.match(/^(Profil [A-D])/i) : null;
                profil = profilMatch ? profilMatch[1] : '';
            }
            const previewHtml = lead.email_corps ? lead.email_corps.replace(/"/g, '&quot;') : '';
            return `
            <div class="panel-section" style="background:var(--surface2);padding:20px;border-radius:12px;margin-bottom:16px">
                <div style="display:flex;align-items:center;gap:14px;margin-bottom:12px">
                    <div style="width:48px;height:48px;background:var(--accent);color:white;border-radius:12px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:20px">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
                    </div>
                    <div style="flex:1">
                        ${profil ? `<div style="font-size:11px;color:var(--accent);font-weight:600;margin-bottom:4px">${escHtml(profil)}</div>` : ''}
                        <div style="font-weight:600;font-size:15px;color:var(--ink)">${escHtml(emailSubject)}</div>
                        <div style="font-size:12px;color:${hasEmail ? 'var(--accent)' : 'var(--ink3)'};margin-top:2px">${hasEmail ? 'Email généré' : 'Non généré'}</div>
                        ${(lead.lien_rapport && lead.lien_rapport.startsWith('http')) ? `<a href="${escHtml(lead.lien_rapport)}" target="_blank" style="font-size:11px;color:var(--blue);margin-top:3px;display:block">Rapport en ligne</a>` : ''}
                    </div>
                </div>
            </div>
            <div class="panel-section">
                <div style="display:flex;gap:8px;flex-wrap:wrap">
                    ${hasEmail ? `
                        <button class="btn bg1 sm" style="font-size:14px;padding:10px 16px" onclick="previewEmail(${lead.id})">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
                            Prévisualiser
                        </button>
                        <button class="btn bg1 sm" style="font-size:14px;padding:10px 16px" onclick="openEmailEditor(${lead.id})">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                            &#201;diter
                        </button>
                        <button class="btn bp1 sm" style="font-size:14px;padding:10px 16px" onclick="sendTestEmail(${lead.id})">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M22 2 11 13"/><path d="M22 2-9 19l-5-5"/></svg>
                            Envoyer test
                        </button>
                    ` : ''}
                    <button class="btn bp1 sm" style="font-size:14px;padding:10px 16px" onclick="generateEmailForLead(${lead.id})">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
                        ${hasEmail ? 'R&#233;g&#233;n&#233;rer' : 'G&#233;n&#233;rer'}
                    </button>
                </div>
            </div>
            ${hasEmail ? `
            <div class="panel-section">
                <h4 style="font-size:11px;font-weight:700;color:var(--ink3);margin-bottom:10px;text-transform:uppercase;letter-spacing:0.5px">Preview</h4>
                <iframe id="email-preview-iframe" class="email-preview-frame" style="height:350px;width:100%;border:1px solid var(--border);border-radius:8px"></iframe>
            </div>
            ` : ''}
            `;
        }

        function _setEmailPreviewSrc(lead) {
            const iframe = document.getElementById('email-preview-iframe');
            if (!iframe || !lead.email_corps) return;
            const blob = new Blob([lead.email_corps], { type: 'text/html' });
            const url = URL.createObjectURL(blob);
            iframe.src = url;
            iframe.onload = () => URL.revokeObjectURL(url);
        }
        
        function renderSuiviPanel(lead) {
            const hasSent = !!lead.sent_at;
            const statutColor = { envoye:'#3b82f6', delivered:'#10b981', bounced:'#ef4444', spam:'#f97316', scheduled:'#6366f1' };
            return `
            <div class="panel-section" style="margin-bottom:14px">
                <h4 style="font-size:10px;font-weight:700;color:var(--ink3);margin-bottom:12px;text-transform:uppercase;letter-spacing:.06em">Statut prospection</h4>
                <div style="display:flex;flex-direction:column;gap:10px">
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <span style="font-size:12px;color:var(--ink3)">Statut lead</span>
                        <span style="font-size:12px;font-weight:600">${escHtml(lead.statut || '—')}</span>
                    </div>
                    ${lead.statut_prospection ? `
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <span style="font-size:12px;color:var(--ink3)">Prospection</span>
                        <span style="font-size:12px;font-weight:600;color:#3b82f6">${escHtml(lead.statut_prospection)}</span>
                    </div>` : ''}
                </div>
            </div>

            <div class="panel-section" style="margin-bottom:14px">
                <h4 style="font-size:10px;font-weight:700;color:var(--ink3);margin-bottom:12px;text-transform:uppercase;letter-spacing:.06em">Historique email</h4>
                ${hasSent ? `
                <div style="display:flex;flex-direction:column;gap:8px">
                    <div style="display:flex;justify-content:space-between">
                        <span style="font-size:12px;color:var(--ink3)">Envoyé le</span>
                        <span style="font-size:12px;font-weight:600">${escHtml((lead.sent_at || '').split('T')[0] || lead.sent_at)}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between">
                        <span style="font-size:12px;color:var(--ink3)">Statut</span>
                        <span style="font-size:12px;font-weight:600;color:${statutColor[lead.email_status] || 'var(--ink1)'}">${escHtml(lead.email_status || '—')}</span>
                    </div>
                    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:4px">
                        <div style="text-align:center;padding:8px;background:var(--surface2);border-radius:8px">
                            <div style="font-size:18px;font-weight:700;color:${lead.is_opened ? '#10b981' : 'var(--ink3)'}">${lead.is_opened ? '✓' : '—'}</div>
                            <div style="font-size:10px;color:var(--ink3)">Ouvert</div>
                        </div>
                        <div style="text-align:center;padding:8px;background:var(--surface2);border-radius:8px">
                            <div style="font-size:18px;font-weight:700;color:${lead.is_clicked ? '#10b981' : 'var(--ink3)'}">${lead.is_clicked ? '✓' : '—'}</div>
                            <div style="font-size:10px;color:var(--ink3)">Cliqué</div>
                        </div>
                        <div style="text-align:center;padding:8px;background:var(--surface2);border-radius:8px">
                            <div style="font-size:18px;font-weight:700;color:${lead.is_replied ? '#f59e0b' : 'var(--ink3)'}">${lead.is_replied ? '✓' : '—'}</div>
                            <div style="font-size:10px;color:var(--ink3)">Répondu</div>
                        </div>
                    </div>
                    ${lead.opened_at ? `<div style="font-size:11px;color:var(--ink3)">Ouvert le ${escHtml(lead.opened_at.split('T')[0])}</div>` : ''}
                </div>
                ` : `<p style="font-size:12px;color:var(--ink3)">Aucun email envoyé</p>`}
            </div>

            <div class="panel-section">
                <h4 style="font-size:10px;font-weight:700;color:var(--ink3);margin-bottom:12px;text-transform:uppercase;letter-spacing:.06em">Actions rapides</h4>
                <div style="display:flex;flex-direction:column;gap:8px">
                    ${lead.statut_prospection === 'repondu' && lead.audit_id ? `
                    <button class="btn bp1 sm" style="font-size:13px;padding:10px" onclick="sniperSendStep2(${lead.audit_id || lead.id})">
                        Envoyer rapport (Step 2)
                    </button>` : ''}
                    <button class="btn bg1 sm" style="font-size:13px;padding:10px" onclick="generateEmailForLead(${lead.id})">
                        ${lead.email_corps ? 'Régénérer email' : 'Générer email'}
                    </button>
                    ${lead.statut_prospection === 'step1_envoye' || lead.statut === 'envoye' ? '' : `
                    <button class="btn bg1 sm" style="font-size:13px;padding:10px" onclick="sendTestEmail(${lead.id})">
                        Envoyer email test
                    </button>`}
                </div>
            </div>`;
        }
        
        // Modal Functions
        function openScraperModal() {
            document.getElementById('modal-scraper').style.display = 'flex';
        }
        
        function onSectorChange(sel) {
            const kw = sel.options[sel.selectedIndex].dataset.kw || '';
            const kwInput = document.getElementById('modal-keyword');
            if (kw) kwInput.value = kw;
            kwInput.readOnly = (sel.value !== 'Autre' && kw !== '');
        }

        function launchScraperFromModal() {
            const keyword = document.getElementById('modal-keyword').value.trim();
            const city    = document.getElementById('modal-city').value.trim();
            const sector  = document.getElementById('modal-sector').value.trim();
            const campagneSector = document.getElementById('modal-campaign-sector')?.value || '';
            const limit   = parseInt(document.getElementById('modal-limit').value) || 20;
            const minEmails = document.getElementById('modal-min-emails').value
                ? parseInt(document.getElementById('modal-min-emails').value) : null;
            const multiZone = document.getElementById('modal-multi-zone')?.checked || false;

            closeModal('modal-scraper');
            launchScraper({ keyword, city, secteur: campagneSector, sector, limit, minEmails, multiZone });
        }
        
        function closeModal(id) {
            document.getElementById(id).style.display = 'none';
        }
        
        function refreshCampaignData() {
            loadCampaignTable();
            showToast('Données rafraîchies', 'success');
        }

        /**
         * saveLead() — appelé par le bouton "Sauvegarder" du modal modal-edit-lead
         * Délègue à unifiedLeadsSave() si disponible (unified_leads.js),
         * sinon appelle directement l'API.
         */
        async function saveLead() {
            if (typeof unifiedLeadsSave === 'function') {
                // unified_leads.js gère les IDs ul-edit-* mais le modal a des IDs edit-lead-*
                // On construit le payload manuellement depuis les bons IDs
            }
            const id = document.getElementById('edit-lead-id')?.value;
            if (!id) { showToast('Erreur : ID lead manquant', 'error'); return; }
            const data = {
                nom:         document.getElementById('edit-lead-nom')?.value || '',
                email:       document.getElementById('edit-lead-email')?.value || '',
                email_2:     document.getElementById('edit-lead-email-2')?.value || '',
                telephone:   document.getElementById('edit-lead-tel')?.value || '',
                telephone_2: document.getElementById('edit-lead-tel-2')?.value || '',
                site_web:    document.getElementById('edit-lead-site')?.value || '',
                category:    document.getElementById('edit-lead-sector')?.value || '',
                ville:       document.getElementById('edit-lead-ville')?.value || '',
            };
            try {
                const r = await fetch('/api/leads/' + id + '/edit', {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                const d = await r.json();
                if (d.success) {
                    closeModal('modal-edit-lead');
                    showToast('Lead mis à jour ✅', 'success');
                    loadCampaignTable();
                    // Rafraîchir le panneau latéral si ouvert sur ce lead
                    if (typeof _selectedLeadId !== 'undefined' && _selectedLeadId == id) {
                        const currentTab = document.querySelector('.side-panel-tab.active')?.dataset?.tab || 'audit';
                        openLeadPanel(id, currentTab);
                    }
                } else {
                    showToast('Erreur : ' + (d.error || 'inconnue'), 'error');
                }
            } catch (e) {
                console.error('[saveLead]', e);
                showToast('Erreur réseau', 'error');
            }
        }

        /**
         * deleteLead() — appelé par le bouton "Supprimer" du modal modal-edit-lead
         */
        async function deleteLead() {
            const id = document.getElementById('edit-lead-id')?.value;
            const nom = document.getElementById('edit-lead-nom')?.value || `#${id}`;
            if (!id) return;
            const ok = typeof showConfirm === 'function'
                ? await showConfirm(`Supprimer définitivement "${nom}" ?`, { title: 'Supprimer', confirmText: 'Supprimer', danger: true })
                : confirm(`Supprimer "${nom}" ?`);
            if (!ok) return;
            try {
                await fetch('/api/lead/delete?id=' + id, { method: 'DELETE' });
                closeModal('modal-edit-lead');
                showToast('Lead supprimé', 'success');
                loadCampaignTable();
                closeSidePanel();
            } catch (e) {
                console.error('[deleteLead]', e);
                showToast('Erreur réseau', 'error');
            }
        }

        async function saveCoreNotes(id, notes) {
            try {
                const r = await fetch('/api/leads/' + id + '/edit', {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ notes: notes })
                });
                const d = await r.json();
                if (d.success) {
                    const idx = _campaignData.findIndex(l => l.id == id);
                    if (idx >= 0) _campaignData[idx].notes = notes;
                    if (typeof showToast === 'function') showToast("Notes sauvegardées", "success");
                }
            } catch (e) {
                console.error(e);
            }
        }

        // ============================================================
        // PUSH COLLECTIF — avec progression et mise à jour lien email
        // ============================================================
        async function pushSelectedToGitHub() {
            const checkboxes = document.querySelectorAll('.lead-cb:checked');
            
            // Si aucune sélection, pousser tous les rapports locaux
            const slugsToPush = [];
            
            if(checkboxes.length > 0) {
                // Résoudre les slugs depuis les leads cochés
                const leadIds = Array.from(checkboxes).map(cb => parseInt(cb.dataset.id)).filter(Boolean);
                const r = await fetch('/api/leads?statut=tous&limit=500');
                const d = await r.json();
                for (const id of leadIds) {
                    const lead = d.leads ? d.leads.find(l => l.id === id) : null;
                    if(lead) slugsToPush.push(makeSlug(lead.nom));
                }
            } else {
                // Tous les rapports locaux disponibles
                const r = await fetch('/api/previews');
                const d = await r.json();
                (d.previews || []).filter(p => p.local && !p.published).forEach(p => slugsToPush.push(p.slug));
            }
            
            if(slugsToPush.length === 0) {
                showToast('Aucun rapport local à publier', 'warning');
                return;
            }
            
            if(!await showConfirm(`Publier ${slugsToPush.length} rapport(s) sur GitHub Pages ?`, { title: 'Publier les rapports', confirmText: 'Publier' })) return;
            
            showToast(`Publication de ${slugsToPush.length} rapport(s)...`, 'info');
            
            // Afficher la progression dans la sidebar
            const globalProgress = document.getElementById('sidebar-audit');
            const textEl = document.getElementById('sidebar-audit-text');
            const pctEl = document.getElementById('sidebar-audit-pct');
            const barEl = document.getElementById('sidebar-audit-bar');
            if(globalProgress) globalProgress.style.display = 'block';
            if(textEl) textEl.innerHTML = `<strong>Publication en cours</strong> (0/${slugsToPush.length})`;
            
            let published = 0, errors = 0;
            
            for (let i = 0; i < slugsToPush.length; i++) {
                const slug = slugsToPush[i];
                const pct = Math.round((i / slugsToPush.length) * 100);
                if(pctEl) pctEl.textContent = pct + '%';
                if(barEl) barEl.style.width = pct + '%';
                if(textEl) textEl.innerHTML = `<strong>Publication en cours</strong> (${i + 1}/${slugsToPush.length}) : ${slug}`;
                
                try {
                    const r = await fetch('/api/previews/push', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ slugs: [slug] })
                    });
                    const d = await r.json();
                    if(d.results && d.results[0] && d.results[0].status === 'published') {
                        published++;
                        // Le backend a déjà mis à jour lien_rapport en base
                        // (UPDATE leads_audites SET lien_rapport = public_url WHERE ...)
                        // Rafraîchir le tableau pour transformer le bouton Prévisualiser en Voir Rapport en ligne
                        loadCampaignTable();
                    } else {
                        errors++;
                    }
                } catch(e) {
                    errors++;
                }
            }
            
            // Masquer la progression
            if(globalProgress) globalProgress.style.display = 'none';
            
            // Notification finale
            if(errors === 0) {
                showToast(`✅ ${published}/${slugsToPush.length} rapport(s) publiés sur GitHub ! Les liens dans les emails sont mis à jour.`, 'success');
            } else {
                showToast(`⚠️ ${published} publiés, ${errors} erreur(s)`, 'warning');
            }
            
            // Rafraîchir les données (les liens dans emails_envoyes sont déjà mis à jour en base)
            loadCampaignTable();
        }
        
        // Sync campaign data to allLeads for edit function compatibility
        function syncAllLeads() {
            if(typeof _allLeads !== 'undefined') {
                _allLeads = _campaignData;
            }
        }
        
        // Toggle all checkboxes
        function toggleAllLeads(source) {
            const checkboxes = document.querySelectorAll('.lead-cb');
            checkboxes.forEach(cb => {
                cb.checked = source.checked;
            });
        }
        
        // Edit lead from panel - uses campaign data
        function openEditLeadFromPanel(leadId) {
            if (typeof unifiedLeadsOpenEdit === 'function') {
                const opened = unifiedLeadsOpenEdit(leadId, _campaignData);
                if (opened !== false) closeSidePanel();
                return;
            }
            const lead = _campaignData.find(l => l.id === leadId);
            if(!lead) {
                showToast('Lead non trouvé', 'error');
                return;
            }
            document.getElementById('edit-lead-id').value = lead.id || '';
            document.getElementById('edit-lead-nom').value = lead.nom || '';
            document.getElementById('edit-lead-email').value = lead.email || '';
            document.getElementById('edit-lead-tel').value = lead.telephone || '';
            document.getElementById('edit-lead-site').value = lead.site_web || '';
            if(document.getElementById('edit-lead-sector')) {
                document.getElementById('edit-lead-sector').value = lead.secteur || '';
            }
            if(document.getElementById('edit-lead-ville')) {
                document.getElementById('edit-lead-ville').value = lead.ville || '';
            }
            closeSidePanel();
            document.getElementById('modal-edit-lead').style.display = 'flex';
        }
        
        // Missing functions for side panel
        async function generateEmailForLead(leadId) {
            const lead = _campaignData.find(l => l.id === leadId);
            if(!lead) return;
            try {
                showToast('Génération de l\'email...', 'info');
                const r = await fetch('/api/email/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ lead_nom: lead.nom })
                });
                const d = await r.json();
                if(d.error) {
                    showToast('Erreur: ' + d.error, 'error');
                } else {
                    showToast('✅ Email généré!', 'success');
                    loadPanelContent(leadId, 'email');
                    loadCampaignTable();
                }
            } catch(e) {
                showToast('Erreur: ' + e, 'error');
            }
        }
        
        function previewEmail(leadId) {
            const lead = _campaignData.find(l => l.id === leadId);
            if(!lead || !lead.email_corps) return;
            const win = window.open('', '_blank');
            win.document.write(lead.email_corps);
        }

        function openEmailEditor(leadId) {
            const lead = _campaignData.find(l => l.id === leadId);
            if (!lead) return;

            // Remove any existing instance
            const existing = document.getElementById('email-editor-modal');
            if (existing) existing.remove();

            const esc = s => (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
            const subjectVal = lead.email_objet || '';
            const bodyVal    = lead.email_corps || '';

            const modal = document.createElement('div');
            modal.id = 'email-editor-modal';
            modal.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.75);display:flex;align-items:center;justify-content:center;padding:16px';
            modal.innerHTML = `
                <div style="background:var(--surface);border-radius:16px;width:100%;max-width:1140px;height:90vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 32px 80px rgba(0,0,0,.6)">
                    <!-- Header -->
                    <div style="padding:18px 24px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:14px;flex-shrink:0">
                        <div style="width:36px;height:36px;background:var(--accent);border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        </div>
                        <div style="flex:1;min-width:0">
                            <div style="font-size:11px;color:var(--ink3);margin-bottom:5px;font-weight:600;text-transform:uppercase;letter-spacing:.5px">&#201;dition de l'email &mdash; ${esc(lead.nom || '')}</div>
                            <input id="eme-subject" type="text" value="${esc(subjectVal)}"
                                style="width:100%;font-size:15px;font-weight:600;background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:7px 12px;color:var(--ink);outline:none;transition:border-color .2s"
                                placeholder="Objet de l'email..."
                                onfocus="this.style.borderColor='var(--accent)'" onblur="this.style.borderColor='var(--border)'">
                        </div>
                        <button id="eme-close" title="Fermer" style="width:34px;height:34px;border-radius:50%;background:var(--surface2);border:1px solid var(--border);cursor:pointer;font-size:16px;color:var(--ink3);display:flex;align-items:center;justify-content:center;flex-shrink:0">&#x2715;</button>
                    </div>
                    <!-- Split body -->
                    <div style="flex:1;display:grid;grid-template-columns:1fr 1fr;overflow:hidden;min-height:0">
                        <!-- HTML editor -->
                        <div style="display:flex;flex-direction:column;border-right:1px solid var(--border)">
                            <div style="padding:7px 16px;font-size:10px;font-weight:700;color:var(--ink3);text-transform:uppercase;letter-spacing:.6px;background:var(--surface2);border-bottom:1px solid var(--border);flex-shrink:0">&#9998; HTML</div>
                            <textarea id="eme-body" spellcheck="false" style="flex:1;resize:none;background:var(--bg);color:var(--ink);font-family:'JetBrains Mono',monospace;font-size:11.5px;line-height:1.6;padding:14px 16px;border:none;outline:none;overflow-y:auto">${esc(bodyVal)}</textarea>
                        </div>
                        <!-- Live preview -->
                        <div style="display:flex;flex-direction:column;overflow:hidden">
                            <div style="padding:7px 16px;font-size:10px;font-weight:700;color:var(--ink3);text-transform:uppercase;letter-spacing:.6px;background:var(--surface2);border-bottom:1px solid var(--border);flex-shrink:0">&#128065; Pr&#233;visualisation</div>
                            <iframe id="eme-preview" style="flex:1;border:none;background:#fff"></iframe>
                        </div>
                    </div>
                    <!-- Footer -->
                    <div style="padding:14px 24px;border-top:1px solid var(--border);display:flex;align-items:center;gap:10px;justify-content:space-between;flex-shrink:0;background:var(--surface)">
                        <div style="font-size:12px;color:var(--ink3)">Les modifications sont enregistr&#233;es dans la base — l'email envoy&#233; sera le version finale.</div>
                        <div style="display:flex;gap:10px">
                            <button id="eme-cancel" class="btn bg1" style="padding:9px 18px">Annuler</button>
                            <button id="eme-save" class="btn bp1" style="padding:9px 18px;min-width:140px">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;vertical-align:-2px"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
                                Enregistrer
                            </button>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);

            // Live preview
            const iframe   = document.getElementById('eme-preview');
            const textarea = document.getElementById('eme-body');

            function _updatePreview() {
                const blob = new Blob([textarea.value], { type: 'text/html' });
                const url  = URL.createObjectURL(blob);
                iframe.src = url;
                iframe.onload = () => URL.revokeObjectURL(url);
            }
            _updatePreview();

            let _previewTimer;
            textarea.addEventListener('input', () => {
                clearTimeout(_previewTimer);
                _previewTimer = setTimeout(_updatePreview, 450);
            });

            // Close
            const _close = () => modal.remove();
            document.getElementById('eme-close').onclick  = _close;
            document.getElementById('eme-cancel').onclick = _close;
            modal.addEventListener('click', e => { if (e.target === modal) _close(); });

            // Save
            document.getElementById('eme-save').onclick = async () => {
                const saveBtn = document.getElementById('eme-save');
                saveBtn.disabled = true;
                saveBtn.textContent = 'Enregistrement...';
                try {
                    const newSubject = document.getElementById('eme-subject').value.trim();
                    const newBody    = textarea.value;
                    const resp = await fetch('/api/email/update', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ lead_id: leadId, objet: newSubject, corps: newBody })
                    });
                    const data = await resp.json();
                    if (data.success) {
                        // Patch in-memory cache
                        const idx = _campaignData.findIndex(l => l.id === leadId);
                        if (idx >= 0) {
                            _campaignData[idx].email_objet = newSubject;
                            _campaignData[idx].email_corps = newBody;
                        }
                        if (typeof showToast === 'function') showToast('\u2705 Email mis \u00e0 jour', 'success');
                        _close();
                        // Refresh side panel
                        if (typeof loadPanelContent === 'function' && typeof _selectedLeadId !== 'undefined' && _selectedLeadId) {
                            loadPanelContent(leadId, 'email');
                        }
                    } else {
                        if (typeof showToast === 'function') showToast('Erreur : ' + (data.error || 'inconnue'), 'error');
                        saveBtn.disabled = false;
                        saveBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;vertical-align:-2px"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>Enregistrer';
                    }
                } catch(err) {
                    if (typeof showToast === 'function') showToast('Erreur r\u00e9seau : ' + err.message, 'error');
                    saveBtn.disabled = false;
                    saveBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;vertical-align:-2px"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>Enregistrer';
                }
            };
        }
        
        async function sendTestEmail(leadId) {
            const lead = _campaignData.find(l => l.id === leadId);
            if(!lead) return;
            try {
                const r = await fetch('/api/email/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ lead_nom: lead.nom })
                });
                const d = await r.json();
                if(d.error) {
                    showToast('Erreur: ' + d.error, 'error');
                } else {
                    showToast('✅ Email de test envoyé!', 'success');
                }
            } catch(e) {
                showToast('Erreur: ' + e, 'error');
            }
        }
        
        function regenerateReport(leadId) {
            if(typeof auditLead === 'function') {
                auditLead(leadId);
            }
        }
        
        function previewReport(leadId) {
            // Fetch fresh data for this lead
            fetch('/api/leads?statut=tous&limit=500')
                .then(r => r.json())
                 .then(d => {
                     const lead = d.leads ? d.leads.find(l => l.id == leadId || l.id === leadId) : null;
                     if(!lead || !lead.nom) {
                         showToast('Lead non trouvé', 'error');
                         return;
                     }
                     
                     // Aligné sur generate_slug() Python : retirer tout sauf alphanum+espaces, puis espaces → tirets
                     const slug = lead.nom.toLowerCase().replace(/[^a-z0-9\s]/g, '').replace(/\s+/g, '-').replace(/^-+|-+$/g, '').slice(0, 50);
                     const lienRapport = lead.lien_rapport || '';
                     
                     console.log('[Preview] lead:', lead.nom, 'lien_rapport:', lienRapport, 'slug:', slug);
                    
                    // Priority 1: Check if local folder exists via API
                    fetch('/api/previews')
                        .then(r => r.json())
                        .then(pd => {
                            console.log('[Preview] previews API:', pd.previews);
                            const preview = pd.previews ? pd.previews.find(p => p.slug === slug || p.slug.includes(slug)) : null;
                            console.log('[Preview] found preview:', preview);
                            
                            if(preview && preview.local) {
                                window.open('/previews/' + slug + '/', '_blank');
                            } else if(lienRapport && lienRapport.startsWith('http')) {
                                window.open(lienRapport, '_blank');
                            } else {
                                showToast('Aucun rapport généré pour ce lead. Cliquer sur "Relancer l\'audit" pour en générer un.', 'error');
                            }
                        })
                        .catch(e => {
                            console.error('[Preview] error:', e);
                            showToast('Erreur: ' + e.message, 'error');
                        });
                })
                .catch(e => {
                    showToast('Erreur: ' + e.message, 'error');
                });
        }
        
        function pushReport(leadId) {
            fetch('/api/leads?statut=tous&limit=500')
                .then(r => r.json())
                .then(async d => {
                    const lead = d.leads ? d.leads.find(l => l.id == leadId || l.id === leadId) : null;
                    if(!lead || !lead.nom) { showToast('Lead non trouvé', 'error'); return; }
                    
                    const slug = makeSlug(lead.nom);
                    const lienRapport = lead.lien_rapport || '';
                    
                    // Vérifier via l'API si un dossier local existe
                    const pd = await fetch('/api/previews').then(r => r.json());
                    const preview = pd.previews ? pd.previews.find(p => p.slug === slug) : null;
                    
                    if(preview && preview.local) {
                        showToast('Publication en cours...', 'info');
                        const pushRes = await fetch('/api/previews/push', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ slugs: [slug] })
                        }).then(r => r.json());
                        if(pushRes.results && pushRes.results[0] && pushRes.results[0].status === 'published') {
                            showToast('✅ Rapport publié : ' + pushRes.results[0].url, 'success');
                            loadPanelContent(leadId, 'audit');
                            loadCampaignTable();
                        } else {
                            showToast('Erreur: ' + (pushRes.results ? pushRes.results[0].message : pushRes.error || 'Inconnu'), 'error');
                        }
                    } else if(lienRapport && lienRapport.startsWith('https://')) {
                        showToast('Rapport déjà en ligne : ' + lienRapport, 'info');
                    } else {
                        showToast('Aucun rapport local trouvé. Lancer l\'audit d\'abord.', 'warning');
                    }
                })
                .catch(e => showToast('Erreur: ' + e.message, 'error'));
        }
        
        function launchAuditForLead(leadId) {
            const lead = _campaignData.find(l => l.id === leadId);
            if(!lead || !lead.nom) {
                showToast('Lead non trouvé', 'error');
                return;
            }
            if(typeof auditLead === 'function') {
                auditLead(lead.id);
            }
        }
        
        async function regenerateAudit(leadId) {
            const lead = _campaignData.find(l => l.id === leadId);
            if(!lead || !lead.nom) {
                showToast('Lead non trouvé', 'error');
                return;
            }
            
            showToast('Lancement de l\'audit pour ' + lead.nom + '...', 'info');
            
            // Vider le contenu du panel pour éviter d'afficher l'ancien rapport
            const content = document.getElementById('panel-content');
            if (content) {
                content.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--ink3)"><div style="font-size:24px;margin-bottom:8px">⏳</div>Audit en cours pour <strong>' + escHtml(lead.nom) + '</strong>...</div>';
            }
            
            const globalProgress = document.getElementById('sidebar-audit');
            if (globalProgress) globalProgress.style.display = 'block';
            
            // Lancer l'audit — le cleanup est déjà fait dans app.py avant chaque lancement
            fetch('/api/audit/launch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lead_ids: [lead.id] })
            })
            .then(r => r.json())
            .then(data => {
                if(data.error) {
                    showToast('Erreur: ' + data.error, 'error');
                    if (globalProgress) globalProgress.style.display = 'none';
                    loadPanelContent(leadId, 'audit');
                    return;
                }
                showToast('Audit démarré...', 'info');
                pollAuditCompletion(leadId, 0);
            })
            .catch(e => {
                showToast('Erreur: ' + e.message, 'error');
                if (globalProgress) globalProgress.style.display = 'none';
                loadPanelContent(leadId, 'audit');
            });
        }
        
function pollAuditCompletion(leadId, attempts) {
    const maxAttempts = 150; // 5 minutes max (2s × 150)
    const globalProgress = document.getElementById('sidebar-audit');
    const textEl = document.getElementById('sidebar-audit-text');
    const pctEl = document.getElementById('sidebar-audit-pct');
    const barEl = document.getElementById('sidebar-audit-bar');
    
    fetch('/api/audit/status')
        .then(r => r.json())
        .then(status => {
            if(status.running) {
                // Mettre à jour la barre de progression
                const total = status.total || 1;
                const current = status.current || 0;
                const pct = total > 0 ? Math.round((current / total) * 100) : Math.min(attempts * 2, 90);
                if(textEl) textEl.innerHTML = `<strong>${current}</strong>/${total} audité(s) — en cours...`;
                if(pctEl) pctEl.textContent = pct + '%';
                if(barEl) barEl.style.width = pct + '%';
                
                attempts++;
                if(attempts >= maxAttempts) {
                    if(globalProgress) globalProgress.style.display = 'none';
                    showToast('⏳ L\'audit continue en arrière-plan (>5min)', 'warning');
                    loadPanelContent(leadId, 'audit');
                    loadCampaignTable();
                    return;
                }
                setTimeout(() => pollAuditCompletion(leadId, attempts), 2000);
                return;
            }
            
            // Audit terminé
            if(globalProgress) globalProgress.style.display = 'none';
            if(status.current > 0 && (status.failed || 0) === 0) {
                showToast('✅ Audit terminé avec succès !', 'success');
            } else if((status.failed || 0) > 0) {
                showToast(`⚠️ Audit : ${status.current - status.failed} OK, ${status.failed} échec(s)`, 'warning');
            } else {
                showToast('Audit terminé', 'info');
            }
            loadPanelContent(leadId, 'audit');
            loadCampaignTable();
        })
        .catch(e => {
            attempts++;
            if(attempts >= maxAttempts) {
                if(globalProgress) globalProgress.style.display = 'none';
                showToast('Timeout - audit en arrière-plan', 'warning');
                loadPanelContent(leadId, 'audit');
                return;
            }
            setTimeout(() => pollAuditCompletion(leadId, attempts), 2000);
        });
}
        
        // Debounced search
        let _searchTimer = null;
        function _debouncedSearch() {
            clearTimeout(_searchTimer);
            _searchTimer = setTimeout(() => loadCampaignTable(), 300);
        }

        // Initialize
        document.addEventListener('DOMContentLoaded', function() {
            const savedPage = getSavedPage();
            const navEl = document.getElementById('nav-' + savedPage);
            nav(savedPage, navEl);
            if(typeof loadStats === 'function') loadStats();

            // Vérification silencieuse de la santé système pour colorer le dot dans la nav
            setTimeout(() => {
                fetch('/api/health')
                    .then(r => r.json())
                    .then(data => {
                        const navDot = document.getElementById('health-dot');
                        if (navDot) navDot.style.background = _overallColors[data.status] || '#6b7280';
                    })
                    .catch(() => {});
            }, 1500);

            // Restaurer un audit de masse interrompu par un refresh
            const saved = localStorage.getItem('_massAudit');
            if (saved) {
                try {
                    const s = JSON.parse(saved);
                    if (s.queue && s.index < s.total) {
                        _massAuditQueue = s.queue;
                        _massAuditIndex = s.index;
                        _massAuditTotal = s.total;
                        // Vérifier si un audit tourne encore côté serveur
                        fetch('/api/audit/status').then(r => r.json()).then(st => {
                            const globalProgress = document.getElementById('sidebar-audit');
                            const textEl = document.getElementById('sidebar-audit-text');
                            if (st.running) {
                                // Reprendre le polling là où on en était
                                if(globalProgress) globalProgress.style.display = 'block';
                                const nom = _massAuditQueue[_massAuditIndex] || '';
                                if(textEl) textEl.innerHTML = `<strong>Audit en cours</strong> (${_massAuditIndex + 1}/${_massAuditTotal}) : ${escHtml(nom)} <em style="font-size:10px;opacity:.7">(repris)</em>`;
                                showToast(`Audit repris : ${_massAuditIndex + 1}/${_massAuditTotal}`, 'info');
                                _pollMassAuditUntilDone(() => { _massAuditIndex++; _runNextMassAudit(); });
                            } else {
                                // Le serveur a fini — continuer avec le prochain lead
                                _massAuditIndex++;
                                _runNextMassAudit();
                            }
                        }).catch(() => { _clearMassAuditState(); });
                    } else {
                        _clearMassAuditState();
                    }
                } catch(e) { _clearMassAuditState(); }
            }
        });
        
        // ============================================================
        // AUDIT DE MASSE — traite 1 à 1 avec progression
        // ============================================================
        let _massAuditQueue = [];
        let _massAuditIndex = 0;
        let _massAuditTotal = 0;

        function launchSelectedAudits() {
            const checkboxes = document.querySelectorAll('.lead-cb:checked');
            if(checkboxes.length === 0) {
                // Aucune sélection : utiliser auditSelected() du module audits.js
                if(typeof auditSelected === 'function') {
                    auditSelected();
                } else {
                    showToast('Sélectionner au moins un lead', 'error');
                }
                return;
            }
            
            const noms = Array.from(checkboxes).map(cb => {
                const id = cb.dataset.id;
                const lead = _campaignData.find(l => l.id == id)
                          || (typeof _allLeads !== 'undefined' && _allLeads.find(l => l.id == id));
                return lead ? lead.nom : (cb.dataset.nom || null);
            }).filter(Boolean);

            if(noms.length === 0) return showToast('Aucun lead valide', 'error');
            
            _massAuditQueue = noms;
            _massAuditIndex = 0;
            _massAuditTotal = noms.length;
            
            showToast(`Audit de masse : ${_massAuditTotal} prospect(s) en file...`, 'info');
            _runNextMassAudit();
        }

        function _saveMassAuditState() {
            localStorage.setItem('_massAudit', JSON.stringify({
                queue: _massAuditQueue, index: _massAuditIndex, total: _massAuditTotal
            }));
        }
        function _clearMassAuditState() { localStorage.removeItem('_massAudit'); }

        function _runNextMassAudit() {
            _saveMassAuditState();
            if(_massAuditIndex >= _massAuditTotal) {
                showToast(`✅ ${_massAuditTotal} audits terminés — affichage de tous les statuts`, 'success');
                _clearMassAuditState();
                // Retirer le filtre "en_attente" pour montrer les leads audités
                const statutEl = document.getElementById('filter-statut');
                if (statutEl && statutEl.value === 'en_attente') statutEl.value = 'tous';
                _campPage = 1;
                loadCampaignTable();
                if(typeof loadStats === 'function') loadStats();
                const globalProgress = document.getElementById('sidebar-audit');
                if (globalProgress) globalProgress.style.display = 'none';
                return;
            }
            
            const nom = _massAuditQueue[_massAuditIndex];
            const progressNum = _massAuditIndex + 1;
            
            // Afficher la progression dans la sidebar
            const globalProgress = document.getElementById('sidebar-audit');
            const textEl = document.getElementById('sidebar-audit-text');
            const pctEl = document.getElementById('sidebar-audit-pct');
            const barEl = document.getElementById('sidebar-audit-bar');
            if(globalProgress) globalProgress.style.display = 'block';
            if(textEl) textEl.innerHTML = `<strong>Audit en cours</strong> (${progressNum}/${_massAuditTotal}) : ${escHtml(nom)}`;
            const pct = Math.round(((_massAuditIndex) / _massAuditTotal) * 100);
            if(pctEl) pctEl.textContent = pct + '%';
            if(barEl) barEl.style.width = pct + '%';
            
            showToast(`Audit ${progressNum}/${_massAuditTotal} : ${nom}`, 'info');
            
            fetch('/api/audit/launch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lead_names: [nom] })
            })
            .then(r => r.json())
            .then(data => {
                if(data.error && data.error.includes('déjà en cours')) {
                    // Attendre et réessayer
                    setTimeout(_runNextMassAudit, 5000);
                    return;
                }
                if(data.error) {
                    showToast(`Erreur pour ${nom}: ${data.error}`, 'error');
                    _massAuditIndex++;
                    setTimeout(_runNextMassAudit, 1000);
                    return;
                }
                // Attendre la fin de cet audit avant de passer au suivant
                _saveMassAuditState();
                _pollMassAuditUntilDone(() => {
                    _massAuditIndex++;
                    _runNextMassAudit();
                });
            })
            .catch(e => {
                showToast(`Erreur réseau pour ${nom}: ${e.message}`, 'error');
                _massAuditIndex++;
                setTimeout(_runNextMassAudit, 2000);
            });
        }

        function _pollMassAuditUntilDone(callback, attempts = 0) {
            const MAX = 200; // ~6.5 min (2s × 200)
            fetch('/api/audit/status')
                .then(r => r.json())
                .then(status => {
                    if(status.running) {
                        const nom = _massAuditQueue[_massAuditIndex] || '';
                        const textEl = document.getElementById('sidebar-audit-text');
                        const pctEl  = document.getElementById('sidebar-audit-pct');
                        const barEl  = document.getElementById('sidebar-audit-bar');
                        const total  = status.total || _massAuditTotal || 1;
                        const done   = status.current || 0;
                        const pct    = Math.round(((_massAuditIndex + done / Math.max(total, 1)) / _massAuditTotal) * 100);
                        if(textEl) textEl.innerHTML = `<strong>Audit en cours</strong> (${_massAuditIndex + 1}/${_massAuditTotal}) : ${escHtml(nom)}`;
                        if(pctEl) pctEl.textContent = pct + '%';
                        if(barEl) barEl.style.width = pct + '%';
                        // Rafraîchir la table toutes les 10 secondes pour montrer les statuts
                        if(attempts % 5 === 4) loadCampaignTable();
                        if(attempts < MAX) setTimeout(() => _pollMassAuditUntilDone(callback, attempts + 1), 2000);
                        else { showToast('Audit toujours en cours (>6min) — refresh manuel', 'warning'); callback(); }
                    } else {
                        // Audit du lead terminé — rafraîchir immédiatement sans filtre statut
                        const statutEl = document.getElementById('filter-statut');
                        const prevFilter = statutEl ? statutEl.value : 'tous';
                        if (statutEl && prevFilter === 'en_attente') statutEl.value = 'tous';
                        loadCampaignTable();
                        if (statutEl && prevFilter === 'en_attente') {
                            // Remettre le filtre après le chargement pour ne pas désorienter
                            // (on le laisse sur "tous" pour que l'utilisateur voie le lead audité)
                        }
                        callback();
                    }
                })
                .catch(() => {
                    if(attempts < MAX) setTimeout(() => _pollMassAuditUntilDone(callback, attempts + 1), 2000);
                    else callback();
                });
        }
        
        function generateSelectedEmails() {
            // Get selected leads and generate emails
            const checkboxes = document.querySelectorAll('.lead-cb:checked, .ul-cb:checked');
            if (checkboxes.length === 0) {
                showToast('Sélectionner au moins un lead', 'error');
                return;
            }
            // IDs only
            const ids = Array.from(checkboxes).map(cb => Number(cb.dataset.id || cb.value)).filter(Boolean);
            if (ids.length === 0) {
                showToast('Aucun lead valide sélectionné', 'error');
                return;
            }
            showToast('Génération des emails pour ' + ids.length + ' leads...', 'info');

            fetch('/api/email/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lead_ids: ids })
            })
            .then(r => r.json())
            .then(d => {
                if (d.error) {
                    showToast('Erreur: ' + d.error, 'error');
                } else {
                    showToast('✅ Emails générés!', 'success');
                    loadCampaignTable?.();
                }
            })
            .catch(e => {
                showToast('Erreur: ' + e.message, 'error');
            });
        }
        
        function sendApprovedEmails() {
            showToast('Envoi des emails approuvés...', 'info');
            fetch('/api/email/send-approved', { 
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            })
            .then(r => r.json())
            .then(d => {
                if(d.error) {
                    showToast('Erreur: ' + d.error, 'error');
                } else {
                    showToast('✅ ' + (d.sent || 0) + ' emails envoyés!', 'success');
                    loadCampaignTable();
                }
            })
            .catch(e => {
                showToast('Erreur: ' + e.message, 'error');
            });
        }
        
        function pushSelectedToGitHub() {
            const checkboxes = document.querySelectorAll('.lead-cb:checked');
            if(checkboxes.length === 0) {
                showToast('Sélectionner au moins un lead', 'error');
                return;
            }
            
            const slugs = Array.from(checkboxes).map(cb => {
                const lead = _campaignData.find(l => l.id == cb.dataset.id);
                return lead ? lead.nom.toLowerCase().replace(/[^a-z0-9]/g, '-') : null;
            }).filter(s => s);
            
            if(slugs.length === 0) {
                showToast('Aucun lead valide sélectionné', 'error');
                return;
            }
            
            showToast('Publication de ' + slugs.length + ' rapports sur GitHub...', 'info');
            
            let pushed = 0;
            slugs.forEach((slug, idx) => {
                setTimeout(() => {
                    fetch('/api/previews/push', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ slugs: [slug] })
                    })
                    .then(r => r.json())
                    .then(d => {
                        pushed++;
                        if(idx === slugs.length - 1) {
                            showToast('✅ ' + pushed + ' rapports publiés sur GitHub!', 'success');
                            loadCampaignTable();
                            // Reload panel if a lead is selected
                            if(_selectedLeadId) {
                                loadPanelContent(_selectedLeadId, 'audit');
                            }
                        }
                    })
                    .catch(e => {
                        showToast('Erreur: ' + e.message, 'error');
                    });
                }, idx * 2000);
            });
        }

        // ============================================================
        // DATE RANGE PICKER — un mois, reste ouvert entre les 2 clics
        // ============================================================
        let _drpStart = null, _drpEnd = null, _drpOpen = false, _drpHover = null;
        let _drpView  = new Date();
        const _DRP_M  = ['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'];
        const _drpFmt = s => s ? s.split('-').reverse().join('/') : '';

        function _drpToggle() {
            _drpOpen = !_drpOpen;
            document.getElementById('drp-popup').style.display = _drpOpen ? 'block' : 'none';
            if (_drpOpen) _drpRender();
        }

        function _drpClose() {
            _drpOpen = false;
            document.getElementById('drp-popup').style.display = 'none';
        }

        function _drpRender() {
            const y = _drpView.getFullYear(), m = _drpView.getMonth();
            document.getElementById('drp-month-label').textContent = _DRP_M[m] + ' ' + y;

            const today  = new Date().toISOString().slice(0, 10);
            const offset = (() => { const d = new Date(y, m, 1).getDay(); return d === 0 ? 6 : d - 1; })();
            const total  = new Date(y, m + 1, 0).getDate();
            const tip    = _drpEnd || (_drpStart && _drpHover ? _drpHover : null);
            const lo     = _drpStart && tip ? (_drpStart < tip ? _drpStart : tip) : _drpStart;
            const hi     = _drpStart && tip ? (_drpStart < tip ? tip : _drpStart) : _drpStart;

            let html = '';
            for (let i = 0; i < offset; i++) html += '<div></div>';

            for (let day = 1; day <= total; day++) {
                const ds     = y + '-' + String(m+1).padStart(2,'0') + '-' + String(day).padStart(2,'0');
                const isLo   = ds === lo;
                const isHi   = ds === hi && lo !== hi;
                const isOnly = ds === lo && lo === hi;
                const inRng  = lo && hi && ds > lo && ds < hi;
                const isDay  = ds === today;

                let bg = '', fg = 'var(--ink)', fw = '400', br = '6px', brd = 'none';
                if (isLo || isHi || isOnly) {
                    bg = 'var(--accent)'; fg = '#fff'; fw = '700';
                    br = isOnly ? '6px' : isLo ? '6px 0 0 6px' : '0 6px 6px 0';
                } else if (inRng) {
                    bg = 'rgba(16,185,129,0.13)'; fg = 'var(--accent)'; br = '0';
                } else if (isDay) {
                    brd = '1.5px solid var(--accent)'; fg = 'var(--accent)'; fw = '600';
                }

                html += `<div onclick="_drpClick('${ds}')" onmouseenter="_drpIn('${ds}')" onmouseleave="_drpOut()"
                    style="text-align:center;padding:6px 1px;font-size:12px;cursor:pointer;border-radius:${br};
                    background:${bg};color:${fg};font-weight:${fw};border:${brd};user-select:none;transition:background .08s,color .08s">${day}</div>`;
            }

            document.getElementById('drp-grid').innerHTML = html;

            const foot = document.getElementById('drp-footer');
            if (!_drpStart) {
                foot.innerHTML = 'Choisissez la <strong>date de début</strong>';
            } else if (!_drpEnd) {
                foot.innerHTML = `<span style="color:var(--accent);font-weight:600">${_drpFmt(_drpStart)}</span> &rarr; Choisissez la <strong>date de fin</strong>`;
            } else {
                foot.innerHTML = `<span style="color:var(--accent);font-weight:600">${_drpFmt(_drpStart)}</span> &rarr; <span style="color:var(--accent);font-weight:600">${_drpFmt(_drpEnd)}</span>`;
            }
        }

        function _drpIn(ds) {
            if (_drpStart && !_drpEnd) { _drpHover = ds; _drpRender(); }
        }
        function _drpOut() {
            if (_drpStart && !_drpEnd) { _drpHover = null; _drpRender(); }
        }

        function _drpClick(ds) {
            if (!_drpStart || (_drpStart && _drpEnd)) {
                _drpStart = ds; _drpEnd = null; _drpHover = null;
                _drpRender();
            } else {
                if (ds === _drpStart) { _drpStart = null; _drpHover = null; _drpRender(); return; }
                if (ds < _drpStart) { _drpEnd = _drpStart; _drpStart = ds; }
                else { _drpEnd = ds; }
                _drpHover = null;
                _drpRender();
                setTimeout(_drpApply, 180);
            }
        }

        function _drpPrevMonth() {
            _drpView = new Date(_drpView.getFullYear(), _drpView.getMonth() - 1, 1);
            _drpRender();
        }
        function _drpNextMonth() {
            _drpView = new Date(_drpView.getFullYear(), _drpView.getMonth() + 1, 1);
            _drpRender();
        }

        function _drpApply() {
            if (!_drpStart || !_drpEnd) return;
            document.getElementById('global-date-start').value = _drpStart;
            document.getElementById('global-date-end').value   = _drpEnd;
            _activeDateStart = _drpStart;
            _activeDateEnd   = _drpEnd;
            const lbl = document.getElementById('drp-label');
            lbl.textContent = _drpFmt(_drpStart) + ' → ' + _drpFmt(_drpEnd);
            lbl.style.color = 'var(--ink)';
            document.getElementById('drp-clear').style.display = 'inline';
            _drpClose();
            showToast('Période : ' + _drpFmt(_drpStart) + ' → ' + _drpFmt(_drpEnd));
            refreshAll();
        }

        function _drpReset() {
            _drpStart = null; _drpEnd = null; _drpHover = null;
            document.getElementById('global-date-start').value = '';
            document.getElementById('global-date-end').value   = '';
            const lbl = document.getElementById('drp-label');
            lbl.textContent = 'Période';
            lbl.style.color = 'var(--ink3)';
            document.getElementById('drp-clear').style.display = 'none';
        }

        // Fermer en cliquant en dehors
        document.addEventListener('click', function(e) {
            if (!_drpOpen) return;
            if (!document.getElementById('drp-trigger').contains(e.target) &&
                !document.getElementById('drp-popup').contains(e.target)) _drpClose();
        });

        // ============================================================
        // MODULE 5: ANALYTICS & BUSINESS INTELLIGENCE
        // ============================================================
        function loadRoiData() {
            showToast('Actualisation des données de ROI...', 'info');
            
            // Charger les statistiques globales du funnel
            fetch('/api/stats/funnel')
                .then(r => r.json())
                .then(data => {
                    const scraped = data.total_scraped || 0;
                    const audited = Math.min(data.total_audited || 0, scraped); // sécurité visuelle
                    const sent = data.total_sent || 0;
                    const clicked = data.total_clicked || 0;
                    const replied = data.total_replied || 0;
                    const rdv = data.total_rdv || 0;
                    
                    document.getElementById('roi-scraped').textContent = scraped;
                    document.getElementById('roi-audited').textContent = audited;
                    document.getElementById('roi-sent2').textContent = sent;
                    document.getElementById('roi-clicked').textContent = clicked;
                    document.getElementById('roi-replied').textContent = replied;
                    
                    const roiSentEl = document.getElementById('roi-sent');
                    if(roiSentEl) roiSentEl.textContent = sent;
                    
                    const roiRdvEl = document.getElementById('roi-rdv');
                    if(roiRdvEl) roiRdvEl.textContent = rdv;
                    
                    const ctr = sent > 0 ? ((clicked / sent) * 100).toFixed(1) + '%' : '—';
                    const rep = sent > 0 ? ((replied / sent) * 100).toFixed(1) + '%' : '—';
                    
                    const roiCtrEl = document.getElementById('roi-ctr');
                    if(roiCtrEl) roiCtrEl.textContent = ctr;
                    
                    const roiRepEl = document.getElementById('roi-reply');
                    if(roiRepEl) roiRepEl.textContent = rep;
                })
                .catch(e => console.error("Erreur funnel:", e));
                
            // Charger les performances par niche
            fetch('/api/stats/niche')
                .then(r => r.json())
                .then(niches => {
                    const tbody = document.getElementById('tbody-niches');
                    if(niches.error) {
                         tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--red)">Erreur de chargement.</td></tr>';
                         return;
                    }
                    if(!niches || niches.length === 0) {
                         tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--ink3)">Pas de données suffisantes pour déterminer les top niches (>5 envois nécessaires).</td></tr>';
                         return;
                    }
                    
                    tbody.innerHTML = niches.map(n => `
                        <tr>
                            <td><div style="font-weight:600;color:var(--ink)">${escHtml(n.category || '—')}</div></td>
                            <td>${escHtml(n.ville || '—')}</td>
                            <td>${n.envois}</td>
                            <td>${n.clics}</td>
                            <td>
                                <div style="display:flex;align-items:center;gap:8px">
                                    <div style="flex:1;height:6px;background:var(--surface2);border-radius:3px;overflow:hidden">
                                        <div style="height:100%;width:${Math.min(100, (n.clics / Math.max(1, n.envois)) * 100).toFixed(1)}%;background:var(--accent);border-radius:3px"></div>
                                    </div>
                                    <span style="font-weight:600;font-size:12px;width:35px;text-align:right">${((n.clics / Math.max(1, n.envois)) * 100).toFixed(1)}%</span>
                                </div>
                            </td>
                        </tr>
                    `).join('');
                })
                .catch(e => console.error("Erreur niche:", e));
                
            // Charger les résultats de l'A/B Testing
            fetch('/api/stats/ab_test')
                .then(r => r.json())
                .then(ab => {
                    const tbody = document.getElementById('tbody-abtest');
                    if(ab.error) {
                        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--red)">Erreur de chargement.</td></tr>';
                        return;
                    }
                    if(!ab || ab.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--ink3)">Pas de données A/B testing (Il faut des envois).</td></tr>';
                        return;
                    }
                    
                    tbody.innerHTML = ab.map(r => {
                        const openRate = r.envois > 0 ? ((r.ouverts / r.envois) * 100).toFixed(1) : 0;
                        const clickRate = r.envois > 0 ? ((r.clics / r.envois) * 100).toFixed(1) : 0;
                        const replyRate = r.envois > 0 ? ((r.reponses / r.envois) * 100).toFixed(1) : 0;
                        
                        return `
                        <tr>
                            <td><span style="font-weight:600">Profil ${r.profile}</span></td>
                            <td><span class="status-badge" style="background:var(--accent-light);color:var(--accent)">${r.variant}</span></td>
                            <td>${r.envois}</td>
                            <td>${r.ouverts} <span style="font-size:10px;color:var(--ink3)">(${openRate}%)</span></td>
                            <td>${r.clics} <span style="font-size:10px;color:var(--ink3)">(${clickRate}%)</span></td>
                            <td>${r.reponses} <span style="font-size:10px;color:var(--ink3)">(${replyRate}%)</span></td>
                        </tr>
                    `}).join('');
                })
                .catch(e => console.error("Erreur AB Test:", e));
        }

        // Add hook to the Navigation router to automatically load ROI data when navigating to the ROI tab
        const originalNav = window.nav;
        window.nav = function(page, el) {
            if(originalNav) originalNav(page, el);
            if(page === 'roi') {
                loadRoiData();
            }
        };
        
        // ═══════════════════════════════════════════════════════
