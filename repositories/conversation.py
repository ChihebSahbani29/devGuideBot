from bson import ObjectId
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorCollection

class ConversationRepository:
    def __init__(self, collection: AsyncIOMotorCollection):
        """Initialize conversation repository with MongoDB collection.
        
        Args:
            collection: MongoDB collection instance
        """
        self.col = collection

    async def create_conversation(self, workspace_id: str, data: dict) -> str:
        """Create a new conversation in the specified workspace.
        
        Args:
            workspace_id: ID of the workspace this conversation belongs to
            data: Conversation data including title and messages
            
        Returns:
            str: The ID of the created conversation
        """
        now = datetime.utcnow()
        conversation_data = {
            "workspace_id": ObjectId(workspace_id),
            "title": data["title"],
            "messages": data.get("messages", []),
            "created_at": now,
            "updated_at": now
        }
        result = await self.col.insert_one(conversation_data)
        return str(result.inserted_id)

    async def get_conversation(self, workspace_id: str, conversation_id: str) -> dict | None:
        """Get a specific conversation from a workspace.
        
        Args:
            workspace_id: ID of the workspace
            conversation_id: ID of the conversation to retrieve
            
        Returns:
            Optional[dict]: The conversation data or None if not found
        """
        return await self.col.find_one({
            "_id": ObjectId(conversation_id),
            "workspace_id": ObjectId(workspace_id)
        })

    async def list_conversations(self, workspace_id: str) -> list[dict]:
        """List all conversations in a workspace.
        
        Args:
            workspace_id: ID of the workspace
            
        Returns:
            list[dict]: List of conversations, or empty list if none found
            
        Raises:
            ValueError: If workspace_id is invalid
        """
        try:
            # Convert workspace_id to ObjectId to validate format
            workspace_oid = ObjectId(workspace_id)
            
            # Find conversations and convert cursor to list
            cursor = self.col.find({"workspace_id": workspace_oid}).sort("updated_at", -1)
            conversations = await cursor.to_list(length=100)  # Limit to 100 conversations
            
            # Convert ObjectId to string for JSON serialization
            for conv in conversations:
                conv['_id'] = str(conv['_id'])
                conv['workspace_id'] = str(conv['workspace_id'])
                
            return conversations or []
            
        except Exception as e:
            # Log the error and re-raise with more context
            error_msg = f"Error listing conversations for workspace {workspace_id}: {str(e)}"
            raise ValueError(error_msg) from e

    async def update_conversation(
        self, 
        workspace_id: str, 
        conversation_id: str, 
        update_data: dict
    ) -> bool:
        """Update a conversation.
        
        Args:
            workspace_id: ID of the workspace
            conversation_id: ID of the conversation to update
            update_data: Fields to update
            
        Returns:
            bool: True if the update was successful, False otherwise
        """
        if not update_data:
            return False
            
        update_data["updated_at"] = datetime.utcnow()
            
        result = await self.col.update_one(
            {
                "_id": ObjectId(conversation_id),
                "workspace_id": ObjectId(workspace_id)
            },
            {"$set": update_data}
        )
        return result.modified_count > 0

    async def delete_conversation(self, workspace_id: str, conversation_id: str) -> bool:
        """Delete a conversation from a workspace.
        
        Args:
            workspace_id: ID of the workspace
            conversation_id: ID of the conversation to delete
            
        Returns:
            bool: True if the deletion was successful, False otherwise
        """
        result = await self.col.delete_one({
            "_id": ObjectId(conversation_id),
            "workspace_id": ObjectId(workspace_id)
        })
        return result.deleted_count > 0
        
    async def add_message(
        self, 
        workspace_id: str, 
        conversation_id: str, 
        message: dict
    ) -> bool:
        """Add a message to a conversation.
        
        Args:
            workspace_id: ID of the workspace
            conversation_id: ID of the conversation
            message: The message to add (should be a dict with question/answer)
            
        Returns:
            bool: True if the message was added successfully
        """
        result = await self.col.update_one(
            {
                "_id": ObjectId(conversation_id),
                "workspace_id": ObjectId(workspace_id)
            },
            {
                "$push": {"messages": message},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        return result.modified_count > 0
