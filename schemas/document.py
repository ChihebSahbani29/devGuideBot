from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field, HttpUrl


class DocumentSourceType(str, Enum):
    """Enum for document source types."""
    GITHUB = "github"
    GITLAB = "gitlab"
    CONFLUENCE = "confluence"
    JIRA = "jira"
    SHAREPOINT = "sharepoint"
    OTHER = "other"


class IngestedDocument(BaseModel):
    """Represents a document ingested from a data source"""
    id: str
    source_id: str
    source_type: DocumentSourceType
    title: str
    content: str
    url: Optional[HttpUrl] = None
    metadata: Dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime


class DocumentBase(BaseModel):
    """Base model for document data."""
    title: str = Field(..., description="Title of the document")
    content: str = Field(..., description="Content of the document")
    source_type: DocumentSourceType = Field(..., description="Type of the data source")
    source_id: str = Field(..., description="ID of the source (e.g., repository ID, space key)")
    source_url: Optional[HttpUrl] = Field(None, description="URL of the source document")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata about the document")


class DocumentCreate(DocumentBase):
    """Schema for creating a new document."""
    pass


class DocumentUpdate(BaseModel):
    """Schema for updating an existing document."""
    title: Optional[str] = None
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class DocumentInDBBase(DocumentBase):
    """Base schema for document in database."""
    id: str = Field(..., alias="_id")
    workspace_id: str = Field(..., description="ID of the workspace this document belongs to")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "json_encoders": {"datetime": lambda v: v.isoformat()}
    }


class Document(DocumentInDBBase):
    """Schema for returning document data."""
    pass


class DocumentList(BaseModel):
    """Schema for a list of documents with pagination info."""
    items: List[Document]
    total: int
    skip: int
    limit: int


class DocumentSearchQuery(BaseModel):
    """Schema for document search query."""
    query: str = Field(..., description="Search query string")
    source_types: Optional[List[DocumentSourceType]] = Field(None, description="Filter by source types")
    source_ids: Optional[List[str]] = Field(None, description="Filter by source IDs")
    workspace_id: Optional[str] = Field(None, description="Filter by workspace ID")
    skip: int = Field(0, ge=0, description="Number of items to skip")
    limit: int = Field(20, ge=1, le=100, description="Maximum number of items to return")


class DocumentReference(BaseModel):
    """Reference to a document used in the chat response."""
    document_id: str
    source: str
    title: Optional[str] = None
    url: Optional[str] = None
    content: Optional[str] = None
    similarity_score: Optional[float] = None
