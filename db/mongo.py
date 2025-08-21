from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
from config.settings import settings

class MongoDatabase:
    def __init__(self, client: AsyncIOMotorClient, db_name: Optional[str] = None):
        """
        Initialize MongoDB connection.
        
        Args:
            client: AsyncIOMotorClient instance
            db_name: Optional database name, defaults to settings.MONGO_DB
        """
        self.client = client
        self.db = self.client[db_name or settings.MONGO_DB]

    def get_collection(self, collection_name: str):
        """Get a collection by name.
        
        Args:
            collection_name: Name of the collection to retrieve
            
        Returns:
            The requested collection instance
        """
        return self.db[collection_name]

    async def close(self):
        """Close MongoDB connection."""
        self.client.close()
