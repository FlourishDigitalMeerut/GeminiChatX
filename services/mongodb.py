import os
from motor.motor_asyncio import AsyncIOMotorClient # pyright: ignore[reportMissingImports]
from contextlib import asynccontextmanager
import logging
from config.settings import MONGODB_URI, DATABASE_NAME, USERS_COLLECTION, API_KEYS_COLLECTION, REFRESH_TOKENS_COLLECTION, PASSWORD_RESET_SESSIONS_COLLECTION
from fastapi import FastAPI

logger = logging.getLogger(__name__)

class MongoDB:
    client: AsyncIOMotorClient = None
    db = None

mongodb = MongoDB()

async def get_database():
    return mongodb.db

async def get_users_collection():
    db = await get_database()
    return db[USERS_COLLECTION]

async def get_api_keys_collection():
    db = await get_database()
    return db[API_KEYS_COLLECTION]

async def get_refresh_tokens_collection():
    db = await get_database()
    return db[REFRESH_TOKENS_COLLECTION]

async def get_password_reset_sessions_collection():
    db = await get_database()
    return db[PASSWORD_RESET_SESSIONS_COLLECTION]

@asynccontextmanager
async def lifespan_manager(app: FastAPI):
    # Startup
    try:
        mongodb.client = AsyncIOMotorClient(MONGODB_URI)
        mongodb.db = mongodb.client[DATABASE_NAME]
        
        await mongodb.client.admin.command('ping')
        logger.info("Successfully connected to MongoDB!")
        
        # Create indexes
        users_collection = await get_users_collection()
        await users_collection.create_index("email", unique=True)
        await users_collection.create_index("username", unique=True)
        await users_collection.create_index("created_at")
        
        refresh_tokens_collection = await get_refresh_tokens_collection()
        await refresh_tokens_collection.create_index("user_id")
        await refresh_tokens_collection.create_index("expires_at", expireAfterSeconds=0)

        password_reset_collection = await get_password_reset_sessions_collection()
        await password_reset_collection.create_index("session_token", unique=True)
        await password_reset_collection.create_index("expires_at", expireAfterSeconds=0)
        await password_reset_collection.create_index("email")
        await password_reset_collection.create_index("used")
        
        logger.info("MongoDB indexes created successfully")
        
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise
    
    yield
    
    # Shutdown
    if mongodb.client:
        mongodb.client.close()
        logger.info("MongoDB connection closed")