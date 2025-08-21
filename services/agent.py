"""Service layer for agent operations."""
import asyncio
import logging
import time
from typing import Dict, Any, List
from typing import Optional, Union

from config.agent_config import initialize_agent, AgentConfigError
from repositories.agent import AgentRepository
from schemas.agent import AgentType, AgentStatus, AgentCreateRequest, AgentExecutionRequest, AgentExecutionResponse, \
    AgentUpdateRequest
from schemas.document import DocumentSourceType, IngestedDocument
from services.document import DocumentService

logger = logging.getLogger(__name__)


class AgentService:
    """Service for agent-related operations."""

    def __init__(
            self,
            agent_repository: AgentRepository,
            document_service: DocumentService
    ):
        """Initialize with dependencies.
        
        Args:
            agent_repository: Repository for agent data access
            document_service: Service for document storage and retrieval
        """
        self.agent_repository = agent_repository
        self.document_service = document_service
        self.agent_instances = {}  # In-memory cache of initialized agents
        self._init_locks: Dict[str, asyncio.Lock] = {}

    async def create_agent(
            self,
            agent_data: AgentCreateRequest,
            workspace_id: str
    ) -> Dict[str, Any]:
        """Create a new agent.
        
        Args:
            agent_data: The agent creation data
            workspace_id: The ID of the workspace to create the agent in
            
        Returns:
            Dict containing the created agent data
            
        Raises:
            ValueError: If the agent type is invalid or configuration is invalid
        """
        # Validate agent type
        try:
            agent_type = AgentType(agent_data.type)
        except ValueError as e:
            raise ValueError(f"Invalid agent type: {agent_data.type}") from e

        # First validate the agent configuration by trying to initialize it
        try:
            # This will raise an exception if the configuration is invalid
            capabilities = await self._get_agent_capabilities(agent_type, agent_data.config)
        except Exception as e:
            logger.error(f"Failed to validate agent configuration: {str(e)}")
            raise ValueError(f"Invalid agent configuration: {str(e)}") from e

        # Create agent configuration (only if validation passed)
        agent_config = {
            "type": agent_type.value,
            "name": agent_data.name,
            "description": agent_data.description,
            "config": agent_data.config,
            "enabled": True,
            "capabilities": capabilities
        }
        
        # Store in database
        try:
            return await self.agent_repository.create_agent(agent_config, workspace_id)
        except Exception as e:
            logger.error(
                f"Failed to persist agent '{agent_data.name}' in workspace '{workspace_id}': {str(e)}",
                exc_info=True,
            )
            raise

    async def get_agent(self, agent_id: str, workspace_id: str) -> Optional[Dict]:
        """Retrieve an agent by ID."""
        return await self.agent_repository.get_agent_by_id(agent_id, workspace_id)

    async def list_agents(
            self,
            workspace_id: str,
            skip: int = 0,
            limit: int = 100,
            agent_type: Optional[AgentType] = None,
            enabled: Optional[bool] = None
    ) -> List[Dict]:
        """List agents with optional filtering."""
        return await self.agent_repository.list_agents(
            workspace_id=workspace_id,
            skip=skip,
            limit=limit,
            agent_type=agent_type.value if agent_type else None,
            enabled=enabled
        )

    async def update_agent(
            self,
            agent_id: str,
            workspace_id: str,
            update_data: AgentUpdateRequest
    ) -> Optional[dict]:
        """Update an agent."""
        # Get existing agent
        agent = await self.get_agent(agent_id, workspace_id)
        if not agent:
            return None

        # Prepare update data
        update_dict = update_data.model_dump(exclude_unset=True)

        # If config is being updated, refresh capabilities
        if 'config' in update_dict:
            try:
                agent_type = AgentType(agent['type'])
                update_dict['capabilities'] = await self._get_agent_capabilities(
                    agent_type,
                    update_dict['config']
                )
            except Exception as e:
                logger.error(f"Error updating agent capabilities: {e}")
                raise ValueError(f"Invalid agent configuration: {e}") from e

        # Clear cached instance if it exists
        self.agent_instances.pop(agent_id, None)

        # Update in database
        updated = await self.agent_repository.update_agent(
            workspace_id, agent_id, update_dict
        )
        if not updated:
            return None

        # Return the updated agent
        return await self.get_agent(agent_id, workspace_id)

    async def delete_agent(self, agent_id: str, workspace_id: str) -> bool:
        """Delete an agent."""
        # Clear cached instance if it exists
        self.agent_instances.pop(agent_id, None)

        # Delete from database
        return await self.agent_repository.delete_agent(agent_id, workspace_id)

    async def execute_agent(
            self,
            agent_id: str,
            workspace_id: str,
            execution_request: AgentExecutionRequest
    ) -> AgentExecutionResponse:
        """Execute an agent action.
        
        Args:
            agent_id: ID of the agent to execute
            workspace_id: ID of the workspace
            execution_request: The execution request
            
        Returns:
            AgentExecutionResponse with the result
        """
        return await self._execute_agent_internal(agent_id, workspace_id, execution_request)

    async def _execute_agent_internal(
            self,
            agent_id: str,
            workspace_id: str,
            execution_request: AgentExecutionRequest
    ) -> AgentExecutionResponse:
        """Internal method to execute an agent action."""
        start_time = time.time()

        try:
            # Get or initialize agent instance
            agent = await self._get_initialized_agent(agent_id, workspace_id)
            if not agent:
                return AgentExecutionResponse(
                    success=False,
                    error=f"Agent {agent_id} not found or initialization failed",
                    execution_time=time.time() - start_time
                )

            # Execute the action
            result = await agent.execute(
                execution_request.action,
                **execution_request.parameters
            )
            # If this was an ingestion action, process the results
            if execution_request.action == "ingest_data" and hasattr(result,
                                                                     'data') and result.data and 'documents' in result.data:
                await self._process_ingested_documents(
                    workspace_id=workspace_id,
                    agent_id=agent_id,
                    agent_type=agent.__class__.__name__,
                    documents=result.data['documents']
                )

            # Update last active time
            await self.agent_repository.update_agent_status(
                agent_id, workspace_id, AgentStatus.ACTIVE
            )

            # Handle different response formats
            is_success = result.status == AgentStatus.ACTIVE
            error = getattr(result, 'error', None)
            data = getattr(result, 'data', None)
            metadata = getattr(result, 'metadata', {})

            return AgentExecutionResponse(
                success=is_success,
                result=data,
                error=error,
                execution_time=time.time() - start_time,
                metadata=metadata
            )

        except Exception as e:
            logger.error(f"Error executing agent {agent_id}: {e}", exc_info=True)

            # Update agent status to error
            await self.agent_repository.update_agent_status(
                agent_id,
                workspace_id,
                AgentStatus.ERROR,
                error=str(e)
            )

            return AgentExecutionResponse(
                success=False,
                error=f"Agent execution failed: {str(e)}",
                execution_time=time.time() - start_time
            )

    async def _process_ingested_documents(
            self,
            workspace_id: str,
            agent_id: str,
            agent_type: str,
            documents: List[Union[Dict[str, Any], IngestedDocument]]
    ) -> Dict[str, int]:
        """Process documents ingested by an agent.
        
        Args:
            workspace_id: ID of the workspace
            agent_id: ID of the agent that ingested the documents
            agent_type: Type of the agent (e.g., 'GitHubAgent')
            documents: List of ingested documents or dictionaries
            
        Returns:
            Dict with counts of processed documents
        """
        if not documents:
            return {"processed": 0, "errors": 0}

        # Convert dictionaries to IngestedDocument objects if needed
        ingested_docs = []
        for doc in documents:
            try:
                if isinstance(doc, IngestedDocument):
                    ingested_docs.append(doc)
                elif isinstance(doc, dict):
                    # Ensure the document has the required fields
                    if all(k in doc for k in ["id", "title", "content", "source_id"]):
                        # Add agent metadata if not present
                        if "metadata" not in doc:
                            doc["metadata"] = {}

                        doc["metadata"]["agent_id"] = agent_id
                        doc["metadata"]["agent_type"] = agent_type

                        # Convert to IngestedDocument
                        ingested_docs.append(IngestedDocument(**doc))
            except Exception as e:
                logger.error(f"Error processing document: {e}")
                continue

        if not ingested_docs:
            return {"processed": 0, "errors": len(documents)}

        # Determine the source type from the agent type
        source_type = self._map_agent_type_to_source_type(agent_type)

        # Use the first document's source_id as the source_id
        source_id = ingested_docs[0].source_id

        # Store the documents using the document service
        result = await self.document_service.ingest_documents(
            documents=ingested_docs,
            workspace_id=workspace_id,
            source_type=source_type,
            source_id=source_id
        )

        return {
            "processed": result.get("inserted", 0) + result.get("updated", 0),
            "inserted": result.get("inserted", 0),
            "updated": result.get("updated", 0),
            "errors": len(documents) - (result.get("inserted", 0) + result.get("updated", 0))
        }

    def _map_agent_type_to_source_type(self, agent_type: str) -> DocumentSourceType:
        """Map an agent type to a document source type."""
        agent_type_lower = agent_type.lower()

        if "github" in agent_type_lower:
            return DocumentSourceType.GITHUB
        elif "gitlab" in agent_type_lower:
            return DocumentSourceType.GITLAB
        elif "confluence" in agent_type_lower:
            return DocumentSourceType.CONFLUENCE
        elif "jira" in agent_type_lower:
            return DocumentSourceType.JIRA
        elif "sharepoint" in agent_type_lower:
            return DocumentSourceType.SHAREPOINT
        else:
            return DocumentSourceType.OTHER

    async def verify_connection(self, agent_id: str, workspace_id: str) -> bool:
        """Verify the connection to the agent's data source.
        
        Args:
            agent_id: ID of the agent to verify
            workspace_id: ID of the workspace the agent belongs to
            
        Returns:
            bool: True if connection is successful, False otherwise
            
        Raises:
            ValueError: If agent is not found or connection fails
        """
        try:
            agent = await self._get_initialized_agent(agent_id, workspace_id)
            if not agent:
                raise ValueError(f"Agent {agent_id} not found or disabled")

            # Verify connection using the agent's verify_connection method
            result = await agent.verify_connection()

            # Update agent status based on verification result
            is_success = result.status == AgentStatus.ACTIVE
            await self.agent_repository.update_agent_status(
                agent_id,
                workspace_id,
                result.status,
                error=None if is_success else result.error
            )

            if not is_success:
                raise ValueError(f"Connection verification failed: {result.error}")

            return True

        except Exception as e:
            logger.error(f"Connection verification failed for agent {agent_id}: {str(e)}")
            await self.agent_repository.update_agent_status(
                agent_id,
                workspace_id,
                AgentStatus.ERROR,
                error=str(e)
            )
            raise

    async def execute_agent_action(
            self,
            agent_id: str,
            workspace_id: str,
            action: str,
            parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a specific action on an agent.
        
        Args:
            agent_id: ID of the agent to execute the action on
            workspace_id: ID of the workspace the agent belongs to
            action: Name of the action to execute
            parameters: Optional parameters for the action
            
        Returns:
            Dict containing the result of the action
        """
        execution_request = AgentExecutionRequest(
            action=action,
            parameters=parameters or {}
        )

        result = await self.execute_agent(agent_id, workspace_id, execution_request)
        return {
            "success": result.success,
            "result": result.result,
            "error": result.error,
            "metadata": result.metadata or {}
        }

    async def _get_initialized_agent(self, agent_id: str, workspace_id: str) -> Any:
        """Get or initialize an agent instance."""
        # Check if agent is already initialized
        if agent_id in self.agent_instances:
            return self.agent_instances[agent_id]

        lock = self._init_locks.setdefault(agent_id, asyncio.Lock())
        async with lock:
            if agent_id in self.agent_instances:
                return self.agent_instances[agent_id]

            # Get configuration
            agent_config = await self.agent_repository.get_agent_by_id(agent_id, workspace_id)
            if not agent_config or not agent_config.get('enabled'):
                logger.warning(f"Agent {agent_id} in workspace {workspace_id} is disabled or missing config.")
                return None

            try:
                await self.agent_repository.update_agent_status(
                    agent_id, workspace_id, AgentStatus.INITIALIZING
                )

                agent = await initialize_agent(
                    agent_config['type'],
                    config_override=agent_config.get('config', {})
                )

                self.agent_instances[agent_id] = agent

                await self.agent_repository.update_agent_status(
                    agent_id, workspace_id, AgentStatus.ACTIVE
                )
                return agent

            except AgentConfigError as e:
                logger.error(f"Configuration error for agent {agent_id}: {e}")
            except Exception as e:
                logger.exception(f"Unexpected error initializing agent {agent_id}")
            finally:
                if agent_id not in self.agent_instances:
                    await self.agent_repository.update_agent_status(
                        agent_id, workspace_id, AgentStatus.ERROR, error=str(e)
                    )
                self._init_locks.pop(agent_id, None)

            return None

    @staticmethod
    async def _get_agent_capabilities(
            agent_type: AgentType,
            config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Get capabilities for an agent type and configuration."""
        logger.info(f"Getting capabilities for agent type: {agent_type.value}")
        logger.info(f"Agent config: {config}")

        try:
            # Use initialize_agent which properly handles async initialization
            logger.info(f"Initializing agent of type: {agent_type.value}")
            agent = await initialize_agent(agent_type.value, config_override=config)
            logger.info(f"Agent initialized: {agent}")

            if hasattr(agent, 'get_capabilities') and callable(agent.get_capabilities):
                logger.info(f"Getting capabilities for agent: {agent_type.value}")
                result = await agent.get_capabilities()
                logger.info(f"Raw capabilities result: {result}")
                logger.info(f"Result type: {type(result)}")
                if hasattr(result, '__dict__'):
                    logger.info(f"Result attributes: {result.__dict__}")
                if hasattr(result, 'data'):
                    logger.info(f"Result data: {result.data}")
                    if hasattr(result.data, '__dict__'):
                        logger.info(f"Result data attributes: {result.data.__dict__}")
                if hasattr(result, 'data') and hasattr(result.data, 'get') and 'capabilities' in result.data:
                    capabilities = []
                    for cap in result.data['capabilities']:
                        if isinstance(cap, str):
                            # Handle string format "action: description"
                            if ': ' in cap:
                                name, description = cap.split(': ', 1)
                                capabilities.append({"name": name.strip(), "description": description.strip()})
                            else:
                                capabilities.append({"name": cap, "description": ""})
                        elif hasattr(cap, 'name') and hasattr(cap, 'description'):
                            # Handle object with name and description attributes
                            capabilities.append({"name": cap.name, "description": cap.description})
                        elif isinstance(cap, dict):
                            # Handle dictionary format
                            capabilities.append({
                                "name": cap.get('name', ''),
                                "description": cap.get('description', '')
                            })
                    return capabilities
                elif hasattr(result, 'capabilities'):
                    # Handle case where capabilities are directly in the result
                    return [
                        {"name": getattr(cap, 'name', 'unknown'),
                         "description": getattr(cap, 'description', 'No description available')}
                        for cap in result.capabilities
                    ]
        except Exception as e:
            logger.warning(f"Could not get capabilities for agent {agent_type}: {e}", exc_info=True)

        # Return default capabilities if we couldn't determine them
        return []
