import sqlite3
import sys
from pathlib import Path

if sys.stdout.encoding.lower() != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

def get_missing_columns_sequences(db_path: str) -> set:
    """Vérifier quelles colonnes manquent dans email_sequences."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(email_sequences)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    required_columns = {'email_objet', 'email_corps', 'telegram_msg_id'}
    missing = required_columns - existing_columns
    conn.close()
    return missing

def add_missing_columns_sequences(db_path: str):
    """Ajouter les colonnes manquantes à email_sequences."""
    missing = get_missing_columns_sequences(db_path)
    if not missing:
        print("[OK] Toutes les colonnes email_sequences sont presentes")
        return
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    for col in missing:
        col_type = 'TEXT'
        try:
            cursor.execute(f"ALTER TABLE email_sequences ADD COLUMN {col} {col_type}")
            print(f"[OK] Colonne email_sequences.{col} ajoutee")
        except sqlite3.OperationalError as e:
            print(f"[WARN] email_sequences.{col} deja existante: {e}")
    conn.commit()
    conn.close()

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
        print("[OK] Toutes les colonnes sont presentes")
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
            print(f"[OK] Colonne ajoutee: {col}")
        except sqlite3.OperationalError as e:
            print(f"[WARN] Colonne deja existante ou erreur: {col} - {e}")
    conn.commit()
    conn.close()

def run_all_migrations(db_path: str):
    """Exécute toutes les migrations."""
    add_missing_columns(db_path)
    add_missing_columns_sequences(db_path)

if __name__ == "__main__":
    db_path = str(Path(__file__).parent.parent / "data" / "prospection.db")
    run_all_migrations(db_path)
