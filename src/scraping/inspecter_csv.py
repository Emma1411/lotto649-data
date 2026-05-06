import pandas as pd

# Lire le CSV
df = pd.read_csv("data/lotto_649_complete.csv")

print("📊 Nombre de lignes :", len(df))
print("\n📋 Colonnes détectées :")
for i, col in enumerate(df.columns):
    print(f"   [{i}] {col}")

print("\n🔍 Premières lignes :")
print(df.head(5).to_string())

print("\n🔍 Dernières lignes :")
print(df.tail(3).to_string())

print("\n📈 Types de données :")
print(df.dtypes)

print("\n⚠️ Valeurs manquantes :")
print(df.isnull().sum())