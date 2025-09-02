from datetime import datetime
from typing import List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection


class ChunkRepository:
    """Repository for chunk data access."""

    def __init__(self, collection: AsyncIOMotorCollection):
        self.col = collection

    async def create_chunk(self, chunk_data: dict) -> str:
        """Create a new chunk and return its ID."""
        chunk_data.update({
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })
        result = await self.col.insert_one(chunk_data)
        return str(result.inserted_id)

    async def create_chunks_batch(self, chunks_data: List[dict]) -> List[str]:
        """Create multiple chunks in a single batch."""
        if not chunks_data:
            return []

        now = datetime.utcnow()
        for chunk in chunks_data:
            chunk.update({"created_at": now, "updated_at": now})

        result = await self.col.insert_many(chunks_data)
        return [str(id) for id in result.inserted_ids]

    async def get_chunk(self, chunk_id: str, workspace_id: str) -> Optional[dict]:
        """Get a chunk by ID and workspace."""
        chunk = await self.col.find_one({
            "_id": ObjectId(chunk_id),
            "workspace_id": workspace_id
        })
        if chunk and '_id' in chunk:
            chunk['_id'] = str(chunk['_id'])
        return chunk

    async def get_chunks_by_document(self, document_id: str, workspace_id: str) -> List[dict]:
        """Get all chunks for a specific document."""
        cursor = self.col.find({
            "document_id": document_id,
            "workspace_id": workspace_id
        })
        return [{"_id": str(doc["_id"]), **doc} async for doc in cursor]

    async def update_chunk(self, chunk_id: str, workspace_id: str, update_data: dict) -> Optional[dict]:
        """Update a chunk and return the updated document."""
        update_data["updated_at"] = datetime.utcnow()
        return await self.col.find_one_and_update(
            {"_id": ObjectId(chunk_id), "workspace_id": workspace_id},
            {"$set": update_data},
            return_document=True
        )

    async def delete_chunks_by_document(self, document_id: str) -> int:
        """Delete all chunks for a document and return the count of deleted chunks."""
        result = await self.col.delete_many({"document_id": document_id})
        return result.deleted_count

    async def vector_search(self, query_embedding: List[float], workspace_id: str, limit: int = 10) -> List[dict]:
        """Perform a vector similarity search."""
        pipeline = [
            {
                "$search": {
                    "cosmosSearch": {
                        "vector": query_embedding,
                        "path": "vector_embedding",
                        "k": limit
                    },
                    "returnStoredSource": True
                }
            },
            {"$match": {"workspace_id": workspace_id}},
            {"$limit": limit}
        ]

        cursor = self.col.aggregate(pipeline)
        return [{"_id": str(doc["_id"]), **doc} async for doc in cursor]
