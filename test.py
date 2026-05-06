from dotenv import load_dotenv
import os

load_dotenv()

print("POSTGRES:", os.getenv("POSTGRES_URL"))
print("MONGO:", os.getenv("MONGO_URL"))