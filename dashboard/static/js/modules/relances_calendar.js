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
                btnTg.className = 'btn sm';
                btnTg.style.fontSize = '11px';
                btnTg.style.padding = '3px 8px';
                btnTg.style.background = '#f59e0b';
                btnTg.style.color = '#000';
                btnTg.textContent = '📲 Telegram';
                btnTg.title = "Demander l'approbation sur Telegram";
                btnTg.onclick = function () {
                    triggerTelegramValidation(b.campagne_id, b.liste_id, b.liste_nom);
                };
                btnRow.appendChild(btnTg);

                var btnSendDirect = document.createElement('button');
                btnSendDirect.className = 'btn primary sm';
                btnSendDirect.style.fontSize = '11px';
                btnSendDirect.style.padding = '3px 8px';
                btnSendDirect.style.background = '#10b981';
                btnSendDirect.style.color = '#fff';
                btnSendDirect.textContent = '🚀 Envoyer (' + b.count + ')';
                btnSendDirect.title = "Envoyer directement sans attendre Telegram";
                btnSendDirect.onclick = function () {
                    triggerDirectSend(b.campagne_id, b.liste_id, b.liste_nom, b.count);
                };
                btnRow.appendChild(btnSendDirect);

                var btnReset = document.createElement('button');
                btnReset.className = 'btn sm';
                btnReset.style.fontSize = '11px';
                btnReset.style.padding = '3px 8px';
                btnReset.style.border = '1px solid var(--border)';
                btnReset.textContent = '🔄 Débloquer';
                btnReset.title = "Réinitialiser le verrou de ce lot";
                btnReset.onclick = function () {
                    triggerResetLock(b.campagne_id, b.liste_id, b.liste_nom);
                };
                btnRow.appendChild(btnReset);
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

    async function triggerTelegramValidation(campagneId, listeId, listeNom) {
        // Vrai popup (et non window.confirm natif) — même helper que le reste de la V6.
        var confirmFn = (window.UI && window.UI.confirm) || window.showConfirm;
        var ok = await confirmFn(
            'Envoyer une demande de validation Telegram pour « ' + listeNom + ' » ?\n\n' +
            'Rappel : l\'envoi n\'a lieu qu\'avec ton ✅, et seulement entre 9 h et 18 h ' +
            '(jours ouvrés).',
            { title: '📲 Validation Telegram', confirmText: 'Envoyer la demande' }
        );
        if (!ok) return;

        fetch('/api/v2/relances/batch-validate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ campagne_id: campagneId, liste_id: listeId })
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            var toast = (typeof showToast === 'function') ? showToast : function () {};
            if (data.success && data.envoyee) {
                toast('📲 Demande Telegram envoyée pour ' + listeNom, 'success');
                loadData();
            } else if (data.success) {
                // Aucune notification partie : réponse déjà dans le hub.
                toast('ℹ️ ' + listeNom + ' — ' + (data.message || 'rien à demander'), 'info');
                loadData();
            } else {
                toast('⚠️ ' + (data.error || 'échec'), 'error');
            }
        })
        .catch(function (err) {
            console.error('[triggerTelegramValidation]', err);
            if (typeof showToast === 'function') showToast('Erreur de communication', 'error');
        });
    }

    async function triggerDirectSend(campagneId, listeId, listeNom, count) {
        var confirmFn = (window.UI && window.UI.confirm) || window.showConfirm;
        var ok = await confirmFn(
            'Confirmer l\'envoi DIRECT et immédiat de ' + count + ' relance(s) pour « ' + listeNom + ' » ?\n\n' +
            'Cette action contourne Telegram et déclenche l\'envoi sécurisé des emails directement depuis le cockpit.',
            { title: '🚀 Envoi direct de relances', confirmText: 'Envoyer maintenant' }
        );
        if (!ok) return;

        var toast = (typeof showToast === 'function') ? showToast : function () {};

        // Afficher un bandeau de progression autonome immédiatement
        _showCalBatchProgress(listeNom, 0, count);

        fetch('/api/v2/relances/batch-send-direct', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ campagne_id: campagneId, liste_id: listeId })
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.success && data.job_id) {
                toast('🚀 Envoi lancé : ' + (data.total || count) + ' relance(s) — Suivi en temps réel', 'info');

                // 1. Si ListesModule est accessible, utiliser son panneau de progression natif
                if (window.ListesModule && typeof window.ListesModule._startProgressTracking === 'function') {
                    window.ListesModule._startProgressTracking(listeId, data.job_id, data.total || count);
                    // Naviguer vers l'onglet Listes pour voir la barre
                    var tabListes = document.querySelector('[data-tab="listes"], [data-section="listes"], #tab-listes');
                    if (tabListes && typeof tabListes.click === 'function') tabListes.click();
                }

                // 2. Polling local pour mettre à jour le bandeau calendrier + rafraîchir à la fin
                _pollCalBatchProgress(listeId, data.job_id, data.total || count, listeNom);

            } else if (!data.success) {
                _hideCalBatchProgress();
                toast('⚠️ ' + (data.error || 'Erreur lors de l\'envoi'), 'error');
            } else {
                _hideCalBatchProgress();
                toast('ℹ️ ' + (data.message || 'Aucune relance à envoyer'), 'info');
            }
        })
        .catch(function (err) {
            _hideCalBatchProgress();
            console.error('[triggerDirectSend]', err);
            toast('Erreur de communication', 'error');
        });
    }

    // ── Bandeau de progression autonome dans le calendrier ──────────────────
    var _calBatchPollTimer = null;

    function _showCalBatchProgress(listeNom, current, total) {
        var existing = document.getElementById('cal-batch-progress-banner');
        if (!existing) {
            existing = document.createElement('div');
            existing.id = 'cal-batch-progress-banner';
            existing.style.cssText = [
                'position:fixed', 'bottom:24px', 'right:24px', 'z-index:9999',
                'background:var(--surface2,#1e293b)', 'border:1px solid var(--border,#334155)',
                'border-radius:12px', 'padding:16px 20px', 'min-width:320px', 'max-width:420px',
                'box-shadow:0 8px 32px rgba(0,0,0,.4)', 'color:var(--ink,#e2e8f0)',
                'font-family:inherit', 'font-size:13px', 'transition:opacity .3s'
            ].join(';');
            existing.innerHTML = [
                '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">',
                '  <span style="font-size:20px">📤</span>',
                '  <div style="flex:1">',
                '    <div id="cal-bp-title" style="font-weight:700;color:var(--accent,#38bdf8)"></div>',
                '    <div id="cal-bp-sub" style="font-size:11px;color:var(--ink3,#94a3b8);margin-top:2px"></div>',
                '  </div>',
                '</div>',
                '<div style="background:var(--surface3,#0f172a);border-radius:6px;overflow:hidden;height:6px;margin-bottom:8px">',
                '  <div id="cal-bp-fill" style="height:100%;background:linear-gradient(90deg,#38bdf8,#818cf8);width:0%;transition:width .4s;border-radius:6px"></div>',
                '</div>',
                '<div id="cal-bp-lead" style="font-size:11px;color:var(--ink2,#cbd5e1);min-height:16px"></div>',
            ].join('');
            document.body.appendChild(existing);
        }
        var title = document.getElementById('cal-bp-title');
        var sub   = document.getElementById('cal-bp-sub');
        var fill  = document.getElementById('cal-bp-fill');
        var lead  = document.getElementById('cal-bp-lead');
        if (title) title.textContent = 'Envoi en cours — ' + listeNom;
        if (sub)   sub.textContent   = '0 / ' + total + ' relances';
        if (fill)  fill.style.width  = '0%';
        if (lead)  lead.textContent  = 'Démarrage…';
        existing.style.opacity = '1';
        existing.style.display = 'block';
    }

    function _hideCalBatchProgress() {
        if (_calBatchPollTimer) { clearInterval(_calBatchPollTimer); _calBatchPollTimer = null; }
        var el = document.getElementById('cal-batch-progress-banner');
        if (el) {
            el.style.opacity = '0';
            setTimeout(function () { if (el) el.remove(); }, 400);
        }
    }

    function _updateCalBatchProgress(job) {
        if (!job) return;
        var fill  = document.getElementById('cal-bp-fill');
        var sub   = document.getElementById('cal-bp-sub');
        var lead  = document.getElementById('cal-bp-lead');
        var title = document.getElementById('cal-bp-title');
        var pct = job.percentage || 0;
        if (fill) fill.style.width = pct + '%';
        if (sub)  sub.textContent = (job.current || 0) + ' / ' + (job.total || 0) + ' relances — ' + (job.sent || 0) + ' envoyées';
        if (job.current_lead && lead) {
            var l = job.current_lead;
            lead.textContent = (l.success ? '✅' : '⚠️') + ' ' + (l.nom || 'Prospect') + ' <' + (l.email || '') + '>';
        }
        if (!job.running) {
            var toast = (typeof showToast === 'function') ? showToast : function () {};
            if (job.status === 'termine') {
                if (title) title.textContent = '✅ Envoi terminé';
                if (lead) lead.textContent = 'Bilan : ' + (job.sent || 0) + ' envoyé(s), ' + (job.failed || 0) + ' erreur(s)';
                toast('✅ Envoi terminé : ' + (job.sent || 0) + ' relance(s) envoyée(s)', 'success');
            } else if (job.status === 'annule') {
                if (title) title.textContent = '⏹️ Envoi interrompu';
                toast('Envoi interrompu', 'warning');
            } else {
                if (title) title.textContent = '❌ Erreur d\'envoi';
                toast(job.error || 'Erreur lors de l\'envoi des relances', 'error');
            }
            setTimeout(_hideCalBatchProgress, 8000);
            loadData(); // Rafraîchir le calendrier
        }
    }

    function _pollCalBatchProgress(listeId, jobId, total, listeNom) {
        // Écoute Socket.IO si disponible (mise à jour instantanée)
        var sock = window.socket || (typeof io !== 'undefined' ? window.socketio : null);
        if (sock && typeof sock.on === 'function') {
            sock.on('list_send_progress', function (payload) {
                if (payload && payload.liste_id === listeId) {
                    _updateCalBatchProgress(Object.assign({ running: true }, payload,
                        { current_lead: payload.lead || null }));
                }
            });
            sock.on('list_send_done', function (payload) {
                if (payload && payload.liste_id === listeId) {
                    _updateCalBatchProgress({ running: false, status: payload.status,
                        sent: payload.sent, failed: payload.failed, total: payload.total,
                        current: payload.total, percentage: 100 });
                }
            });
        }

        // Polling de secours toutes les 1,5 s
        if (_calBatchPollTimer) clearInterval(_calBatchPollTimer);
        _calBatchPollTimer = setInterval(function () {
            fetch('/api/v2/listes/' + listeId + '/send/status')
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.job) _updateCalBatchProgress(data.job);
                    if (!data.running) {
                        clearInterval(_calBatchPollTimer);
                        _calBatchPollTimer = null;
                    }
                })
                .catch(function () {});
        }, 1500);
    }

    async function triggerResetLock(campagneId, listeId, listeNom) {
        var confirmFn = (window.UI && window.UI.confirm) || window.showConfirm;
        var ok = await confirmFn(
            'Réinitialiser le verrou de « ' + listeNom + ' » ?\n\n' +
            'Cela débloquera le lot si une notification Telegram était restée figée ou en attente.',
            { title: '🔄 Débloquer le lot', confirmText: 'Débloquer' }
        );
        if (!ok) return;

        fetch('/api/v2/relances/batch-reset-lock', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ campagne_id: campagneId, liste_id: listeId })
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            var toast = (typeof showToast === 'function') ? showToast : function () {};
            if (data.success) {
                toast('✅ Verrou réinitialisé pour ' + listeNom, 'success');
                loadData();
            } else {
                toast('⚠️ ' + (data.error || 'Échec'), 'error');
            }
        })
        .catch(function (err) {
            console.error('[triggerResetLock]', err);
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
