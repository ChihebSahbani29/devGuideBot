from abc import ABC, abstractmethod
from typing import Any, Dict

from schemas.agent import AgentResponse
from schemas.document import DocumentSourceType


class BaseAgent(ABC):
    """Abstract base class for all MCP agents.
    
    This class defines the interface that all agent implementations must follow.
    """

    def __init__(self, name: str, description: str, config: Dict[str, Any]):
        """Initialize the base agent with common attributes.
        
        Args:
            name: Name of the agent
            description: Description of the agent's purpose
            config: Configuration dictionary for the agent
        """
        self.name = name
        self.description = description
        self.config = config
        self.initialized = False
        self.source_type: DocumentSourceType

    @abstractmethod
    async def initialize(self) -> AgentResponse:
        """Initialize the agent and any required connections.
        
        Returns:
            AgentResponse: The result of the initialization
        """
        pass

    @abstractmethod
    async def execute(self, action: str, **kwargs) -> AgentResponse:
        """Execute an action with the agent.
        
        Args:
            action: The action to execute (e.g., 'ingest_data', 'search')
            **kwargs: Action-specific parameters
            
        Returns:
            AgentResponse: The result of the action
        """
        pass

    @abstractmethod
    async def get_capabilities(self) -> AgentResponse:
        """Return the capabilities of this agent.
        
        Returns:
            AgentResponse: Contains the agent's capabilities
        """
        pass

    @abstractmethod
    async def verify_connection(self) -> AgentResponse:
        """Verify the connection to the data source.
        
        Returns:
            AgentResponse: success=True if connection is valid
        """
        pass

    @abstractmethod
    async def health_check(self) -> AgentResponse:
        """Check the health of the agent and its connection.
        
        Returns:
            AgentResponse: The health status of the agent
        """
        pass

    @abstractmethod
    async def ingest_data(self, **kwargs) -> AgentResponse:
        """Ingest data from the data source.
        
        Returns:
            AgentResponse: Contains list of IngestedDocument in the data field
        """
        pass
