# -*- coding: utf-8 -*-
"""
envoi/email_shell.py — mise en forme HTML des emails v2 au moment de l'envoi.

Transforme un corps texte brut (template rendu + humanisation IA) en un email
HTML propre et minimal : paragraphes, liens cliquables, typographie lisible.

Règles :
  - Un corps déjà HTML complet (<!DOCTYPE / <html>) est renvoyé tel quel.
  - Le texte est échappé (html.escape) puis découpé en <p> sur les doubles
    retours ligne. `white-space: pre-wrap` préserve les retours ligne simples,
    les espaces répétés et l'indentation (ni <br> ni collapse HTML).
  - Les URLs http(s) sont transformées en liens cliquables.
  - Aucune logique d'envoi ni de rédaction : uniquement de la présentation.
"""
import html
import re

_URL_RE = re.compile(r"(https?://[^\s<>]+)")

_SHELL = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{objet}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.7; color: #1a1a1a; margin: 0; padding: 24px 12px; background-color: #f5f6f7; }}
        .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; padding: 36px 40px; border-radius: 8px; white-space: pre-wrap; }}
        p {{ margin: 0 0 16px 0; font-size: 16px; }}
        a {{ color: #065f46; }}
        .signature {{ margin-top: 28px; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #374151; }}
        .signature p {{ margin-bottom: 4px; }}
    </style>
</head>
<body>
    <div class="container">{corps}</div>
</body>
</html>
"""

_ESCAPED_URL_RE = re.compile(r"(https?://[^\s<>]+)")


def _is_full_html(text: str) -> bool:
    t = (text or "").strip()
    return t.lstrip().lower().startswith("<!doctype") or "<html" in t.lower()


def _linkify(escaped: str) -> str:
    """Transforme les URLs du texte déjà échappé en liens cliquables.

    La ponctuation de clôture (.,;:!?<>) n'est PAS incluse dans l'URL du lien.
    """

    def _repl(m):
        url = m.group(1).rstrip(".,;:!?<>()[]{}")
        return f'<a href="{url}">{url}</a>'

    return _ESCAPED_URL_RE.sub(_repl, escaped)


def _paragraphs(text: str) -> str:
    """Découpe le texte brut en <p> en PRÉSERVANT les espaces et l'indentation.

    Le container porte `white-space: pre-wrap` : un `\n` seul affiche un retour
    ligne, les espaces répétés et l'indentation sont conservés (plus de `<br>`).
    Seuls le premier caractère non-blanc de la 1re ligne et le dernier espace de
    la dernière ligne de chaque bloc sont nettoyés.
    """
    blocks = re.split(r"\n{2,}", text)
    out = []
    for block in blocks:
        lines = block.split("\n")
        if lines:
            lines[0] = lines[0].lstrip()
            lines[-1] = lines[-1].rstrip()
        block = "\n".join(lines)
        if not block.strip():
            continue
        inline = _linkify(block)
        out.append(f"<p>{inline}</p>")
    # Signature discrète : pas de marqueur dédié, on isole simplement le
    # dernier bloc court de clôture s'il commence par "Bien à vous" / "Cordialement".
    if out and re.match(r"<p>(Bien (à|a) vous|Cordialement|Bonne journée)", out[-1], re.I):
        last = out.pop()
        out.append('<div class="signature">' + last + "</div>")
    return "\n".join(out)


def build_html_email(objet: str, corps: str) -> str:
    """Retourne le corps mis en forme en HTML (ou tel quel s'il est déjà HTML)."""
    corps = corps or ""
    if _is_full_html(corps):
        return corps
    body = _paragraphs(html.escape(corps))
    return _SHELL.format(objet=html.escape(objet or ""), corps=body)