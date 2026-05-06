import kagglehub
import shutil
import os

# Télécharger le dataset
print("📥 Téléchargement du dataset Kaggle...")
path = kagglehub.dataset_download("markkruger/lotto-649-historical-dataset-1982-2025")
print(f"✅ Dataset téléchargé ici : {path}")

# Copier les fichiers dans ton dossier data/
os.makedirs("data", exist_ok=True)

for fichier in os.listdir(path):
    src = os.path.join(path, fichier)
    dst = os.path.join("data", fichier)
    shutil.copy(src, dst)
    print(f"📁 Copié : {fichier} → data/")

print("\n✅ Fichiers disponibles dans data/ :")
for f in os.listdir("data"):
    print(f"   - {f}")