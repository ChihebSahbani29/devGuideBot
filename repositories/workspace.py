from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

class WorkspaceRepository:
    def __init__(self, collection: AsyncIOMotorCollection):
        """Initialize workspace repository with MongoDB collection.
        
        Args:
            collection: MongoDB collection instance
        """
        self.col = collection

    async def create_workspace(self, data: dict) -> str:
        res = await self.col.insert_one(data)
        return str(res.inserted_id)

    async def get_workspace(self, workspace_id: str) -> dict | None:
        return await self.col.find_one({"_id": ObjectId(workspace_id)})

    async def list_workspaces(self) -> list[dict]:
        cursor = self.col.find()
        return await cursor.to_list(length=None)
        
    async def update_workspace(self, workspace_id: str, update_data: dict) -> bool:
        if not update_data:
            return False
            
        result = await self.col.update_one(
            {"_id": ObjectId(workspace_id)},
            {"$set": update_data}
        )
        return result.modified_count > 0
        
    async def delete_workspace(self, workspace_id: str) -> bool:
        result = await self.col.delete_one({"_id": ObjectId(workspace_id)})
        return result.deleted_count > 0
