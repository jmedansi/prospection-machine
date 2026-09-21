# -*- coding: utf-8 -*-
"""
Tests — envoi/email_shell.py : mise en forme HTML du corps v2.

Aucun réseau, aucun LLM : unittest pur sur la transformation texte → HTML.
"""
import pytest

from envoi.email_shell import build_html_email


def test_texte_brut_est_enveloppe_en_html():
    html = build_html_email("Un mot sur votre site", "Bonjour,\n\nVoici une ébauche.\n\nBien à vous,\nJean-Marc")
    assert html.startswith("<!DOCTYPE html>")
    assert "<title>Un mot sur votre site</title>" in html
    assert "<p>Bonjour,</p>" in html
    assert "<p>Voici une ébauche.</p>" in html
    # le retour ligne simple est préservé (rendu garanti par white-space: pre-wrap)
    assert "<p>Bien à vous,\nJean-Marc</p>" in html
    assert "white-space: pre-wrap" in html


def test_signature_isolee_dans_un_bloc():
    html = build_html_email("O", "Bonjour,\n\nMerci de votre retour.\n\nBien à vous,\nJean-Marc")
    assert '<div class="signature">' in html
    assert "<p>Bien à vous,\nJean-Marc</p>" in html


def test_espaces_et_indentation_preserves():
    html = build_html_email("O", "Points clés :\n   1. Point A\n   2. Point B\n\nEspaces  multiples  conservés.")
    assert "   1. Point A" in html
    assert "   2. Point B" in html
    assert "Espaces  multiples  conservés." in html


def test_urls_transformees_en_liens():
    html = build_html_email("O", "Rendez-vous sur https://dupont.fr/maquette pour voir l'ébauche.")
    assert '<a href="https://dupont.fr/maquette">https://dupont.fr/maquette</a>' in html


def test_texte_echappe_pas_dejection_html():
    html = build_html_email("O", "Essai <b>pas gras</b> & « guillemets ».")
    assert "<b>pas gras</b>" not in html
    assert "&lt;b&gt;pas gras&lt;/b&gt;" in html
    assert "&amp;" in html
    assert "« guillemets »" in html


def test_html_deja_complet_renvoye_tel_quel():
    existing = '<!DOCTYPE html><html><body><p>Déjà prêt</p></body></html>'
    assert build_html_email("O", existing) == existing

    partiel = "<html><body><p>mise en forme</p></body></html>"
    assert build_html_email("O", partiel) == partiel


def test_corps_vide_retourne_coquille_vide():
    html = build_html_email("O", "")
    assert "<p>" not in html
    assert 'class="container"' in html


def test_accent_enrichi_sans_double_encodage():
    html = build_html_email("O", "Été & café")
    assert "Été &amp; café" in html