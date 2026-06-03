#!/usr/bin/env node
/**
 * wappalyzer_check.js — Wrapper CLI pour le package npm Wappalyzer
 *
 * Usage :
 *   node wappalyzer_check.js <url>
 *
 * Sortie (stdout) : JSON
 *   {
 *     "cms": "WordPress",           // CMS détecté, null si aucun
 *     "cdn": "Cloudflare",          // CDN/WAF détecté, null si aucun
 *     "ecommerce": "WooCommerce",   // Plateforme e-commerce, null si aucun
 *     "server": "Apache",           // Serveur web, null si aucun
 *     "technologies": [...],        // Liste brute des techs détectées
 *     "error": null                 // Message d'erreur si échec
 *   }
 */

const url = process.argv[2];
if (!url) {
    console.log(JSON.stringify({ error: "URL manquante" }));
    process.exit(1);
}

// ─── Mapping catégories Wappalyzer → clés normalisées ────────────────────────

const CMS_NAMES = new Set([
    "WordPress", "PrestaShop", "Joomla", "Drupal", "TYPO3",
    "Magento", "Shopify", "OpenCart", "WooCommerce",
    "Wix", "Squarespace", "Weebly", "Jimdo", "Webflow",
    "Blogger", "Ghost", "Kirby", "Craft CMS",
]);

const CDN_NAMES = new Set([
    "Cloudflare", "Cloudflare Bot Management", "Cloudflare Browser Insights",
    "Sucuri", "Akamai", "Fastly", "Imperva", "Incapsula",
    "MaxCDN", "KeyCDN", "BunnyCDN", "AWS CloudFront",
    "jsDelivr", "unpkg",
]);

const ECOMMERCE_NAMES = new Set([
    "WooCommerce", "PrestaShop", "Magento", "Shopify", "OpenCart",
    "BigCommerce", "CS-Cart", "osCommerce", "VirtueMart",
]);

// ─── Analyse des résultats ────────────────────────────────────────────────────

function normalize(technologies) {
    let cms = null;
    let cdn = null;
    let ecommerce = null;
    let server = null;

    for (const tech of technologies) {
        const name = tech.name;
        const cats = (tech.categories || []).map(c => (typeof c === 'string' ? c : c.name || ''));

        // CMS
        if (!cms && (CMS_NAMES.has(name) || cats.some(c => c.toLowerCase().includes('cms')))) {
            cms = name;
        }
        // CDN / WAF
        if (!cdn && (CDN_NAMES.has(name) || cats.some(c =>
            c.toLowerCase().includes('cdn') || c.toLowerCase().includes('security') || c.toLowerCase().includes('waf')
        ))) {
            cdn = name;
        }
        // Ecommerce
        if (!ecommerce && (ECOMMERCE_NAMES.has(name) || cats.some(c => c.toLowerCase().includes('ecommerce')))) {
            ecommerce = name;
        }
        // Web server
        if (!server && cats.some(c => c.toLowerCase().includes('web server'))) {
            server = name;
        }
    }

    return { cms, cdn, ecommerce, server };
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
    try {
        // Tenter import package wappalyzer (npm install -g wappalyzer)
        let Wappalyzer;
        try {
            Wappalyzer = require('wappalyzer');
        } catch (e) {
            // Fallback : essayer le chemin local node_modules
            Wappalyzer = require('./node_modules/wappalyzer');
        }

        const wappalyzer = new Wappalyzer({ debug: false, delay: 500, maxWait: 15000 });
        await wappalyzer.init();

        const site = await wappalyzer.open(url, {}, { delay: 1000 });
        const results = await site.analyze();
        await wappalyzer.destroy();

        const technologies = (results.technologies || []).map(t => ({
            name: t.name,
            categories: (t.categories || []).map(c => typeof c === 'string' ? c : c.name),
        }));

        const normalized = normalize(technologies);

        console.log(JSON.stringify({
            ...normalized,
            technologies: technologies.map(t => t.name),
            error: null,
        }));

    } catch (err) {
        console.log(JSON.stringify({
            cms: null, cdn: null, ecommerce: null, server: null,
            technologies: [],
            error: err.message || String(err),
        }));
    }
}

main();
