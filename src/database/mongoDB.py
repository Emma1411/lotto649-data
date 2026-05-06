import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

def connect_mongo():
    return MongoClient(os.getenv("MONGO_URL"))