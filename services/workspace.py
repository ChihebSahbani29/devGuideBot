import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import HTTPException, status

from config.agent_config import initialize_agent
from repositories.workspace import WorkspaceRepository
from schemas.agent import AgentStatus
from schemas.agent import AgentType, AgentCreateRequest
from schemas.workspace import JiraConfig, ConfluenceConfig, SharePointConfig, GitConfig
from services.agent import AgentService

logger = logging.getLogger(__name__)


class WorkspaceService:
    def __init__(self, repo: WorkspaceRepository, agent_service: AgentService):
        self.repo = repo
        self.agent_service = agent_service

    def _convert_urls_to_strings(self, data: Any) -> Any:
        """Recursively convert URL objects to strings in a dictionary, list, or other nested structure.

        Args:
            data: The data to process (dict, list, or any other type)

        Returns:
            The processed data with URL objects converted to strings
        """
        # Handle Pydantic's HttpUrl type and other URL-like objects
        if hasattr(data, '__str__') and not isinstance(data, (str, int, float, bool, type(None))):
            if hasattr(data, '__class__') and 'Url' in data.__class__.__name__:
                return str(data)
            if hasattr(data, 'model_dump'):
                return self._convert_urls_to_strings(data.model_dump())
            return str(data)
            
        if isinstance(data, dict):
            return {
                k: self._convert_urls_to_strings(v)
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [self._convert_urls_to_strings(item) for item in data]
            
        return data

    async def _create_agent_for_source(
            self,
            workspace_id: str,
            source_type: str,
            config: Dict[str, Any],
            agent_type: AgentType
    ) -> Optional[Dict[str, Any]]:
        """Helper method to create and verify an agent for a data source.
        
        Args:
            workspace_id: ID of the workspace
            source_type: Type of the data source (e.g., 'github', 'gitlab')
            config: Configuration for the data source
            agent_type: Type of agent to create
            
        Returns:
            Dict containing agent details if successful, None otherwise
            
        Raises:
            HTTPException: If agent creation or verification fails
        """
        try:
            # Validate required configuration based on source type
            if source_type in ['github', 'gitlab']:
                if not config.get('access_token'):
                    raise ValueError(f"{source_type} configuration is missing required 'access_token'")
                if not (config.get('default_owner') and config.get('default_repo')):
                    raise ValueError(
                        f"{source_type} configuration is missing required 'default_owner' and/or 'default_repo'")
            elif source_type == 'sharepoint':
                required_fields = ['client_id', 'client_secret', 'tenant_id', 'site_url']
                missing_fields = [field for field in required_fields if not config.get(field)]
                if missing_fields:
                    raise ValueError(
                        f"SharePoint configuration is missing required fields: {', '.join(missing_fields)}")

            # Convert any URL objects to strings in the config
            processed_config = self._convert_urls_to_strings(config)

            # Create agent data
            agent_data = AgentCreateRequest(
                type=agent_type,
                name=f"{source_type.title()} Agent - {workspace_id[:8]}",
                description=f"Automatically created agent for {source_type} in workspace {workspace_id}",
                config=processed_config
            )

            # Create the agent
            agent = await self.agent_service.create_agent(agent_data, workspace_id)

            # Ensure the agent is properly activated in the database
            await self.agent_service.agent_repository.update_agent_status(
                agent_id=agent['id'],
                workspace_id=workspace_id,
                status=AgentStatus.ACTIVE,
                error=None
            )

            # Verify connection to the data source
            try:
                verify_result = await self.agent_service.verify_connection(agent['id'], workspace_id)
                if not verify_result:
                    logger.error(f"{source_type} connection verification failed")
                    # Clean up the agent if verification fails
                    await self.agent_service.delete_agent(agent['id'], workspace_id)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to verify {source_type} connection"
                    )
            except Exception as e:
                logger.error(f"Error during {source_type} connection verification: {str(e)}", exc_info=True)
                # Clean up the agent if verification fails with an exception
                await self.agent_service.delete_agent(agent['id'], workspace_id)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error during {source_type} connection verification: {str(e)}"
                )

            logger.info(f"Successfully created and verified {source_type} agent {agent['id']}")
            return agent

        except HTTPException:
            raise  # Re-raise HTTP exceptions

        except Exception as e:
            logger.error(f"Failed to create/verify {source_type} agent: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to set up {source_type} integration: {str(e)}"
            ) from e

    async def _ingest_data_source(
            self,
            workspace_id: str,
            agent_id: str,
            source_type: str
    ) -> Dict[str, Any]:
        """Fetch, parse and ingest data from a data source.
        
        This method is called after successful workspace creation to asynchronously
        fetch data from the data source, parse it, and store it in MongoDB and Redis.
        
        Args:
            workspace_id: ID of the workspace
            agent_id: ID of the agent to use for ingestion
            source_type: Type of the data source (e.g., 'github', 'gitlab')
            
        Returns:
            Dict with 'success' status and optional 'error' message
        """
        try:
            logger.info(f"Starting data ingestion for {source_type} in workspace {workspace_id}")

            # Execute the agent's data ingestion
            result = await self.agent_service.execute_agent_action(
                agent_id=agent_id,
                workspace_id=workspace_id,
                action="ingest_data",
                parameters={
                    "source_type": source_type,
                    "workspace_id": workspace_id
                }
            )

            if not result.get('success'):
                error_msg = f"Failed to ingest data from {source_type}: {result.get('error')}"
                logger.error(error_msg)
                # Consider notifying admin of the failure
                return {"success": False, "error": error_msg}

            # Log successful ingestion
            stats = result.get('metadata', {})
            logger.info(
                f"Successfully ingested {source_type} data for workspace {workspace_id}. "
                f"Processed: {stats.get('processed', 0)}, "
                f"Inserted: {stats.get('inserted', 0)}, "
                f"Updated: {stats.get('updated', 0)}, "
                f"Errors: {stats.get('errors', 0)}"
            )

            return {
                "success": True,
                "stats": stats
            }

        except Exception as e:
            error_msg = f"Error in data ingestion for {source_type}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            # Consider notifying admin of the error
            return {"success": False, "error": error_msg}

    async def create_workspace(
            self,
            name: str,
            description: Optional[str] = None,
            jira: Optional[JiraConfig] = None,
            confluence: Optional[ConfluenceConfig] = None,
            sharepoint: Optional[SharePointConfig] = None,
            github: Optional[GitConfig] = None,
            gitlab: Optional[GitConfig] = None
    ) -> str:
        """Create a new workspace with optional data source configurations.
        
        This method creates a new workspace and sets up agents for each provided
        data source. For each data source, it will:
        1. Create an agent
        2. Verify the connection
        3. Asynchronously start data ingestion
        
        Args:
            name: Name of the workspace
            description: Optional description of the workspace
            jira: Optional Jira configuration
            confluence: Optional Confluence configuration
            sharepoint: Optional SharePoint configuration
            github: Optional GitHub configuration
            gitlab: Optional GitLab configuration
            
        Returns:
            str: ID of the created workspace
            
        Raises:
            HTTPException: If workspace creation or agent setup fails
        """
        try:
            # Create workspace with initial data including configurations
            workspace_data = {
                "name": name,
                "description": description,
                "status": "initializing",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }

            # Add configurations with URL objects converted to strings
            configs = {
                'jira': jira,
                'confluence': confluence,
                'sharepoint': sharepoint,
                'github': github,
                'gitlab': gitlab
            }

            for key, config in configs.items():
                if config is not None:
                    config_dict = config.model_dump()
                    workspace_data[key] = self._convert_urls_to_strings(config_dict)

            # Create workspace in the database
            workspace_id = await self.repo.create_workspace(workspace_data)

            # Create and verify agents for each data source
            agents = {}

            # Process GitHub if provided
            if github:
                github_config = github.model_dump()
                github_agent = await self._create_agent_for_source(
                    workspace_id=workspace_id,
                    source_type="github",
                    config=github_config,
                    agent_type=AgentType.GITHUB
                )
                if github_agent:
                    agents['github'] = {
                        'id': github_agent['id'],
                        'name': github_agent['name'],
                        'status': 'active'
                    }

            # Process GitLab if provided
            if gitlab:
                gitlab_config = gitlab.model_dump()
                gitlab_agent = await self._create_agent_for_source(
                    workspace_id=workspace_id,
                    source_type="gitlab",
                    config=gitlab_config,
                    agent_type=AgentType.GITLAB
                )
                if gitlab_agent:
                    agents['gitlab'] = {
                        'id': gitlab_agent['id'],
                        'name': gitlab_agent['name'],
                        'status': 'active'
                    }

            # Process SharePoint if provided
            if sharepoint:
                sharepoint_config = sharepoint.model_dump()
                sharepoint_agent = await self._create_agent_for_source(
                    workspace_id=workspace_id,
                    source_type="sharepoint",
                    config=sharepoint_config,
                    agent_type=AgentType.SHAREPOINT
                )
                if sharepoint_agent:
                    agents['sharepoint'] = {
                        'id': sharepoint_agent['id'],
                        'name': sharepoint_agent['name'],
                        'status': 'active'
                    }

            # Update workspace with agent references and mark as active
            await self.repo.update_workspace(workspace_id, {
                "agents": agents,
                "status": "active"
            })

            # Start background tasks for data ingestion
            for source_type, agent_info in agents.items():
                asyncio.create_task(
                    self._ingest_data_source(
                        workspace_id=workspace_id,
                        agent_id=agent_info['id'],
                        source_type=source_type
                    )
                )

            logger.info(f"Successfully created workspace {workspace_id} with {len(agents)} data sources")
            return workspace_id

        except Exception as e:
            # Cleanup in case of error
            logger.error(f"Error creating workspace: {str(e)}", exc_info=True)
            if 'workspace_id' in locals():
                # Mark workspace as failed
                await self.repo.update_workspace(workspace_id, {
                    "status": "error",
                    "error": str(e)
                })
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create workspace: {str(e)}"
            ) from e

    async def list_workspaces(self) -> list[dict]:
        """List all workspaces with their configurations."""
        workspaces = await self.repo.list_workspaces()
        return [self._format_workspace_response(ws) for ws in workspaces]

    async def get_workspace(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        """Get a workspace by ID with its configurations."""
        workspace = await self.repo.get_workspace(workspace_id)
        if workspace:
            return self._format_workspace_response(workspace)
        return None

    async def update_workspace(
            self,
            workspace_id: str,
            update_data: Dict[str, Any]
    ) -> bool:
        """Update workspace fields including data source configurations.
        
        Args:
            workspace_id: ID of the workspace to update
            update_data: Dictionary with fields to update. For data sources, 
                        set to None to remove the configuration.
                        
        Returns:
            bool: True if update was successful, False otherwise
        """
        # Create a copy to avoid modifying the input dictionary
        processed_data = update_data.copy()

        # Convert any URL objects to strings in the processed data
        processed_data = self._convert_urls_to_strings(processed_data)

        if not processed_data:
            return False

        return await self.repo.update_workspace(workspace_id, processed_data)

    def _format_workspace_response(self, workspace: Dict[str, Any]) -> Dict[str, Any]:
        """Format workspace data for response, ensuring consistent output format."""
        # Convert MongoDB _id to id
        if '_id' in workspace:
            workspace['id'] = str(workspace.pop('_id'))
        return workspace

    async def delete_workspace(self, workspace_id: str) -> bool:
        """Delete a workspace by ID."""
        return await self.repo.delete_workspace(workspace_id)
