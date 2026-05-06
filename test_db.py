from src.database.postgres import connect_postgres
from src.database.mongoDB import connect_mongo

# Test PostgreSQL
conn = connect_postgres()
print("Postgres OK")
conn.close()

# Test MongoDB
client = connect_mongo()
print("Mongo OK")