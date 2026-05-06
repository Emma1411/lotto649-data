import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os
import  lightgbm as lgb
import warnings

warnings.filterwarnings("ignore")

load_dotenv()

# ====================== CONFIG ======================
WINDOW = 60
N_NUMBERS = 49
N_TEST = 400                    # On teste sur plus de tirages pour fiabilité
COST_TICKET = 3.0

# Gains RÉALISTES observés au Loto 6/49 (Canada / France / etc.)
GAINS_REALISTES = {
    0: 0,
    1: 0,
    2: 0,
    3: 8,           # Moyenne réelle souvent entre 7$ et 12$
    4: 65,          # Entre 40$ et 120$ en moyenne
    5: 1200,        # Très variable (souvent 600$ à 2500$)
    6: 1500000      # Jackpot moyen estimé (fortement variable)
}

# ====================== CONNEXION ======================
def get_engine():
    return create_engine(os.getenv("POSTGRES_URL"))

def load_data():
    engine = get_engine()
    tirages = pd.read_sql("""
        SELECT date_tirage, n1, n2, n3, n4, n5, n6, complementaire
        FROM tirages ORDER BY date_tirage ASC
    """, engine)

    stats = pd.read_sql("""
        SELECT numero, frequence_totale, gap_moyen, categorie
        FROM numeros_stats ORDER BY numero ASC
    """, engine)

    coocc = pd.read_sql("SELECT numero_a, numero_b, frequence FROM cooccurrences", engine)

    print(f"✅ {len(tirages)} tirages chargés")
    return tirages, stats, coocc


# ====================== FEATURES ======================
def build_features(tirages, stats, coocc):
    print("\n⚡ Construction des features...")

    draws = tirages[["n1","n2","n3","n4","n5","n6"]].values
    N = len(draws)

    mat = np.zeros((N, N_NUMBERS), dtype=np.int8)
    for i, row in enumerate(draws):
        mat[i, row-1] = 1

    cumsum = np.cumsum(mat, axis=0)
    rolling = np.zeros((N, N_NUMBERS), dtype=np.float32)
    for i in range(WINDOW, N):
        rolling[i] = (cumsum[i] - cumsum[i-WINDOW]) / (WINDOW * 6.0)

    stats = stats.copy()
    stats["cat_enc"] = stats["categorie"].astype("category").cat.codes

    # Co-occurrence
    co_score = np.zeros(N_NUMBERS, dtype=np.float32)
    for a, b, f in zip(coocc.numero_a, coocc.numero_b, coocc.frequence):
        co_score[a-1] += f
        co_score[b-1] += f
    co_score /= (co_score.max() + 1e-8)

    return draws, rolling, stats, co_score, tirages


# ====================== BACKTEST ======================
def backtest(tirages, stats, coocc, n_test=400):
    print("\n⚡ Backtesting réaliste avec LightGBM (rolling)...")

    draws, rolling, stats, co_score, tirages_df = build_features(tirages, stats, coocc)

    results = []
    start_idx = len(draws) - n_test

    for i in range(start_idx, len(draws)):
        # Rolling training
        X_train, y_train = [], []
        train_start = max(WINDOW, i - 1200)

        for t in range(train_start, i):
            freq = rolling[t]
            current = set(draws[t])
            for n in range(N_NUMBERS):
                s = stats.iloc[n]
                X_train.append([
                    freq[n],
                    s["frequence_totale"] / len(draws),
                    co_score[n],
                    (n % 2),
                    (n // 16),
                    s["cat_enc"] / 3.0
                ])
                y_train.append(1 if (n + 1) in current else 0)

        if len(X_train) < 800:
            continue

        # LightGBM
        train_set = lgb.Dataset(np.array(X_train, dtype=np.float32), label=np.array(y_train))
        params = {
            'objective': 'binary',
            'metric': 'auc',
            'boosting_type': 'gbdt',
            'num_leaves': 31,
            'learning_rate': 0.08,
            'feature_fraction': 0.75,
            'bagging_fraction': 0.8,
            'verbose': -1,
            'seed': 42
        }
        model = lgb.train(params, train_set, num_boost_round=120)

        # Prédiction
        freq = rolling[i]
        X_pred = []
        for n in range(N_NUMBERS):
            s = stats.iloc[n]
            X_pred.append([
                freq[n],
                s["frequence_totale"] / len(draws),
                co_score[n],
                n % 2,
                n // 16,
                s["cat_enc"] / 3.0
            ])

        proba = model.predict(np.array(X_pred, dtype=np.float32))
        top6_idx = np.argsort(proba)[::-1][:6]
        pred = {x + 1 for x in top6_idx}

        real = set(draws[i])
        hits = len(pred & real)

        results.append({
            "date": tirages_df.iloc[i]["date_tirage"],
            "hits": hits,
            "pred": sorted(pred),
            "real": sorted(real)
        })

        if (i - start_idx) % 40 == 0:
            print(f"⏳ {i - start_idx}/{n_test}")

    return pd.DataFrame(results)


# ====================== ANALYSE ======================
def analyze(df):
    print("\n" + "="*70)
    print("📊 BACKTESTING - VERSION RÉALISTE")
    print("="*70)

    print(df["hits"].value_counts().sort_index())

    avg_hits = df["hits"].mean()
    baseline = 6 * (6 / 49.0)

    print(f"\n🎯 Moyenne hits par tirage : {avg_hits:.3f}")
    print(f"📌 Hasard pur              : {baseline:.3f}")
    print(f"📈 Amélioration            : {(avg_hits / baseline - 1)*100:.1f}%")

    # Simulation financière
    total_cost = len(df) * COST_TICKET
    total_gain = df["hits"].map(GAINS_REALISTES).sum()
    profit = total_gain - total_cost
    roi = (profit / total_cost) * 100 if total_cost > 0 else 0

    print(f"\n💰 SIMULATION FINANCIÈRE (Gains réalistes)")
    print(f"Tirages joués      : {len(df)}")
    print(f"Coût total         : {total_cost:.2f} $")
    print(f"Gains totaux       : {total_gain:.2f} $")
    print(f"Profit / Perte     : {profit:.2f} $")
    print(f"ROI                : {roi:.2f}%")

    if roi > 0:
        print("⚠️  ROI positif sur cette période (à prendre avec prudence)")
    else:
        print("❌ Perte financière → stratégie non rentable")

    return avg_hits, roi


if __name__ == "__main__":
    tirages, stats, coocc = load_data()
    results = backtest(tirages, stats, coocc, n_test=N_TEST)
    analyze(results)
    print("\n🚀 Backtesting réaliste terminé")