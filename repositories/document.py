from datetime import datetime
from typing import List, Optional, Dict

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ReturnDocument

from schemas.document import DocumentSourceType


class DocumentRepository:
    """Repository for document data access."""

    def __init__(self, collection: AsyncIOMotorCollection):
        """Initialize with MongoDB collection.
        
        Args:
            collection: MongoDB collection instance
        """
        self.col = collection

    async def create_document(self, document_data: dict) -> str:
        """Create a new document.
        
        Args:
            document_data: Document data to create
            
        Returns:
            str: ID of the created document
        """
        document_data["created_at"] = datetime.utcnow()
        document_data["updated_at"] = document_data["created_at"]

        result = await self.col.insert_one(document_data)
        return str(result.inserted_id)

    async def get_document(self, document_id: str, workspace_id: str) -> Optional[dict]:
        """Get a document by ID and workspace."""
        return await self.col.find_one({
            "_id": ObjectId(document_id),
            "workspace_id": workspace_id
        })

    async def update_document(
            self,
            document_id: str,
            workspace_id: str,
            update_data: dict
    ) -> Optional[dict]:
        """Update a document.
        
        Args:
            document_id: ID of the document to update
            workspace_id: ID of the workspace
            update_data: Dictionary of fields to update
            
        Returns:
            dict: The updated document or None if not found
        """
        if not update_data:
            return None
        update_data["updated_at"] = datetime.utcnow()

        return await self.col.find_one_and_update(
            {"_id": ObjectId(document_id), "workspace_id": workspace_id},
            {"$set": update_data},
            return_document=ReturnDocument.AFTER
        )

    async def delete_document(self, document_id: str, workspace_id: str) -> bool:
        """Delete a document."""
        result = await self.col.delete_one({
            "_id": ObjectId(document_id),
            "workspace_id": workspace_id
        })
        return result.deleted_count > 0

    async def delete_all_documents(self, workspace_id: str) -> int:
        """Delete all documents for a workspace.

        Args:
            workspace_id: ID of the workspace

        Returns:
            int: Number of documents deleted
        """
        result = await self.col.delete_many({"workspace_id": workspace_id})
        return result.deleted_count

    async def list_documents(
            self,
            workspace_id: str,
            skip: int = 0,
            limit: int = 100,
            source_type: Optional[DocumentSourceType] = None,
            source_id: Optional[str] = None
    ) -> List[dict]:
        """List documents in a workspace with optional filters."""
        query = {"workspace_id": workspace_id}
        if source_type:
            query["source_type"] = source_type
        if source_id:
            query["source_id"] = source_id

        cursor = self.col.find(query).skip(skip).limit(limit)
        documents = []
        async for doc in cursor:
            # Convert ObjectId to string for JSON serialization
            if '_id' in doc:
                doc['_id'] = str(doc['_id'])
            documents.append(doc)
        return documents

    async def search_documents(
            self,
            workspace_id: str,
            query: str,
            source_types: Optional[List[DocumentSourceType]] = None,
            source_ids: Optional[List[str]] = None,
            skip: int = 0,
            limit: int = 20
    ) -> List[dict]:
        """Search documents in a workspace."""
        search_filter = {"workspace_id": workspace_id, "$text": {"$search": query}}

        if source_types:
            search_filter["source_type"] = {"$in": [st.value for st in source_types]}
        if source_ids:
            search_filter["source_id"] = {"$in": source_ids}

        cursor = self.col.find(
            search_filter,
            {"score": {"$meta": "textScore"}}
        ).sort([("score", {"$meta": "textScore"})]).skip(skip).limit(limit)

        documents = []
        async for doc in cursor:
            if '_id' in doc:
                doc['_id'] = str(doc['_id'])
            documents.append(doc)
        return documents

    async def get_documents_by_ids(self, workspace_id: str, document_ids: List[str]) -> List[dict]:
        """Get multiple documents by their IDs.
        
        Args:
            workspace_id: ID of the workspace
            document_ids: List of document IDs to retrieve
            
        Returns:
            List of document dictionaries
        """
        if not document_ids:
            return []
            
        query = {
            "workspace_id": workspace_id,
            "_id": {"$in": [ObjectId(doc_id) for doc_id in document_ids]}
        }
        
        cursor = self.col.find(query)
        documents = []
        async for doc in cursor:
            if '_id' in doc:
                doc['_id'] = str(doc['_id'])
            documents.append(doc)
            
        # Maintain the same order as the input document_ids
        doc_map = {doc['_id']: doc for doc in documents}
        return [doc_map[doc_id] for doc_id in document_ids if doc_id in doc_map]

    async def count_documents_by_source(self, workspace_id: str) -> Dict[str, int]:
        """Count documents by source type in a workspace."""
        pipeline = [
            {"$match": {"workspace_id": workspace_id}},
            {"$group": {"_id": "$source_type", "count": {"$sum": 1}}}
        ]

        result = {}
        async for doc in self.col.aggregate(pipeline):
            result[doc["_id"]] = doc["count"]
        return result

    async def find_document_by_source(
            self,
            workspace_id: str,
            source_type: DocumentSourceType,
            source_id: str,
            document_id: str
    ) -> Optional[dict]:
        """Find a document by its source information."""
        return await self.col.find_one({
            "_id": ObjectId(document_id),
            "workspace_id": workspace_id,
            "source_type": source_type,
            "source_id": source_id
        })

    async def update_source_index(
            self,
            source_type: DocumentSourceType,
            source_id: str,
            workspace_id: str,
            count: Optional[int] = None
    ) -> None:
        """Update the source index with document count."""
        if count is None:
            count = await self.col.count_documents({
                "workspace_id": workspace_id,
                "source_type": source_type,
                "source_id": source_id
            })

        await self.col.update_one(
            {
                "workspace_id": workspace_id,
                "source_type": source_type,
                "source_id": source_id
            },
            {
                "$set": {
                    "document_count": count,
                    "last_updated": datetime.utcnow()
                }
            },
            upsert=True
        )
