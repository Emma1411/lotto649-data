import pandas as pd
import psycopg2
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

# ─────────────────────────────
# CONNEXION POSTGRES
# ─────────────────────────────
def connect_postgres():
    return psycopg2.connect(os.getenv("POSTGRES_URL"))

# ─────────────────────────────
# CLEAN DATE SAFE
# ─────────────────────────────
def clean_date(date_str):
    try:
        # correction erreurs fréquentes Kaggle
        date_str = date_str.replace("Febraury", "February")
        return datetime.strptime(date_str.strip(), "%B %d, %Y").strftime("%Y-%m-%d")
    except Exception:
        return None

# ─────────────────────────────
# ETL PRINCIPAL
# ─────────────────────────────
def inserer_tous_tirages():
    print("Lecture du CSV...")
    df = pd.read_csv("data/lotto_649_complete.csv")

    print(f"{len(df)} lignes détectées")

    conn = connect_postgres()
    cur = conn.cursor()

    ok = 0
    erreurs = 0
    ignores = 0

    print("Insertion en cours...")

    for index, row in df.iterrows():
        try:
            date = clean_date(row["Date"])
            if not date:
                ignores += 1
                continue

            cur.execute("""
                INSERT INTO tirages (
                    date_tirage,
                    n1, n2, n3, n4, n5, n6, complementaire
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING;
            """, (
                date,
                int(row["Num1"]),
                int(row["Num2"]),
                int(row["Num3"]),
                int(row["Num4"]),
                int(row["Num5"]),
                int(row["Num6"]),
                int(row["Bonus"])
            ))

            ok += 1

            if ok % 500 == 0:
                print(f"{ok} lignes insérées...")

        except Exception as e:
            conn.rollback()   # reset transaction cassée
            erreurs += 1
            print(f"Erreur ligne {index} : {e}")

    # commit FINAL (très important)
    conn.commit()

    cur.close()
    conn.close()

    print("\n==============================")
    print("INSERT TERMINÉ")
    print("OK :", ok)
    print("IGNORÉES :", ignores)
    print("ERREURS :", erreurs)
    print("==============================")

    # ─────────────────────────────
    # VERIFICATION
    # ─────────────────────────────
    conn = connect_postgres()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM tirages;")
    total = cur.fetchone()[0]

    cur.execute("SELECT MIN(date_tirage), MAX(date_tirage) FROM tirages;")
    min_date, max_date = cur.fetchone()

    cur.close()
    conn.close()

    print("\nVérification DB")
    print("Total :", total)
    print("Min date :", min_date)
    print("Max date :", max_date)

# ─────────────────────────────
# MAIN
# ─────────────────────────────
if __name__ == "__main__":
    inserer_tous_tirages()