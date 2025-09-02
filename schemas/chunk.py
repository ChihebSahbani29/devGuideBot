from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, HttpUrl
from bson import ObjectId

class ChunkBase(BaseModel):
    """Base model for chunk data."""
    document_id: str = Field(..., description="Reference to the parent document")
    workspace_id: str = Field(..., description="ID of the workspace")
    content: str = Field(..., description="The chunk content")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the chunk"
    )
    token_count: Optional[int] = Field(
        None,
        description="Number of tokens in the chunk"
    )
    vector_embedding: Optional[list[float]] = Field(
        None,
        description="Vector embedding of the chunk"
    )

class ChunkCreate(ChunkBase):
    """Schema for creating a new chunk."""
    pass

class ChunkInDB(ChunkBase):
    """Schema for chunk data in database."""
    id: str = Field(..., alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {
            "datetime": lambda v: v.isoformat(),
            ObjectId: str
        }

class ChunkUpdate(BaseModel):
    """Schema for updating a chunk."""
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    token_count: Optional[int] = None
    vector_embedding: Optional[list[float]] = None

class ChunkList(BaseModel):
    """Schema for a list of chunks with pagination info."""
    items: list[ChunkInDB]
    total: int
    skip: int
    limit: int
