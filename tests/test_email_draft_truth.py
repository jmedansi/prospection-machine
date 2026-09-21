# -*- coding: utf-8 -*-
import pytest
from database import get_conn, prospects as prospects_repo, campagnes as campagnes_repo
from envoi.sequence_engine import prepare_step, get_custom_step_email
from dashboard.routes.campagnes import _render_v2_email


def test_custom_ai_email_is_single_source_of_truth():
    """Vérifie que l'email rédigé par l'agent IA prime sur tout template générique."""
    import uuid
    uid = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        # 1. Créer une campagne avec un template générique
        cur = conn.execute("INSERT INTO campagnes (nom, statut) VALUES (?, 'actif')", (f"Campagne Test {uid}",))
        cid = cur.lastrowid
        cur_l = conn.execute("INSERT INTO listes (campagne_id, nom) VALUES (?, ?)", (cid, f"Liste Test {uid}"))
        lid = cur_l.lastrowid
        
        # Insérer un template générique pour cette campagne
        conn.execute("""
            INSERT INTO sequence_templates (campagne_id, position, nom, objet, corps, actif)
            VALUES (?, 0, 'Generic Template', 'Template générique objet', 'Template générique corps', 1)
        """, (cid,))
        conn.commit()
        
    # 2. Créer un prospect avec un email rédigé par l'agent IA dans data_extra
    ia_objet = "Opportunité spécifique pour Restaurant Le Gourmet"
    ia_corps = "Bonjour Chef,\n\nVoici notre analyse sur-mesure de votre présence en ligne..."
    
    res = prospects_repo.insert_prospect(
        lid,
        nom="Le Gourmet",
        email=f"chef_{cid}@legourmet.fr",
        data_extra={
            "email_objet": ia_objet,
            "email_corps": ia_corps,
            "email_objet_2": "Re: Opportunité spécifique",
            "email_corps_2": "Bonjour Chef, je me permets de relancer mon message précédent."
        }
    )
    assert res['success'] is True
    pid = res['prospect_id']

    # 3. Récupérer le prospect
    p = prospects_repo.get_prospect(pid)
    assert p is not None
    assert p['email_objet'] == ia_objet
    assert p['email_corps'] == ia_corps

    # 4. Vérifier get_custom_step_email
    custom_0 = get_custom_step_email(p, 0)
    assert custom_0 is not None
    assert custom_0[0] == ia_objet
    assert custom_0[1] == ia_corps

    # 5. Vérifier la prévisualisation (_render_v2_email)
    rendered = _render_v2_email(p)
    assert rendered['source'] == 'ia_redaction'
    assert rendered['objet'] == ia_objet
    assert ia_corps in rendered['corps_texte']
    assert "Template générique" not in rendered['corps_texte']

    # 6. Vérifier la préparation pour l'envoi (prepare_step)
    prepared = prepare_step(cid, pid, 0, 'Envoi initial')
    assert prepared['ok'] is True
    assert prepared['objet'] == ia_objet
    assert prepared['corps'] == ia_corps
    assert prepared['humanise'] is False
    assert "Template générique" not in prepared['corps']

    # 7. Vérifier la relance (position 1)
    custom_1 = get_custom_step_email(p, 1)
    assert custom_1 is not None
    assert "Re:" in custom_1[0]
    assert "relancer" in custom_1[1]
