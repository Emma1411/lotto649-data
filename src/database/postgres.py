import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def connect_postgres():
    return psycopg2.connect(os.getenv("POSTGRES_URL"))