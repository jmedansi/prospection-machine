import re

from copywriter.main import generate_email_content
from dashboard.pipeline.email_generation import SITUATION_TO_PROFILE
from envoi.email_builder import build_premium_email


def make_audit_for_label(label: str) -> dict:
    base = {
        'nom': 'Test Entreprise',
        'site_web': 'https://example.com',
        'ville': 'Paris',
        'category': 'Restaurant',
        'mobile_score': 85,
        'desktop_score': 95,
        'lcp_ms': 1800,
        'fcp_ms': 900,
        'cls': 0.05,
        'has_https': True,
        'has_meta_description': True,
        'h1_count': 1,
        'render_blocking_scripts': 0,
        'uses_cache': True,
        'tel_link': True,
        'has_contact_button': True,
        'images_without_alt': 0,
        'has_analytics': True,
        'cms_detected': 'WordPress',
        'rating': 4.6,
        'reviews_count': 120,
    }

    if label == 'Pas de site web':
        base.update({'site_web': '', 'has_meta_description': False, 'cms_detected': '', 'rating': 0, 'reviews_count': 0})
    elif label == 'Site lent sur mobile':
        base.update({'lcp_ms': 4200, 'mobile_score': 45, 'rating': 4.0, 'reviews_count': 25})
    elif label == 'Bon GMB, mauvais site':
        base.update({'lcp_ms': 4200, 'mobile_score': 45, 'rating': 4.5, 'reviews_count': 70})
    elif label == 'Pas de meta description':
        base.update({'has_meta_description': False, 'rating': 4.4, 'reviews_count': 55})
    elif label == "Peu d'avis Google":
        base.update({'rating': 4.3, 'reviews_count': 8})
    elif label == 'Note Google faible':
        base.update({'rating': 3.6, 'reviews_count': 55})
    elif label == 'Pas de bouton contact / tel':
        base.update({'has_contact_button': False, 'tel_link': False})
    elif label == 'CMS vieillot (Wix/Jimdo)':
        base.update({'cms_detected': 'Wix'})
    return base


def test_situation_to_profile_and_template_mapping():
    expected_title_snippets = {
        'A': "voici une ébauche gratuite de votre site web",
        'B': 'Votre site web est lent',
        'C': 'vos concurrents sont loin devant',
        'D': 'est invisible sur Google',
    }

    main_problem = {'service_propose': 'test', 'probleme_principal': 'test'}

    for phrase, profile in SITUATION_TO_PROFILE.items():
        audit_dict = make_audit_for_label(phrase)
        copy_result = generate_email_content(audit_dict, main_problem)

        assert copy_result['phrase_synthese'] == phrase, f"Mauvaise situation détectée pour {phrase}"

        builder_data = {
            **audit_dict,
            'profile': profile,
            'template_variant': 'v1',
            'lien_rapport': 'https://audit.incidenx.com/test-slug/',
        }
        html = build_premium_email(builder_data, verify_link=False)

        assert html is not None, f"Aucun HTML généré pour le profil {profile} ({phrase})"
        assert expected_title_snippets[profile] in html, (
            f"Le template utilisé pour le profil {profile} ne correspond pas au HTML généré pour {phrase}"
        )

        title_match = re.search(r'<title>([^<]+)</title>', html)
        assert title_match, f"Aucun <title> trouvé dans le HTML pour {phrase}"
        assert title_match.group(1).strip(), f"Le <title> est vide pour {phrase}"
