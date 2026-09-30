/**
 * dashboard/static/js/modules/relances_calendar.js
 * Calendrier interactif des relances (modèle v2 en jours ouvrés).
 */
window.RelancesCalendarModule = (function () {
    'use strict';

    var MONTH_NAMES_FR = [
        'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
    ];

    var DAY_NAMES_FR = [
        'Dimanche', 'Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi'
    ];

    var state = {
        currentYear: new Date().getFullYear(),
        currentMonth: new Date().getMonth(), // 0-indexed
        selectedDate: null,
        campagneFilter: '',
        listeFilter: '',
        stepFilter: '',
        rawApiResponse: null,
        isLoading: false
    };

    function init() {
        var now = new Date();
        state.currentYear = now.getFullYear();
        state.currentMonth = now.getMonth();
        state.selectedDate = formatDateYMD(now);
        loadData();
    }

    function formatDateYMD(d) {
        var y = d.getFullYear();
        var m = String(d.getMonth() + 1).padStart(2, '0');
        var day = String(d.getDate()).padStart(2, '0');
        return y + '-' + m + '-' + day;
    }

    function parseDateYMD(str) {
        if (!str) return new Date();
        var parts = str.split('-');
        return new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
    }

    function loadData() {
        state.isLoading = true;
        var url = '/api/v2/relances/calendar';
        var params = [];
        if (state.campagneFilter) params.push('campagne_id=' + encodeURIComponent(state.campagneFilter));
        if (state.listeFilter) params.push('liste_id=' + encodeURIComponent(state.listeFilter));
        if (params.length) url += '?' + params.join('&');

        fetch(url)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                state.isLoading = false;
                if (!data.success) {
                    if (typeof showToast === 'function') showToast('Erreur chargement calendrier: ' + (data.error || 'inconnue'), 'error');
                    return;
                }
                state.rawApiResponse = data;
                updateKPIs(data.summary);
                populateCampagnesFilter(data.campagnes);
                populateListesFilter(data.listes);
                renderMonthHeader();
                renderGrid();

                // Sélectionner aujourd'hui, ou conserver la date courante si elle
                // appartient au mois affiché (le détail est toujours rafraîchi).
                var todayStr = data.today || formatDateYMD(new Date());
                if (!state.selectedDate) {
                    selectDay(todayStr);
                } else {
                    _clampSelectionToMonth();
                }
            })
            .catch(function (err) {
                state.isLoading = false;
                console.error('[RelancesCalendar] Erreur fetch:', err);
                if (typeof showToast === 'function') showToast('Erreur réseau calendrier', 'error');
            });
    }

    function updateKPIs(summary) {
        if (!summary) return;
        var elDue = document.getElementById('cal-kpi-due');
        var elPlanned = document.getElementById('cal-kpi-planned');
        var elSent = document.getElementById('cal-kpi-sent');
        var elActive = document.getElementById('cal-kpi-active');
        var elDueBadge = document.getElementById('calendar-kpi-badge-due');
        var elSubtabBadge = document.getElementById('badge-relances-calendar-due');

        if (elDue) elDue.textContent = summary.total_due_now || 0;
        if (elPlanned) elPlanned.textContent = summary.total_planned || 0;
        if (elSent) elSent.textContent = summary.total_sent || 0;
        if (elActive) elActive.textContent = summary.active_prospects || 0;

        var dueCount = summary.total_due_now || 0;
        if (elDueBadge) {
            if (dueCount > 0) {
                elDueBadge.textContent = dueCount + ' due' + (dueCount > 1 ? 's' : '');
                elDueBadge.style.display = 'inline-block';
            } else {
                elDueBadge.style.display = 'none';
            }
        }
        if (elSubtabBadge) {
            if (dueCount > 0) {
                elSubtabBadge.textContent = dueCount;
                elSubtabBadge.style.display = 'inline-block';
            } else {
                elSubtabBadge.style.display = 'none';
            }
        }
    }

    function populateCampagnesFilter(camps) {
        var select = document.getElementById('calendar-filter-campagne');
        if (!select || !camps) return;
        var currentVal = select.value;
        select.innerHTML = '<option value="">Toutes les campagnes</option>';
        camps.forEach(function (c) {
            var opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = c.nom;
            if (String(c.id) === String(currentVal)) opt.selected = true;
            select.appendChild(opt);
        });
    }

    function populateListesFilter(listes) {
        var select = document.getElementById('calendar-filter-liste');
        if (!select) return;
        var currentVal = state.listeFilter;
        select.innerHTML = '<option value="">Toutes les listes</option>';
        (listes || []).forEach(function (l) {
            var opt = document.createElement('option');
            opt.value = l.id;
            opt.textContent = l.nom;
            if (String(l.id) === String(currentVal)) opt.selected = true;
            select.appendChild(opt);
        });
        // Sélection devenue indisponible (filtre campagne changé) → on vide
        if (currentVal && select.value !== String(currentVal)) {
            state.listeFilter = '';
            select.value = '';
        }
    }

    function renderMonthHeader() {
        var label = document.getElementById('calendar-current-month-label');
        if (label) {
            label.textContent = MONTH_NAMES_FR[state.currentMonth] + ' ' + state.currentYear;
        }
    }

    function prevMonth() {
        state.currentMonth--;
        if (state.currentMonth < 0) {
            state.currentMonth = 11;
            state.currentYear--;
        }
        renderMonthHeader();
        renderGrid();
        _clampSelectionToMonth();
    }

    function nextMonth() {
        state.currentMonth++;
        if (state.currentMonth > 11) {
            state.currentMonth = 0;
            state.currentYear++;
        }
        renderMonthHeader();
        renderGrid();
        _clampSelectionToMonth();
    }

    function jumpToToday() {
        var now = new Date();
        state.currentYear = now.getFullYear();
        state.currentMonth = now.getMonth();
        var todayStr = formatDateYMD(now);
        renderMonthHeader();
        renderGrid();
        selectDay(todayStr);
    }

    function onCampagneChange(val) {
        state.campagneFilter = val;
        state.listeFilter = '';
        var sel = document.getElementById('calendar-filter-liste');
        if (sel) sel.value = '';
        loadData();
    }

    function onListeChange(val) {
        state.listeFilter = val;
        loadData();
    }

    function onStepChange(val) {
        state.stepFilter = val;
        renderGrid();
        if (state.selectedDate) selectDay(state.selectedDate);
    }

    function renderGrid() {
        var container = document.getElementById('calendar-days-grid');
        if (!container) return;
        container.innerHTML = '';

        var firstDay = new Date(state.currentYear, state.currentMonth, 1);
        var lastDay = new Date(state.currentYear, state.currentMonth + 1, 0);
        var numDays = lastDay.getDate();

        // 0=Dimanche, 1=Lundi ... on veut 0=Lundi, 6=Dimanche
        var startDayOfWeek = firstDay.getDay() === 0 ? 6 : firstDay.getDay() - 1;

        var daysData = (state.rawApiResponse && state.rawApiResponse.days) || {};
        var todayStr = (state.rawApiResponse && state.rawApiResponse.today) || formatDateYMD(new Date());

        // Jours du mois précédent (padding)
        var prevMonthLastDay = new Date(state.currentYear, state.currentMonth, 0).getDate();
        for (var i = startDayOfWeek - 1; i >= 0; i--) {
            var pDayNum = prevMonthLastDay - i;
            var prevDateObj = new Date(state.currentYear, state.currentMonth - 1, pDayNum);
            var pDateStr = formatDateYMD(prevDateObj);
            var cell = createDayCell(pDateStr, pDayNum, true, daysData[pDateStr], todayStr);
            container.appendChild(cell);
        }

        // Jours du mois courant
        for (var d = 1; d <= numDays; d++) {
            var curDateObj = new Date(state.currentYear, state.currentMonth, d);
            var curDateStr = formatDateYMD(curDateObj);
            var cell = createDayCell(curDateStr, d, false, daysData[curDateStr], todayStr);
            container.appendChild(cell);
        }

        // Jours du mois suivant (padding jusqu'à compléter les semaines)
        var totalCells = startDayOfWeek + numDays;
        var remainder = 7 - (totalCells % 7);
        if (remainder > 0 && remainder < 7) {
            for (var nextD = 1; nextD <= remainder; nextD++) {
                var nextDateObj = new Date(state.currentYear, state.currentMonth + 1, nextD);
                var nextDateStr = formatDateYMD(nextDateObj);
                var cell = createDayCell(nextDateStr, nextD, true, daysData[nextDateStr], todayStr);
                container.appendChild(cell);
            }
        }
    }

    function createDayCell(dateStr, dayNum, isOtherMonth, dayInfo, todayStr) {
        var cell = document.createElement('div');
        cell.className = 'cal-day-cell';
        cell.dataset.date = dateStr;

        var dObj = parseDateYMD(dateStr);
        var isWeekend = (dObj.getDay() === 0 || dObj.getDay() === 6);
        var isToday = (dateStr === todayStr);

        if (isOtherMonth) cell.classList.add('is-other');
        if (isWeekend) cell.classList.add('is-weekend');
        if (isToday) cell.classList.add('is-today');
        if (state.selectedDate === dateStr) cell.classList.add('is-selected');

        // Header du jour (Numéro + Pastille weekend)
        var header = document.createElement('div');
        header.className = 'cal-day-head';

        var numSpan = document.createElement('span');
        numSpan.className = 'cal-day-num';
        numSpan.textContent = dayNum;
        header.appendChild(numSpan);

        if (isWeekend) {
            var weTag = document.createElement('span');
            weTag.className = 'cal-day-we';
            weTag.textContent = 'WE';
            header.appendChild(weTag);
        }

        cell.appendChild(header);

        // Contenu des relances du jour
        if (dayInfo && dayInfo.batches && dayInfo.batches.length > 0) {
            var batches = dayInfo.batches;
            if (state.stepFilter) {
                batches = batches.filter(function (b) { return String(b.position) === String(state.stepFilter); });
            }

            if (batches.length > 0) {
                cell.classList.add('has-data');
                var badgeContainer = document.createElement('div');
                badgeContainer.className = 'cal-day-badges';

                var maxToShow = 2;
                batches.slice(0, maxToShow).forEach(function (b) {
                    var badge = document.createElement('div');
                    badge.className = 'cal-badge';
                    if (b.status === 'sent') badge.classList.add('is-sent');
                    else if (b.status === 'due') badge.classList.add('is-due');

                    badge.textContent = (b.liste_nom || 'L' + b.liste_id) + ' (' + b.count + ') · R' + b.position;
                    badge.title = (b.campagne_nom || '') + ' - ' + (b.liste_nom || '') + ' : ' + b.count + ' prospects (' + b.step_name + ')';
                    badgeContainer.appendChild(badge);
                });

                if (batches.length > maxToShow) {
                    var more = document.createElement('div');
                    more.className = 'cal-badge-more';
                    more.textContent = '+' + (batches.length - maxToShow) + ' autre(s)...';
                    badgeContainer.appendChild(more);
                }

                cell.appendChild(badgeContainer);
            }
        }

        cell.onclick = function () {
            selectDay(dateStr);
        };

        return cell;
    }

    function selectDay(dateStr) {
        state.selectedDate = dateStr;

        // Seule la sélection change : `.is-other` / `.is-weekend` / `.is-today`
        // restent portés par la cellule, donc le fond hors mois n'est plus perdu.
        document.querySelectorAll('.cal-day-cell').forEach(function (el) {
            el.classList.toggle('is-selected', el.dataset.date === dateStr);
        });

        renderDayDetail(dateStr);
    }

    // Après un rechargement ou un changement de mois, repositionne la sélection
    // sur le même jour du mois (borné aux jours du mois cible) : le panneau
    // détail reste surligné au lieu de pointer hors de la grille.
    function _clampSelectionToMonth() {
        if (!state.selectedDate) return;
        var d = parseDateYMD(state.selectedDate);
        if (d.getFullYear() === state.currentYear && d.getMonth() === state.currentMonth) {
            renderDayDetail(state.selectedDate); // déjà dans la grille : juste rafraîchir le détail
            return;
        }
        var lastOfTarget = new Date(state.currentYear, state.currentMonth + 1, 0).getDate();
        var dayNum = Math.min(d.getDate(), lastOfTarget);
        selectDay(formatDateYMD(new Date(state.currentYear, state.currentMonth, dayNum)));
    }

    function frDate(ymd) {
        var d = parseDateYMD(ymd);
        return d.getDate() + ' ' + MONTH_NAMES_FR[d.getMonth()].toLowerCase() + ' ' + d.getFullYear();
    }

    // Affiche l'ancre du calcul : jours ouvrés écoulés depuis la touche de départ.
    function anchorLabel(b, dateStr) {
        if (b.status === 'sent') return 'Envoyé le ' + frDate(dateStr);
        if (b.delai_jours == null || !b.last_touch_at) return '';
        var from = String(b.last_touch_at).slice(0, 10);
        var quoi = b.position === 1
            ? "l'envoi initial du "
            : 'la Relance ' + (b.position - 1) + ' du ';
        return 'J+' + b.delai_jours + ' jours ouvrés depuis ' + quoi + frDate(from) + ' → ' + frDate(dateStr);
    }

    function renderDayDetail(dateStr) {
        var titleEl = document.getElementById('cal-detail-date-title');
        var subEl = document.getElementById('cal-detail-date-sub');
        var badgeTotal = document.getElementById('cal-detail-total-badge');
        var listContainer = document.getElementById('cal-detail-batches-list');

        if (!titleEl || !listContainer) return;

        var dObj = parseDateYMD(dateStr);
        var dayName = DAY_NAMES_FR[dObj.getDay()];
        var formattedFr = dayName + ' ' + dObj.getDate() + ' ' + MONTH_NAMES_FR[dObj.getMonth()] + ' ' + dObj.getFullYear();
        var isWeekend = (dObj.getDay() === 0 || dObj.getDay() === 6);

        titleEl.textContent = formattedFr;

        var daysData = (state.rawApiResponse && state.rawApiResponse.days) || {};
        var dayInfo = daysData[dateStr];

        if (isWeekend) {
            subEl.textContent = '⛔ Week-end : Jour de repos ouvré (aucun envoi)';
        } else {
            subEl.textContent = 'Jour ouvré';
        }

        listContainer.innerHTML = '';

        if (!dayInfo || !dayInfo.batches || dayInfo.batches.length === 0) {
            badgeTotal.style.display = 'none';
            listContainer.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--ink3);font-size:13px">Aucune relance prévue ou effectuée pour ce jour.</div>';
            return;
        }

        var batches = dayInfo.batches;
        if (state.stepFilter) {
            batches = batches.filter(function (b) { return String(b.position) === String(state.stepFilter); });
        }

        var totalCount = batches.reduce(function (acc, b) { return acc + b.count; }, 0);
        badgeTotal.textContent = totalCount + ' relance' + (totalCount > 1 ? 's' : '');
        badgeTotal.style.display = 'inline-block';

        batches.forEach(function (b) {
            var card = document.createElement('div');
            card.style.background = 'var(--surface2)';
            card.style.border = '1px solid var(--border)';
            card.style.borderRadius = '8px';
            card.style.padding = '12px';
            card.style.display = 'flex';
            card.style.flexDirection = 'column';
            card.style.gap = '8px';

            var topRow = document.createElement('div');
            topRow.style.display = 'flex';
            topRow.style.justifyContent = 'space-between';
            topRow.style.alignItems = 'flex-start';

            var nameCol = document.createElement('div');
            var title = document.createElement('div');
            title.style.fontWeight = '700';
            title.style.fontSize = '13px';
            title.style.color = 'var(--ink)';
            title.textContent = b.liste_nom || 'Liste #' + b.liste_id;

            var campName = document.createElement('div');
            campName.style.fontSize = '11px';
            campName.style.color = 'var(--ink3)';
            campName.textContent = 'Campagne : ' + (b.campagne_nom || 'Générale');

            nameCol.appendChild(title);
            nameCol.appendChild(campName);

            var statusBadge = document.createElement('span');
            statusBadge.style.fontSize = '10px';
            statusBadge.style.fontWeight = '700';
            statusBadge.style.padding = '2px 8px';
            statusBadge.style.borderRadius = '10px';

            if (b.status === 'sent') {
                statusBadge.style.background = 'rgba(16,185,129,0.15)';
                statusBadge.style.color = '#10b981';
                statusBadge.textContent = '✓ Envoyé (' + b.count + ')';
            } else if (b.status === 'due') {
                statusBadge.style.background = 'rgba(245,158,11,0.2)';
                statusBadge.style.color = '#f59e0b';
                statusBadge.textContent = '⏳ Dû (' + b.count + ')';
            } else {
                statusBadge.style.background = 'rgba(59,130,246,0.15)';
                statusBadge.style.color = '#3b82f6';
                statusBadge.textContent = '📅 Planifié (' + b.count + ')';
            }

            topRow.appendChild(nameCol);
            topRow.appendChild(statusBadge);
            card.appendChild(topRow);

            var stepInfo = document.createElement('div');
            stepInfo.style.fontSize = '12px';
            stepInfo.style.color = 'var(--ink2)';
            stepInfo.textContent = 'Étape : ' + b.step_name;
            card.appendChild(stepInfo);

            // Ancre du calcul : jours ouvrés écoulés depuis la touche de départ.
            var anchorInfo = document.createElement('div');
            anchorInfo.style.fontSize = '11px';
            anchorInfo.style.color = 'var(--ink3)';
            anchorInfo.textContent = anchorLabel(b, dateStr);
            card.appendChild(anchorInfo);

            // Boutons d'action
            var btnRow = document.createElement('div');
            btnRow.style.display = 'flex';
            btnRow.style.gap = '6px';
            btnRow.style.flexWrap = 'wrap';
            btnRow.style.marginTop = '4px';

            var btnView = document.createElement('button');
            btnView.className = 'btn sm';
            btnView.style.fontSize = '11px';
            btnView.style.padding = '3px 8px';
            btnView.textContent = '👥 Voir les prospects (' + b.count + ')';
            btnView.onclick = function () {
                openBatchProspectsModal(b);
            };
            btnRow.appendChild(btnView);

            // Action validation Telegram si le lot est dû
            if (b.status === 'due') {
                var btnTg = document.createElement('button');
                btnTg.className = 'btn primary sm';
                btnTg.style.fontSize = '11px';
                btnTg.style.padding = '3px 8px';
                btnTg.style.background = '#f59e0b';
                btnTg.style.color = '#000';
                btnTg.textContent = '📲 Déclencher Telegram';
                btnTg.onclick = function () {
                    triggerTelegramValidation(b.campagne_id, b.liste_id, b.liste_nom);
                };
                btnRow.appendChild(btnTg);
            }

            card.appendChild(btnRow);
            listContainer.appendChild(card);
        });
    }

    var currentModalProspects = [];

    function openBatchProspectsModal(batch) {
        var modal = document.getElementById('modal-cal-batch-prospects');
        var titleEl = document.getElementById('modal-cal-batch-title');
        var subEl = document.getElementById('modal-cal-batch-sub');
        var searchInput = document.getElementById('modal-cal-prospects-search');

        if (!modal) return;

        titleEl.textContent = (batch.liste_nom || 'Liste #' + batch.liste_id) + ' — ' + batch.step_name;
        subEl.textContent = (batch.campagne_nom || '') + ' · ' + batch.count + ' prospects concernés';

        currentModalProspects = batch.prospects || [];
        if (searchInput) searchInput.value = '';

        renderModalProspectsTable(currentModalProspects);

        modal.classList.add('active');
        modal.style.display = 'flex';
        modal.style.opacity = '1';
    }

    function renderModalProspectsTable(prospects) {
        var tbody = document.getElementById('modal-cal-batch-tbody');
        if (!tbody) return;

        tbody.innerHTML = '';
        if (!prospects || prospects.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;padding:1.5rem;color:var(--ink3)">Aucun prospect trouvé</td></tr>';
            return;
        }

        prospects.forEach(function (p) {
            var tr = document.createElement('tr');
            tr.innerHTML = '<td style="font-weight:600;padding:8px 12px">' + (p.nom || p.prenom || '—') + '</td>' +
                           '<td style="padding:8px 12px">' + (p.entreprise || '—') + '</td>' +
                           '<td style="padding:8px 12px"><code style="font-size:12px;color:var(--ink2)">' + (p.email || '—') + '</code></td>';
            tbody.appendChild(tr);
        });
    }

    function filterModalProspects(query) {
        var q = (query || '').toLowerCase().trim();
        if (!q) {
            renderModalProspectsTable(currentModalProspects);
            return;
        }
        var filtered = currentModalProspects.filter(function (p) {
            return (p.nom && p.nom.toLowerCase().indexOf(q) !== -1) ||
                   (p.prenom && p.prenom.toLowerCase().indexOf(q) !== -1) ||
                   (p.entreprise && p.entreprise.toLowerCase().indexOf(q) !== -1) ||
                   (p.email && p.email.toLowerCase().indexOf(q) !== -1);
        });
        renderModalProspectsTable(filtered);
    }

    function closeModal() {
        var modal = document.getElementById('modal-cal-batch-prospects');
        if (modal) {
            modal.classList.remove('active');
            modal.style.display = 'none';
            modal.style.opacity = '0';
        }
    }

    function triggerTelegramValidation(campagneId, listeId, listeNom) {
        if (!confirm('Voulez-vous envoyer une demande de validation Telegram immédiate pour "' + listeNom + '" ?')) {
            return;
        }

        fetch('/api/v2/relances/batch-validate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ campagne_id: campagneId, liste_id: listeId })
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.success) {
                if (typeof showToast === 'function') showToast('Demande Telegram envoyée pour ' + listeNom + ' !', 'success');
                loadData();
            } else {
                if (typeof showToast === 'function') showToast('Erreur : ' + (data.error || 'échec'), 'error');
            }
        })
        .catch(function (err) {
            console.error('[triggerTelegramValidation]', err);
            if (typeof showToast === 'function') showToast('Erreur de communication', 'error');
        });
    }

    // Écouter la touche Échap pour fermer la modale
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' || e.keyCode === 27) {
            closeModal();
        }
    });

    return {
        init: init,
        refresh: loadData,
        prevMonth: prevMonth,
        nextMonth: nextMonth,
        jumpToToday: jumpToToday,
        onCampagneChange: onCampagneChange,
        onListeChange: onListeChange,
        onStepChange: onStepChange,
        selectDay: selectDay,
        openBatchProspectsModal: openBatchProspectsModal,
        closeModal: closeModal,
        filterModalProspects: filterModalProspects
    };
})();
