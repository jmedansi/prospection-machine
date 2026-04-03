import sqlite3
from pathlib import Path

def get_missing_columns(db_path: str) -> set:
    """Vérifier quelles colonnes manquent dans emails_envoyes."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(emails_envoyes)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    required_columns = {
        'date_premiere_ouverture',
        'date_derniere_ouverture',
        'nb_ouvertures',
        'nb_clics',
        'date_dernier_clic',
        'ip_ouverture',
        'user_agent_ouverture',
        'date_relance_prevue',
        'relance_type',
        'lead_temperature',
        'derniere_interaction',
        'score_lead'
    }
    missing = required_columns - existing_columns
    conn.close()
    return missing

def add_missing_columns(db_path: str):
    """Ajouter les colonnes manquantes à emails_envoyes."""
    missing = get_missing_columns(db_path)
    if not missing:
        print("✅ Toutes les colonnes sont présentes")
        return
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    for col in missing:
        if col in ['nb_ouvertures', 'nb_clics', 'score_lead']:
            default = 'DEFAULT 0'
            col_type = 'INTEGER'
        else:
            default = ''
            col_type = 'TEXT'
        try:
            cursor.execute(f"ALTER TABLE emails_envoyes ADD COLUMN {col} {col_type} {default}")
            print(f"✅ Colonne ajoutée: {col}")
        except sqlite3.OperationalError as e:
            print(f"⚠️ Colonne déjà existante ou erreur: {col} - {e}")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    db_path = str(Path(__file__).parent.parent / "data" / "prospection.db")
    add_missing_columns(db_path)
