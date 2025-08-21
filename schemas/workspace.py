from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, HttpUrl

class JiraConfig(BaseModel):
    """Jira configuration model."""
    url: HttpUrl
    email: str
    api_token: str
    project_key: str

class ConfluenceConfig(BaseModel):
    """Confluence configuration model."""
    url: HttpUrl
    email: str
    api_token: str
    space_key: str

class SharePointConfig(BaseModel):
    """SharePoint configuration model."""
    site_url: HttpUrl
    client_id: str
    client_secret: str
    tenant_id: str

class GitConfig(BaseModel):
    """Base Git configuration model (for GitHub/GitLab)."""
    url: HttpUrl
    access_token: str
    default_owner: str = Field(..., description="The owner/username of the repository")
    default_repo: str = Field(..., description="The name of the repository")

class WorkspaceCreateRequest(BaseModel):
    """Request model for creating a new workspace."""
    name: str = Field(..., json_schema_extra={"example": "Data Governance Workspace"})
    description: str | None = Field(None, json_schema_extra={"example": "Used for RAG experiments"})
    jira: Optional[JiraConfig] = None
    confluence: Optional[ConfluenceConfig] = None
    sharepoint: Optional[SharePointConfig] = None
    github: Optional[GitConfig] = None
    gitlab: Optional[GitConfig] = None

class WorkspaceResponse(BaseModel):
    """Response model for workspace data."""
    id: str
    name: str
    description: str | None
    jira: Optional[Dict[str, Any]] = None
    confluence: Optional[Dict[str, Any]] = None
    sharepoint: Optional[Dict[str, Any]] = None
    github: Optional[Dict[str, Any]] = None
    gitlab: Optional[Dict[str, Any]] = None

class WorkspaceUpdateRequest(BaseModel):
    """Request model for updating a workspace."""
    name: str | None = Field(None, json_schema_extra={"example": "Updated Workspace Name"})
    description: str | None = Field(None, json_schema_extra={"example": "Updated description"})
    jira: Optional[JiraConfig] | None = Field(None, description="Set to null to remove Jira config")
    confluence: Optional[ConfluenceConfig] | None = Field(None, description="Set to null to remove Confluence config")
    sharepoint: Optional[SharePointConfig] | None = Field(None, description="Set to null to remove SharePoint config")
    github: Optional[GitConfig] | None = Field(None, description="Set to null to remove GitHub config")
    gitlab: Optional[GitConfig] | None = Field(None, description="Set to null to remove GitLab config")

class WorkspaceListResponse(BaseModel):
    workspaces: list[WorkspaceResponse]
