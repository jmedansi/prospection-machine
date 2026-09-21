/**
 * dashboard/static/js/modules/v6_shell.js
 * Noyau UI du dashboard V6 — interface 100 % modèle v2 (campagnes/listes/prospects).
 *
 * Remplace les fonctions de navigation autrefois fournies par dashboard_core.js
 * (nav, switchSectionTab) et relaie les inits v2 par onglet. Chargé EN DERNIER
 * dans dashboard_v6.html pour écraser les définitions de ui.js (nav/tab).
 *
 * Sections connues de la V6 :
 *   cockpit · suivi · campagne (leads | listes | sources) · planificateur · tasks · settings
 */
(function () {
    'use strict';

    window.V6_MODE = true;

    var SECTION_TITLES = {
        cockpit: 'Cockpit', suivi: 'Suivi', campagne: 'Prospection', planificateur: 'Planning',
        tasks: 'Console Tâches', settings: 'Paramètres'
    };
    var KNOWN_PAGES = ['cockpit', 'suivi', 'campagne', 'planificateur', 'tasks', 'settings'];

    // ── Init par onglet (équivalent V2 de dashboard_core._loadDataForSubTab) ──
    function v6LoadSubTab(tabName) {
        if (tabName === 'leads' || tabName === 'leads_unified') {
            if (typeof unifiedLeadsInit === 'function') unifiedLeadsInit();
            if (window.ActionsModule && typeof ActionsModule.init === 'function') ActionsModule.init();
        } else if (tabName === 'listes') {
            if (window.ListesModule && typeof ListesModule.init === 'function') ListesModule.init();
        } else if (tabName === 'sources') {
            if (typeof sourcesInit === 'function') sourcesInit();
        } else if (['settings_gen', 'setting_profil', 'setting_api', 'setting_system', 'setting_boites'].indexOf(tabName) !== -1) {
            if (typeof loadSettings === 'function') loadSettings();
        } else if (tabName === 'health') {
            if (typeof runHealthCheck === 'function') runHealthCheck();
        } else if (tabName === 'logs') {
            if (typeof loadLogs === 'function') loadLogs();
        } else if (tabName === 'tasks') {
            // TaskConsole s'auto-initialise au chargement global (bind WS + refresh).
            // Ici on refraîchit simplement à chaque navigation — jamais de double bind.
            if (typeof TaskConsole !== 'undefined' && typeof TaskConsole.refreshTasks === 'function') {
                TaskConsole.refreshTasks();
            }
        }
    }

    function v6LoadSection(page) {
        if (page === 'cockpit') {
            if (typeof loadStats === 'function') loadStats();
            if (typeof loadConfig === 'function') loadConfig();
        } else if (page === 'suivi') {
            if (window.SuiviModule && typeof SuiviModule.init === 'function') SuiviModule.init();
        } else if (page === 'campagne') {
            var active = document.querySelector('#section-campagne .section-tab.active');
            if (active) {
                var m = active.getAttribute('onclick').match(/'([^']+)'/);
                if (m) v6LoadSubTab(m[1]);
            }
        } else if (page === 'tasks') {
            v6LoadSubTab('tasks');
        } else if (page === 'planificateur') {
            if (typeof initPlanificateur === 'function') initPlanificateur();
        } else if (page === 'settings') {
            var act = document.querySelector('#section-settings .section-tab.active');
            if (act) {
                var mm = act.getAttribute('onclick').match(/'([^']+)'/);
                if (mm) v6LoadSubTab(mm[1]);
            }
        }
    }

    function setPT(label) {
        var pt = document.getElementById('PT');
        if (pt) pt.textContent = label;
    }

    // ── Navigation (reprend l'algo de dashboard_core, réduit au périmètre V6) ──
    window.nav = function (page, el) {
        var subtab = null;
        if (page === 'leads' || page === 'listes' || page === 'sources') {
            subtab = page;
            page = 'campagne';
        }

        if (KNOWN_PAGES.indexOf(page) === -1) {
            if (typeof showToast === 'function') showToast('Section indisponible dans la V6', 'info');
            page = 'cockpit';
        }

        localStorage.setItem('pm_current_page', page);

        document.querySelectorAll('.ni, .mobile-nav-item').forEach(function (n) { n.classList.remove('active'); });

        var highlightId = subtab || page;
        var desktopNav = document.getElementById('nav-' + highlightId) || document.getElementById('nav-' + page);
        if (desktopNav) desktopNav.classList.add('active');

        var mobileNav = document.getElementById('nav-' + highlightId + '-m') || document.getElementById('nav-' + page + '-m');
        if (mobileNav) mobileNav.classList.add('active');

        // Masquer toutes les sections (y compris la Console Tâches, classe .content-section)
        document.querySelectorAll('.v-section').forEach(function (s) { s.classList.remove('active'); });
        var tasks = document.getElementById('section-tasks');
        if (tasks) tasks.classList.remove('active');

        var target = document.getElementById('section-' + page);
        if (target) {
            target.classList.add('active');

            var savedSubtab = localStorage.getItem('pm_subtab_section-' + page);
            var subtabToUse = subtab || savedSubtab;
            if (subtabToUse) {
                var tabBtn = target.querySelector('.section-tab[onclick*="\'' + subtabToUse + '\'"]');
                if (tabBtn) {
                    switchSectionTab(subtabToUse, tabBtn);
                } else {
                    v6LoadSection(page);
                }
            } else {
                var activeTabBtn = target.querySelector('.section-tab.active');
                if (activeTabBtn) {
                    var m2 = activeTabBtn.getAttribute('onclick').match(/'([^']+)'/);
                    if (m2) { switchSectionTab(m2[1], activeTabBtn); }
                    else { v6LoadSection(page); }
                } else {
                    v6LoadSection(page);
                }
            }
        } else {
            v6LoadSection(page);
        }

        var displayTitle = subtab === 'leads' ? 'Leads'
            : subtab === 'listes' ? 'Listes'
            : subtab === 'sources' ? 'Sources'
            : (SECTION_TITLES[page] || page);
        setPT(displayTitle);
    };

    // ── Bascule d'onglet (sous-sections) ──
    window.switchSectionTab = function (tabName, el) {
        if (!el) return;
        var tabsContainer = el.closest('.section-tabs');
        if (!tabsContainer) return;
        var parentSection = tabsContainer.parentElement;

        tabsContainer.querySelectorAll('.section-tab').forEach(function (t) { t.classList.remove('active'); });
        el.classList.add('active');

        if (parentSection && parentSection.id) {
            localStorage.setItem('pm_subtab_' + parentSection.id, tabName);
        }

        Array.from(parentSection.children).forEach(function (child) {
            if (child.classList.contains('subtab-content')) child.style.display = 'none';
        });

        var targetContent = document.getElementById('subtab-' + tabName);
        if (targetContent) {
            targetContent.style.display = 'block';
            v6LoadSubTab(tabName);
        }
    };

    // ── FAB mobile : « nouveau lead » v2 = aiguiller vers la création de campagne ──
    if (typeof window.openNewLeadModal !== 'function') {
        window.openNewLeadModal = function () {
            if (window.CampagnesModule && typeof window.CampagnesModule.openCreate === 'function') {
                CampagnesModule.openCreate();
            } else if (typeof showToast === 'function') {
                showToast('Créez d\'abord une campagne dans la topbar (+)', 'info');
            }
        };
    }

    // ── Boot ──
    document.addEventListener('DOMContentLoaded', function () {
        var saved = localStorage.getItem('pm_current_page') || 'cockpit';
        if (saved === 'campagne') {
            var st = localStorage.getItem('pm_subtab_section-campagne');
            saved = (st === 'sources' || st === 'listes') ? st : 'leads';
        }
        if (['cockpit', 'suivi', 'campagne', 'leads', 'listes', 'sources', 'planificateur', 'tasks', 'settings'].indexOf(saved) === -1) {
            saved = 'cockpit';
        }
        window.nav(saved, document.getElementById('nav-' + saved));

        // Sélecteur de campagne (topbar) + état v2, puis stats cockpit campagne-aware
        if (window.CampagnesModule && typeof CampagnesModule.init === 'function') window.CampagnesModule.init();
        if (window.ActionsModule && typeof ActionsModule.init === 'function') ActionsModule.init();
        if (typeof loadStats === 'function') loadStats();
        if (typeof loadConfig === 'function') loadConfig();
    });
})();