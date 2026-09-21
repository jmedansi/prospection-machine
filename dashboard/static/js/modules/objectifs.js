/**
 * dashboard/static/js/modules/objectifs.js
 * SHIM DE COMPATIBILITÉ — le modèle v2 « objectif » a été remplacé par
 * « Campagne → Liste → Prospect ». Le vrai module vit dans campagnes.js.
 *
 * Ce fichier ne fait qu'exposer l'ancien nom de module (ObjectifsModule) vers
 * CampagnesModule pour ne pas casser les templates legacy, l'interface V5
 * (dashboard_v5.html, /legacy) et les appels inline pendant la bascule (#5c).
 * Si campagnes.js n'a pas été chargé par la page, il est injecté à la volée.
 */
(function () {
    'use strict';
    function alias() {
        if (window.CampagnesModule) window.ObjectifsModule = window.CampagnesModule;
    }
    if (window.CampagnesModule) { alias(); return; }
    var s = document.createElement('script');
    s.src = '/static/js/modules/campagnes.js';
    s.onload = alias;
    document.head.appendChild(s);
})();