"""Chat-related schemas."""
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field

from schemas.document import DocumentSourceType, DocumentReference


class ChatMessage(BaseModel):
    """A message in a chat conversation."""
    role: str = Field(..., description="The role of the message sender (user, assistant, system)")
    content: str = Field(..., description="The content of the message")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional metadata for the message"
    )


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str = Field(
        ...,
        description="The user's message content"
    )
    source_types: Optional[List[DocumentSourceType]] = Field(
        None,
        description="List of source types to filter documents by (e.g., ['github', 'confluence'])"
    )
    source_ids: Optional[List[str]] = Field(
        None,
        description="List of source IDs to filter documents by"
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of relevant documents to include in the context"
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for the response generation"
    )
    max_tokens: int = Field(
        default=1000,
        ge=1,
        le=4096,
        description="Maximum number of tokens to generate in the response"
    )
    stream: bool = Field(
        default=False,
        description="Whether to stream the response as it's generated"
    )
    system_prompt: Optional[str] = Field(
        None,
        description="Optional system prompt to set the assistant's behavior"
    )


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    response: str = Field(..., description="The generated response from the assistant")
    conversation_id: Optional[str] = Field(
        None,
        description="ID of the conversation, if a new one was created"
    )
    documents: List[DocumentReference] = Field(
        default_factory=list,
        description="List of documents used to generate the response"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the response"
    )


class ChatStreamChunk(BaseModel):
    """A chunk of a streaming chat response."""
    content: str = Field(..., description="The content chunk")
    done: bool = Field(default=False, description="Whether this is the last chunk")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the chunk"
    )


class TestChatRequest(BaseModel):
    """Request model for test chat endpoint."""
    message: str = Field(..., description="The message to send to the chat agent")
    system_prompt: Optional[str] = Field(
        None,
        description="Optional system prompt to guide the assistant's behavior"
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for the response generation"
    )
    max_tokens: int = Field(
        default=500,
        ge=1,
        le=4000,
        description="Maximum number of tokens to generate in the response"
    )
