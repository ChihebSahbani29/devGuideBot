"""Repository for agent data access."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from schemas.agent import AgentStatus


class AgentRepository:
    """Repository for agent data access operations."""

    def __init__(self, collection: AsyncIOMotorCollection):
        """Initialize with MongoDB collection.
        
        Args:
            collection: MongoDB collection instance for agents
        """
        self.col = collection

    async def create_agent(
            self,
            agent_data: Dict,
            workspace_id: str
    ) -> Dict[str, Any] | None:
        """Create a new agent.
        
        Args:
            agent_data: Dictionary containing agent data
            workspace_id: ID of the workspace this agent belongs to
            
        Returns:
            Dict[str, Any]: The created agent document
        """
        now = datetime.utcnow()

        # Create a new document with the agent data
        agent_doc = {
            **agent_data,
            "workspace_id": ObjectId(workspace_id),
            "status": AgentStatus.ACTIVE.value,
            "created_at": now,
            "updated_at": now,
            "last_active_at": None,
            "data": {"message": "agent created successfully"}
        }

        # Insert the document
        result = await self.col.insert_one(agent_doc)

        # Retrieve the created document
        created_agent = await self.col.find_one({"_id": result.inserted_id})

        # Convert ObjectId to string for the response and map _id to id
        if created_agent:
            # Create a new dict with the correct field names
            result = {k: v for k, v in created_agent.items() if k != '_id'}
            result["id"] = str(created_agent["_id"])
            result["workspace_id"] = str(result["workspace_id"])
            # Ensure all datetime objects are timezone-aware
            if 'created_at' in result and result['created_at']:
                result['created_at'] = now
            if 'updated_at' in result and result['updated_at']:
                result['updated_at'] = now
            if 'last_active_at' in result and result['last_active_at']:
                result['last_active_at'] = now
            return result

        return None

    async def get_agent(self, workspace_id: str, agent_id: str) -> Optional[Dict]:
        """Get a specific agent from a workspace.
        
        Args:
            workspace_id: ID of the workspace
            agent_id: ID of the agent to retrieve
            
        Returns:
            Optional[Dict]: The agent data or None if not found
        """
        try:
            agent = await self.col.find_one({
                "_id": ObjectId(agent_id),
                "workspace_id": ObjectId(workspace_id)
            })

            if agent:
                # Create a new dict with the correct field names
                result = {k: v for k, v in agent.items() if k != '_id'}
                result["id"] = str(agent["_id"])
                result["workspace_id"] = str(result["workspace_id"])

                # Ensure all datetime objects are timezone-aware
                if 'created_at' in result and result['created_at'] and not result['created_at'].tzinfo:
                    result['created_at'] = result['created_at'].replace(tzinfo=datetime.timezone.utc)
                if 'updated_at' in result and result['updated_at'] and not result['updated_at'].tzinfo:
                    result['updated_at'] = result['updated_at'].replace(tzinfo=datetime.timezone.utc)
                if 'last_active_at' in result and result['last_active_at'] and not result['last_active_at'].tzinfo:
                    result['last_active_at'] = result['last_active_at'].replace(tzinfo=datetime.timezone.utc)

                result.setdefault("data", {})  # Ensure data field exists
                return result
            return None
        except Exception as e:
            logger.error(f"Error getting agent {agent_id}: {str(e)}")
            return None

    async def list_agents(
            self,
            workspace_id: str,
            skip: int = 0,
            limit: int = 100,
            agent_type: Optional[str] = None,
            enabled: Optional[bool] = None
    ) -> List[Dict]:
        """List all agents in a workspace with optional filtering and pagination.
        
        Args:
            workspace_id: ID of the workspace
            skip: Number of documents to skip (for pagination)
            limit: Maximum number of documents to return
            agent_type: Optional filter by agent type as string (e.g., 'github', 'gitlab')
            enabled: Optional filter by enabled status
            
        Returns:
            List[Dict]: List of agents, or empty list if none found
            
        Raises:
            ValueError: If workspace_id is invalid
        """
        try:
            query = {"workspace_id": ObjectId(workspace_id)}

            # Add optional filters
            if agent_type:
                query["type"] = agent_type
            if enabled is not None:
                query["enabled"] = enabled

            cursor = self.col.find(query).skip(skip).limit(limit)
            agents = []

            async for agent in cursor:
                # Create a new dict with the correct field names
                result = {k: v for k, v in agent.items() if k != '_id'}
                result["id"] = str(agent["_id"])
                result["workspace_id"] = str(result["workspace_id"])

                # Ensure all datetime objects are timezone-aware
                if 'created_at' in result and result['created_at'] and not result['created_at'].tzinfo:
                    result['created_at'] = result['created_at'].replace(tzinfo=datetime.timezone.utc)
                if 'updated_at' in result and result['updated_at'] and not result['updated_at'].tzinfo:
                    result['updated_at'] = result['updated_at'].replace(tzinfo=datetime.timezone.utc)
                if 'last_active_at' in result and result['last_active_at'] and not result['last_active_at'].tzinfo:
                    result['last_active_at'] = result['last_active_at'].replace(tzinfo=datetime.timezone.utc)

                result.setdefault("data", {})  # Ensure data field exists
                agents.append(result)

            return agents

        except Exception as e:
            logger.error(f"Error listing agents for workspace {workspace_id}: {str(e)}")
            return []
            raise ValueError(error_msg) from e

    async def update_agent(
            self,
            workspace_id: str,
            agent_id: str,
            update_data: Dict
    ) -> bool:
        """Update an agent's data.
        
        Args:
            workspace_id: ID of the workspace
            agent_id: ID of the agent to update
            update_data: Dictionary of fields to update
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        if not update_data:
            return False

        update_data['updated_at'] = datetime.utcnow()

        result = await self.col.update_one(
            {
                "_id": ObjectId(agent_id),
                "workspace_id": ObjectId(workspace_id)
            },
            {"$set": update_data}
        )

        return result.modified_count > 0

    async def delete_agent(self, workspace_id: str, agent_id: str) -> bool:
        """Delete an agent.
        
        Args:
            workspace_id: ID of the workspace
            agent_id: ID of the agent to delete
            
        Returns:
            bool: True if deletion was successful, False otherwise
        """
        result = await self.col.delete_one({
            "_id": ObjectId(agent_id),
            "workspace_id": ObjectId(workspace_id)
        })

        return result.deleted_count > 0

    async def get_agent_by_id(self, agent_id: str, workspace_id: str) -> Optional[Dict]:
        """Retrieve an agent by ID."""
        agent = await self.col.find_one(
            {"_id": ObjectId(agent_id), "workspace_id": ObjectId(workspace_id)}
        )
        return self._convert_object_id(agent) if agent else None

    async def update_agent_status(
            self,
            agent_id: str,
            workspace_id: str,
            status: AgentStatus,
            error: Optional[str] = None
    ) -> bool:
        """Update agent status and optionally set an error message."""
        update_data = {
            "status": status.value,
            "updated_at": datetime.utcnow(),
        }

        if status == AgentStatus.ACTIVE:
            update_data["last_active_at"] = datetime.utcnow()
        if error:
            update_data["error"] = error

        result = await self.col.update_one(
            {"_id": ObjectId(agent_id), "workspace_id": ObjectId(workspace_id)},
            {"$set": update_data},
        )
        return result.modified_count > 0

    @staticmethod
    def _convert_object_id(agent: Dict) -> Dict:
        """Convert MongoDB ObjectId to string."""
        if agent and "_id" in agent:
            agent["id"] = str(agent.pop("_id"))
        if agent and "workspace_id" in agent:
            agent["workspace_id"] = str(agent.pop("workspace_id"))
        return agent
