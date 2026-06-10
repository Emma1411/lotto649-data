import requests
from bs4 import BeautifulSoup
import psycopg2
from dotenv import load_dotenv
import os
import time
from datetime import datetime, date

load_dotenv()

BASE_URL   = "https://ca.lottonumbers.com/lotto-649/numbers"
DETAIL_URL = "https://ca.lottonumbers.com/lotto-649/numbers"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Gains reels par categorie
GAINS_REELS = {
    "Match 6":             "6/6",
    "Match 5 plus Bonus":  "5/6+C",
    "Match 5":             "5/6",
    "Match 4":             "4/6",
    "Match 3":             "3/6",
    "Match 2 plus Bonus":  "2/6+C",
    "Match 2":             "2/6",
}

def get_connection():
    return psycopg2.connect(os.getenv("POSTGRES_URL"))


# ── Recupere la derniere date en base ─────────────────
def get_derniere_date():
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("SELECT MAX(date_tirage) FROM tirages")
    result = cur.fetchone()[0]
    cur.close()
    conn.close()
    return result


def scraper_details(date_str: str):
    url = f"{DETAIL_URL}/{date_str}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return {}

        soup  = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table", class_="res-breakdown-table")
        if not table:
            return {}

        def parse_montant(txt):
            txt = txt.replace("$", "").replace(",", "").strip()
            try:
                return float(txt)
            except ValueError:
                return 0.0

        def parse_winners(txt):
            txt = txt.replace(",", "").strip()
            try:
                return int(txt)
            except ValueError:
                return 0

        details = {
            "match_6_prize":     0.0, "match_6_winners":    0,
            "match_5c_prize":    0.0, "match_5c_winners":   0,
            "match_5_prize":     0.0, "match_5_winners":    0,
            "match_4_prize":     0.0, "match_4_winners":    0,
            "match_3_prize":     0.0, "match_3_winners":    0,
            "match_2c_prize":    0.0, "match_2c_winners":   0,
            "match_2_winners":   0,
            "gold_ball_prize":   0.0, "gold_ball_winners":  0,
            "next_gold_ball":    0.0,
            "total_winners":     0,   "total_fund":         0.0,
            "jackpot_montant":   None,
        }

        rows = table.find("tbody").find_all("tr")
        for row in rows:
            cols   = row.find_all("td")
            if len(cols) < 4:
                continue
            niveau  = cols[0].get_text(strip=True)
            prize   = parse_montant(cols[1].get_text(strip=True))
            winners = parse_winners(cols[2].get_text(strip=True))

            if niveau == "Match 6":
                details["match_6_prize"]    = prize
                details["match_6_winners"]  = winners
                details["jackpot_montant"]  = int(prize)
            elif niveau == "Match 5 plus Bonus":
                details["match_5c_prize"]   = prize
                details["match_5c_winners"] = winners
            elif niveau == "Match 5":
                details["match_5_prize"]    = prize
                details["match_5_winners"]  = winners
            elif niveau == "Match 4":
                details["match_4_prize"]    = prize
                details["match_4_winners"]  = winners
            elif niveau == "Match 3":
                details["match_3_prize"]    = prize
                details["match_3_winners"]  = winners
            elif niveau == "Match 2 plus Bonus":
                details["match_2c_prize"]   = prize
                details["match_2c_winners"] = winners
            elif niveau == "Match 2":
                details["match_2_winners"]  = winners
            elif niveau == "Gold Ball Jackpot":
                details["gold_ball_prize"]   = prize
                details["gold_ball_winners"] = winners
            elif niveau == "Next Gold Ball Jackpot":
                details["next_gold_ball"]   = prize
            elif niveau == "Totals":
                details["total_winners"]    = winners
                fund = parse_montant(cols[3].get_text(strip=True))
                details["total_fund"]       = fund

        return details

    except Exception as e:
        print(f"Erreur details {date_str}: {e}")
        return {}


def inserer_details(date_obj, date_str: str, conn, cur):
    details = scraper_details(date_str)
    if not details:
        return

    cur.execute("""
        SELECT * FROM sp_tirage_details_upsert(
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
    """, (
        date_obj,
        details["match_6_prize"],    details["match_6_winners"],
        details["match_5c_prize"],   details["match_5c_winners"],
        details["match_5_prize"],    details["match_5_winners"],
        details["match_4_prize"],    details["match_4_winners"],
        details["match_3_prize"],    details["match_3_winners"],
        details["match_2c_prize"],   details["match_2c_winners"],
        details["match_2_winners"],
        details["gold_ball_prize"],  details["gold_ball_winners"],
        details["next_gold_ball"],
        details["total_winners"],    details["total_fund"],
    ))

# ── Parse la page principale ──────────────────────────
def scraper_tirages(depuis: date):
    """
    Scrape tous les tirages depuis 'depuis' jusqu'a aujourd'hui
    Retourne une liste de dicts
    """
    tirages = []
    page    = 1

    print(f"Scraping depuis {depuis}...")

    while True:
        url = BASE_URL if page == 1 else f"{BASE_URL}?page={page}"
        print(f"Page {page}...")

        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                print(f"Erreur HTTP {r.status_code}")
                break

            soup  = BeautifulSoup(r.text, "html.parser")
            boxes = soup.find_all("div", class_="resultBox")

            if not boxes:
                print("Aucun tirage trouve sur cette page")
                break

            stop = False

            for box in boxes:
                try:
                    # Date
                    date_div = box.find("div")
                    date_text = date_div.get_text(strip=True)

                    # Extraire jour et date (ex: "SaturdayJune 6 2026")
                    # Separer le jour de semaine du reste
                    strong = date_div.find("strong")
                    jour_semaine = strong.get_text(strip=True).lower() if strong else ""

                    # Nettoyer le texte pour avoir juste la date
                    date_clean = date_text.replace(
                        strong.get_text(strip=True), ""
                    ).strip() if strong else date_text

                    # Parser la date (ex: "June 6 2026")
                    try:
                        date_obj = datetime.strptime(date_clean, "%B %d %Y").date()
                    except ValueError:
                        try:
                            date_obj = datetime.strptime(date_clean, "%B %d, %Y").date()
                        except ValueError:
                            continue

                    # Si la date est avant notre seuil, on arrete
                    if date_obj <= depuis:
                        stop = True
                        break

                    # Numeros
                    balls      = box.find_all("li", class_="ball")
                    bonus_ball = box.find("li", class_="bonus-ball")

                    numeros = []
                    for b in balls:
                        classes = b.get("class", [])
                        if "bonus-ball" not in classes:
                            try:
                                numeros.append(int(b.get_text(strip=True)))
                            except ValueError:
                                pass

                    if len(numeros) != 6:
                        continue

                    complementaire = int(bonus_ball.get_text(strip=True)) if bonus_ball else 0

                    # Jour de semaine en francais
                    jours_fr = {
                        "monday":    "lundi",
                        "tuesday":   "mardi",
                        "wednesday": "mercredi",
                        "thursday":  "jeudi",
                        "friday":    "vendredi",
                        "saturday":  "samedi",
                        "sunday":    "dimanche",
                    }
                    jour_fr = jours_fr.get(jour_semaine, jour_semaine)

                    # Lien detail
                    lien = box.find("a", class_="details-btn")
                    date_str = lien["href"].split("/")[-1] if lien else str(date_obj)

                    tirages.append({
                        "date_tirage":    date_obj,
                        "jour_semaine":   jour_fr,
                        "n1":             numeros[0],
                        "n2":             numeros[1],
                        "n3":             numeros[2],
                        "n4":             numeros[3],
                        "n5":             numeros[4],
                        "n6":             numeros[5],
                        "complementaire": complementaire,
                        "date_str":       date_str,
                    })

                    print(f"  {date_obj} | {numeros} + {complementaire}")

                except Exception as e:
                    print(f"Erreur parsing tirage: {e}")
                    continue

            if stop:
                print(f"Date seuil atteinte ({depuis}) - arret")
                break

            # Verifier s'il y a une page suivante
            next_btn = soup.find("a", string=lambda t: t and "Next" in t)
            if not next_btn:
                break

            page += 1
            time.sleep(1.5)  # Respecter le serveur

        except Exception as e:
            print(f"Erreur page {page}: {e}")
            break

    return tirages


# ── Inserer dans PostgreSQL ───────────────────────────
def inserer_tirages(tirages: list):
    if not tirages:
        print("Aucun tirage a inserer")
        return 0

    conn = get_connection()
    cur  = conn.cursor()
    ok   = 0

    for t in tirages:
        try:
            details = scraper_details(t["date_str"])
            jackpot = details.get("jackpot_montant", None)

            cur.execute("""
                INSERT INTO tirages
                    (date_tirage, jour_semaine,
                     n1, n2, n3, n4, n5, n6,
                     complementaire, jackpot_montant)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                t["date_tirage"], t["jour_semaine"],
                t["n1"], t["n2"], t["n3"],
                t["n4"], t["n5"], t["n6"],
                t["complementaire"], jackpot,
            ))

            # Inserer aussi les details
            inserer_details(t["date_tirage"], t["date_str"], conn, cur)

            conn.commit()
            ok += 1
            time.sleep(0.8)

        except Exception as e:
            print(f"Erreur insertion {t['date_tirage']}: {e}")
            conn.rollback()
            continue

    cur.close()
    conn.close()
    print(f"{ok}/{len(tirages)} tirages inseres avec details")
    return ok

# ── Verifier et mettre a jour les tickets ─────────────
def verifier_tickets():
    """
    Compare les tickets en attente avec les vrais tirages
    et met a jour leur statut + resultat
    """
    conn = get_connection()
    cur  = conn.cursor()

    # Tickets en attente avec une date de tirage
    cur.execute("""
        SELECT t.id, t.numeros_joues, t.date_tirage, t.cout_ticket
        FROM tickets_joues t
        WHERE t.statut = 'en_attente'
        AND t.date_tirage IS NOT NULL
    """)
    tickets = cur.fetchall()

    print(f"{len(tickets)} tickets en attente a verifier")
    mis_a_jour = 0

    for ticket in tickets:
        ticket_id     = ticket[0]
        numeros_joues = ticket[1]
        date_tirage   = ticket[2]
        cout          = float(ticket[3])

        # Chercher le tirage correspondant
        cur.execute("""
            SELECT id, n1, n2, n3, n4, n5, n6, complementaire
            FROM tirages
            WHERE date_tirage = %s
        """, (date_tirage,))
        tirage = cur.fetchone()

        if not tirage:
            continue

        tirage_id      = tirage[0]
        numeros_reels  = list(tirage[1:7])
        complementaire = tirage[7]

        # Calculer les correspondances
        joues = set(numeros_joues)
        reels = set(numeros_reels)
        bons  = len(joues & reels)
        bonus = complementaire in joues

        # Determiner categorie et gain
        if bons == 6:
            categorie = "6/6"
            gain      = 5000000.00
        elif bons == 5 and bonus:
            categorie = "5/6+C"
            gain      = 188973.00
        elif bons == 5:
            categorie = "5/6"
            gain      = 1301.00
        elif bons == 4:
            categorie = "4/6"
            gain      = 85.00
        elif bons == 3:
            categorie = "3/6"
            gain      = 10.00
        elif bons == 2 and bonus:
            categorie = "2/6+C"
            gain      = 5.00
        else:
            categorie = "perdu"
            gain      = 0.00

        profit   = gain - cout
        statut   = "gagnant" if gain > 0 else "perdant"

        # Inserer dans tickets_resultats
        cur.execute("""
            INSERT INTO tickets_resultats
                (ticket_id, numero_tirage,
                 numeros_gagnants_reels, nb_bons_numeros,
                 complementaire_bon, categorie_gain,
                 montant_gagne, profit_net)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticket_id) DO UPDATE SET
                numeros_gagnants_reels = EXCLUDED.numeros_gagnants_reels,
                nb_bons_numeros        = EXCLUDED.nb_bons_numeros,
                complementaire_bon     = EXCLUDED.complementaire_bon,
                categorie_gain         = EXCLUDED.categorie_gain,
                montant_gagne          = EXCLUDED.montant_gagne,
                profit_net             = EXCLUDED.profit_net
        """, (
            ticket_id,
            tirage_id,
            numeros_reels,
            bons,
            bonus,
            categorie,
            gain,
            profit,
        ))

        # Mettre a jour statut du ticket
        cur.execute("""
            UPDATE tickets_joues
            SET statut = %s
            WHERE id = %s
        """, (statut, ticket_id))

        mis_a_jour += 1
        print(f"  Ticket {ticket_id} | {bons} bons | {categorie} | +{gain} $")

    conn.commit()
    cur.close()
    conn.close()
    print(f"{mis_a_jour} tickets mis a jour")
    return mis_a_jour


if __name__ == "__main__":
    # 1. Trouver la derniere date en base
    derniere_date = get_derniere_date()
    print(f"Derniere date en base : {derniere_date}")

    # 2. Scraper les tirages manquants
    tirages = scraper_tirages(depuis=derniere_date)
    print(f"{len(tirages)} tirages trouves a inserer")

    # 3. Inserer en base
    if tirages:
        inserer_tirages(tirages)

    # 4. Verifier les tickets en attente
    verifier_tickets()

    print("\nMise a jour terminee")