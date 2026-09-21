# -*- coding: utf-8 -*-
"""
envoi/track_links.py — tracking maison (backend SMTP) : pixel d'ouverture + wrapper de clic.

Appliqué au moment de l'envoi quand TRACKING_BASE_URL est défini. Les liens http(s)
du HTML sont réécrits vers un endpoint du dashboard qui enregistre le clic puis
redirige ; un pixel 1x1 transparent est inséré en fin de corps pour le suivi
d'ouverture. Le token est le Message-ID RFC de la touche.

Resend fait son propre rewriting (track_opens/track_clicks, voir resend_sender.py) —
ce module ne s'applique qu'au backend SMTP (maison).

TODO serveurs de reporting : les endpoints vivent dans dashboard/routes/webhooks.py
(section « tracking maison »).
"""
import html as _html
import os
import re

from urllib.parse import quote

_URL_RE = re.compile(r'href="(https?://[^"]+)"')

_PIXEL_IMG = (
    '<img src="{base}/api/webhooks/track/pixel/{mid}" width="1" '
    'height="1" alt="" style="display:none;width:1px;height:1px;border:0">'
)


def tracking_enabled() -> bool:
    """True si TRACKING_BASE_URL est configurée (tracking maison actif)."""
    return bool(os.getenv('TRACKING_BASE_URL', '').strip())


def get_base_url() -> str:
    return os.getenv('TRACKING_BASE_URL', '').strip().rstrip('/')


def rewrite_links(html: str, base_url: str, message_id: str) -> str:
    """Réécrit chaque <a href="http(s)://..."> vers le tracker de clic."""

    def _repl(m):
        url = m.group(1)
        u = quote(url, safe='')
        return f'href="{base_url}/api/webhooks/track/click/{quote(message_id, safe="")}?u={u}"'

    return _URL_RE.sub(_repl, html)


def inject_pixel(html: str, base_url: str, message_id: str) -> str:
    pixel = _PIXEL_IMG.format(base=base_url, mid=_html.escape(message_id, quote=True))
    if '</body>' in html.lower():
        return html.replace('</body>', pixel + '</body>', 1)
    return html + pixel


def apply_tracking(html: str, message_id: str) -> str:
    """Applique le tracking maison (liens + pixel) si configuré. Idempotent."""
    if not message_id:
        return html
    base_url = get_base_url()
    if not base_url:
        return html
    if f'/api/webhooks/track/pixel/{_html.escape(message_id, quote=True)}' in html:
        return html
    html = rewrite_links(html, base_url, message_id)
    return inject_pixel(html, base_url, message_id)