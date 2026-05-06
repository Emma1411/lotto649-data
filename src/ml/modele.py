import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
import pickle
import warnings

warnings.filterwarnings("ignore")

load_dotenv()

WINDOW = 50
N_NUMBERS = 49


# ======================
# CONNEXION
# ======================
def get_engine():
    return create_engine(os.getenv("POSTGRES_URL"))


# ======================
# LOAD DATA
# ======================
def load_data():
    engine = get_engine()

    tirages = pd.read_sql("""
        SELECT date_tirage, n1, n2, n3, n4, n5, n6
        FROM tirages
        ORDER BY date_tirage ASC
    """, engine)

    stats = pd.read_sql("""
        SELECT numero, frequence_totale, gap_moyen, gap_actuel, categorie
        FROM numeros_stats
        ORDER BY numero ASC
    """, engine)

    coocc = pd.read_sql("""
        SELECT numero_a, numero_b, frequence
        FROM cooccurrences
    """, engine)

    return tirages, stats, coocc


# ======================
# FEATURE ENGINEERING (CLEAN + FAST)
# ======================
def build_features(tirages, stats, coocc, window=WINDOW):

    print("⚡ Feature engineering optimisé...")

    draws = tirages[["n1","n2","n3","n4","n5","n6"]].values
    n_draws = len(draws)

    # one hot matrix
    mat = np.zeros((n_draws, N_NUMBERS), dtype=np.int8)

    for i, row in enumerate(draws):
        mat[i, row - 1] = 1

    # rolling freq (vectorisé)
    cumsum = np.cumsum(mat, axis=0)
    rolling = np.zeros_like(mat, dtype=np.float32)

    for i in range(window, n_draws):
        rolling[i] = (cumsum[i] - cumsum[i-window]) / (window * 6)

    # encode category
    stats = stats.copy()
    stats["cat"] = stats["categorie"].astype("category").cat.codes

    # coocc score
    co = np.zeros(N_NUMBERS)

    for a, b, f in zip(coocc.numero_a, coocc.numero_b, coocc.frequence):
        co[a-1] += f
        co[b-1] += f

    co = co / (co.max() + 1e-9)

    X, y = [], []

    for i in range(window, n_draws):

        current = set(draws[i])
        freq = rolling[i]

        for n in range(N_NUMBERS):

            s = stats.iloc[n]

            X.append([
                freq[n],
                s.frequence_totale / n_draws,
                (s.gap_moyen or 0) / 100,
                co[n],
                n % 2,
                n // 16
            ])

            y.append(1 if (n+1) in current else 0)

    X = np.array(X, dtype=np.float32)
    y = np.array(y, dtype=np.int8)

    print(f"✅ Dataset: {X.shape} | Positifs: {y.sum():,}")

    return X, y, stats, rolling


# ======================
# TRAIN (CORRIGÉ)
# ======================
def train(X, y):

    print("\n🤖 Training model...")

    model = RandomForestClassifier(
        n_estimators=400,
        max_depth=12,
        min_samples_leaf=5,
        max_features="sqrt",
        class_weight="balanced",
        n_jobs=-1,
        random_state=42
    )

    # IMPORTANT: TimeSeriesSplit (anti leakage)
    tscv = TimeSeriesSplit(n_splits=3)

    scores = cross_val_score(
        model,
        X,
        y,
        cv=tscv,
        scoring="roc_auc",
        n_jobs=-1
    )

    print(f"📊 AUC: {scores.mean():.4f} ± {scores.std():.4f}")

    model.fit(X, y)

    return model


# ======================
# PREDICTION
# ======================
def predict(model, stats, rolling):

    print("\n🎯 Prediction...")

    last = rolling[-1]

    Xp = []

    for i in range(N_NUMBERS):

        s = stats.iloc[i]

        Xp.append([
            last[i],
            s.frequence_totale / len(stats),
            (s.gap_moyen or 0) / 100,
            0,
            i % 2,
            i // 16
        ])

    Xp = np.array(Xp, dtype=np.float32)

    proba = model.predict_proba(Xp)[:, 1]

    stats = stats.copy()
    stats["proba"] = proba

    top = stats.sort_values("proba", ascending=False).head(15)

    print("\n🏆 TOP 15 :")
    print(top[["numero","proba","categorie"]])

    return stats


# ======================
# SAVE
# ======================
def save(model, stats):

    os.makedirs("models", exist_ok=True)

    pickle.dump(model, open("models/model.pkl","wb"))

    stats.sort_values("proba", ascending=False)\
         .head(20)\
         .to_csv("models/top20.csv", index=False)

    print("💾 Saved")


# ======================
# MAIN
# ======================
if __name__ == "__main__":

    tirages, stats, coocc = load_data()

    X, y, stats, rolling = build_features(tirages, stats, coocc)

    model = train(X, y)

    stats = predict(model, stats, rolling)

    save(model, stats)

    print("\n🚀 Pipeline terminé")