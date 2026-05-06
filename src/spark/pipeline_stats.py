from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window
import psycopg2
from dotenv import load_dotenv
import os
import re

load_dotenv()

# ─────────────────────────────────────────────
# SPARK SESSION
# ─────────────────────────────────────────────
def creer_spark():
    # Fix Windows / Hadoop
    os.environ["HADOOP_HOME"] = "C:\\hadoop"
    os.environ["PATH"] = os.environ["PATH"] + ";C:\\hadoop\\bin"

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    jar_path = os.path.join(base_dir, "jars", "postgresql-42.7.3.jar")

    if not os.path.exists(jar_path):
        raise FileNotFoundError(f"Driver PostgreSQL introuvable: {jar_path}")

    return SparkSession.builder \
        .appName("Lotto649Pipeline") \
        .config("spark.driver.memory", "2g") \
        .config("spark.jars", jar_path) \
        .config("spark.driver.extraJavaOptions", "-Djava.security.manager=allow") \
        .master("local[*]") \
        .getOrCreate()


# ─────────────────────────────────────────────
# CHARGEMENT POSTGRES VIA SPARK JDBC
# ─────────────────────────────────────────────
def charger_tirages(spark):
    pg_url = os.getenv("POSTGRES_URL")

    match = re.search(r"postgresql://(.+):(.+)@(.+)", pg_url)
    if not match:
        raise ValueError("Format POSTGRES_URL invalide dans .env")

    user     = match.group(1)
    password = match.group(2)
    host_db  = match.group(3)

    jdbc_url = f"jdbc:postgresql://{host_db}"

    df = spark.read \
        .format("jdbc") \
        .option("url", jdbc_url) \
        .option("dbtable", "tirages") \
        .option("user", user) \
        .option("password", password) \
        .option("driver", "org.postgresql.Driver") \
        .load()

    df = df.orderBy("date_tirage")
    print(f"✅ {df.count()} tirages chargés depuis PostgreSQL")
    return df


# ─────────────────────────────────────────────
# PIPELINE PRINCIPAL
# ─────────────────────────────────────────────
def calculer_stats():
    spark = creer_spark()
    spark.sparkContext.setLogLevel("ERROR")

    df = charger_tirages(spark)

    print("\nSchema détecté :")
    df.printSchema()

    # ── 1. EXPLODE NUMÉROS ────────────────────
    df_explode = df.select(
        "id", "date_tirage",
        F.explode(F.array(
            "n1", "n2", "n3", "n4", "n5", "n6"
        )).alias("numero")
    )

    # ── 2. FRÉQUENCES ─────────────────────────
    print("\n📈 Calcul des fréquences...")
    df_freq = df_explode.groupBy("numero") \
        .agg(F.count("*").alias("frequence_totale"))

    # ── 3. DERNIÈRE APPARITION ────────────────
    print("📅 Calcul des dernières apparitions...")
    df_last = df_explode.groupBy("numero") \
        .agg(F.max("date_tirage").alias("derniere_apparition"))

    # ── 4. GAP MOYEN ──────────────────────────
    print("📏 Calcul des gaps moyens...")
    window_spec = Window.partitionBy("numero").orderBy("date_tirage")

    df_gaps = df_explode.withColumn(
        "prev_date",
        F.lag("date_tirage").over(window_spec)
    ).withColumn(
        "gap",
        F.datediff("date_tirage", "prev_date")
    ).groupBy("numero") \
     .agg(F.avg("gap").alias("gap_moyen"))

    # ── 5. JOIN STATS ─────────────────────────
    print("🔗 Assemblage des statistiques...")
    df_stats = df_freq \
        .join(df_last, "numero") \
        .join(df_gaps, "numero")

    # ── 6. CATÉGORISATION ─────────────────────
    print("🌡️ Catégorisation chaud/tiède/froid...")
    max_freq = df_stats.agg(F.max("frequence_totale")).collect()[0][0]
    min_freq = df_stats.agg(F.min("frequence_totale")).collect()[0][0]

    seuil_haut = min_freq + (max_freq - min_freq) * 0.66
    seuil_bas  = min_freq + (max_freq - min_freq) * 0.33

    df_stats = df_stats.withColumn(
        "categorie",
        F.when(F.col("frequence_totale") >= seuil_haut, "chaud")
         .when(F.col("frequence_totale") >= seuil_bas,  "tiede")
         .otherwise("froid")
    )

    print("\n🌡️ Distribution des catégories :")
    df_stats.groupBy("categorie").count().show()

    print("\n🔢 Top 10 numéros les plus fréquents :")
    df_stats.orderBy(F.desc("frequence_totale")).show(10)

    # ── 7. SAUVEGARDE POSTGRES ────────────────
    print("💾 Sauvegarde des stats...")
    sauvegarder_stats(df_stats.toPandas())

    # ── 8. COOCCURRENCES ──────────────────────
    print("🔗 Calcul des cooccurrences...")
    calculer_cooccurrences(df)

    spark.stop()
    print("\n✅ Pipeline Spark terminé avec succès !")


# ─────────────────────────────────────────────
# SAUVEGARDE STATS DANS POSTGRES
# ─────────────────────────────────────────────
def sauvegarder_stats(df):
    conn = psycopg2.connect(os.getenv("POSTGRES_URL"))
    cur  = conn.cursor()

    for _, row in df.iterrows():
        cur.execute("""
            INSERT INTO numeros_stats 
                (numero, frequence_totale, derniere_apparition, gap_moyen, categorie)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (numero) DO UPDATE SET
                frequence_totale    = EXCLUDED.frequence_totale,
                derniere_apparition = EXCLUDED.derniere_apparition,
                gap_moyen           = EXCLUDED.gap_moyen,
                categorie           = EXCLUDED.categorie,
                updated_at          = CURRENT_TIMESTAMP;
        """, (
            int(row["numero"]),
            int(row["frequence_totale"]),
            str(row["derniere_apparition"]),
            float(row["gap_moyen"]) if row["gap_moyen"] else None,
            str(row["categorie"])
        ))

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ {len(df)} numéros sauvegardés dans numeros_stats")


# ─────────────────────────────────────────────
# COOCCURRENCES
# ─────────────────────────────────────────────
def calculer_cooccurrences(df):
    from itertools import combinations

    rows  = df.select("n1", "n2", "n3", "n4", "n5", "n6").collect()
    pairs = {}

    for row in rows:
        nums = sorted([row.n1, row.n2, row.n3, row.n4, row.n5, row.n6])
        for a, b in combinations(nums, 2):
            pairs[(a, b)] = pairs.get((a, b), 0) + 1

    conn = psycopg2.connect(os.getenv("POSTGRES_URL"))
    cur  = conn.cursor()

    for (a, b), freq in pairs.items():
        cur.execute("""
            INSERT INTO cooccurrences (numero_a, numero_b, frequence)
            VALUES (%s, %s, %s)
            ON CONFLICT (numero_a, numero_b)
            DO UPDATE SET frequence = EXCLUDED.frequence;
        """, (a, b, freq))

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ {len(pairs)} cooccurrences sauvegardées")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    calculer_stats()