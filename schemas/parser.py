"""Schemas for parser testing and configuration."""
from typing import Dict, List, Literal, Optional, Any
from pydantic import BaseModel, Field


class ParserTestRequest(BaseModel):
    """Request model for testing parsers and chunkers."""
    content: str = Field(..., description="The content to parse and chunk")
    content_type: str = Field(..., description="MIME type or file extension of the content")
    parser_type: Optional[str] = Field(
        None,
        description="Specific parser type to use (e.g., 'python', 'markdown'). If not provided, will auto-detect."
    )
    chunker_type: Optional[str] = Field(
        None,
        description="Specific chunker type to use (e.g., 'code', 'text'). If not provided, will auto-detect."
    )
    chunk_size: int = Field(
        1000,
        description="Maximum size of each chunk in characters",
        gt=0,
        le=10000
    )
    chunk_overlap: int = Field(
        100,
        description="Number of characters to overlap between chunks",
        ge=0,
        le=1000
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional metadata to include with the parsed content"
    )


class ChunkResult(BaseModel):
    """Result of a single chunk of parsed content."""
    content: str = Field(..., description="The chunked content")
    metadata: Dict[str, Any] = Field(..., description="Metadata associated with the chunk")
    type: str = Field(..., description="Type of the chunk (e.g., 'code', 'text', 'heading')")
    token_count: Optional[int] = Field(None, description="Number of tokens in the chunk")


class ParserTestResult(BaseModel):
    """Result of a parser test."""
    content_type: str = Field(..., description="Detected content type")
    parser_used: str = Field(..., description="Parser that was used")
    chunker_used: str = Field(..., description="Chunker that was used")
    chunks: List[ChunkResult] = Field(..., description="List of chunks produced")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the parsing process"
    )
    stats: Dict[str, Any] = Field(
        default_factory=dict,
        description="Statistics about the parsing process"
    )
