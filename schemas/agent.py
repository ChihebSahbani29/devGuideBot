"""Pydantic models for the Agent API."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pydantic import BaseModel, Field


class AgentType(str, Enum):
    """Enumeration of supported agent types."""
    CONFLUENCE = "confluence"
    JIRA = "jira"
    GITLAB = "gitlab"
    GITHUB = "github"
    SHAREPOINT = "sharepoint"
    # Add more agent types as needed


class AgentStatus(str, Enum):
    """Status of an agent."""
    INITIALIZING = "initializing"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class AgentCapability(BaseModel):
    """Represents a capability of an agent."""
    name: str
    description: str
    parameters: Optional[Dict[str, Any]] = None


class AgentConfiguration(BaseModel):
    """Base configuration for an agent."""
    type: AgentType
    name: str
    description: str
    enabled: bool = True
    config: Dict[str, Any] = Field(default_factory=dict)
    capabilities: List[AgentCapability] | None = Field(default_factory=list)


class AgentCreateRequest(BaseModel):
    """Request model for creating a new agent."""
    type: AgentType
    name: str = Field(..., min_length=3, max_length=50)
    description: str = Field(..., min_length=10, max_length=500)
    config: Dict[str, Any] = Field(..., description="Agent-specific configuration")


class AgentUpdateRequest(BaseModel):
    """Request model for updating an agent."""
    name: Optional[str] = Field(None, min_length=3, max_length=50)
    description: Optional[str] = Field(None, min_length=10, max_length=500)
    config: Optional[Dict[str, Any]] = Field(
        None,
        description="Agent-specific configuration updates"
    )
    enabled: Optional[bool] = None


class AgentResponse(BaseModel):
    """Response model for agent data."""
    id: str
    type: AgentType
    name: str
    description: str
    status: AgentStatus
    enabled: bool
    config: Dict[str, Any]
    capabilities: List[Dict[str, Any]]
    workspace_id: str
    created_at: datetime
    updated_at: datetime
    last_active_at: Optional[datetime] = None
    error: Optional[str] = None
    data: dict[str, Any]

    class Config:
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "type": "github",
                "name": "GitHub Data Fetcher",
                "description": "Fetches repository data from GitHub",
                "status": "active",
                "enabled": True,
                "config": {
                    "access_token": "ghp_...",
                    "default_owner": "myorg",
                    "default_repo": "myrepo"
                },
                "capabilities": [
                    {
                        "name": "list_repositories",
                        "description": "List all repositories for a user or organization"
                    },
                    {
                        "name": "get_file_content",
                        "description": "Get the content of a file from a repository"
                    }
                ],
                "workspace_id": "507f1f77bcf86cd799439012",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:00:00Z",
                "last_active_at": "2023-01-01T12:00:00Z"
            }
        }


class AgentListResponse(BaseModel):
    """Response model for a list of agents."""
    agents: List[AgentResponse]


class AgentExecutionRequest(BaseModel):
    """Request model for executing an agent action."""
    action: str = Field(..., description="The action to execute")
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for the action"
    )


class AgentConnectionVerifyRequest(BaseModel):
    """Request model for verifying agent connection."""
    config: Dict[str, Any] = Field(
        ...,
        description="Agent configuration to verify. The top-level key should be the agent type (e.g., 'github', 'gitlab')."
    )


class AgentConnectionVerifyResponse(BaseModel):
    """Response model for agent connection verification."""
    success: bool
    agent_type: str
    message: str
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class AgentExecutionResponse(BaseModel):
    """Response model for agent execution results."""
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time: float
    metadata: Dict[str, Any] = Field(default_factory=dict)
