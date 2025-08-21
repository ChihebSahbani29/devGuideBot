from datetime import datetime

from bson import ObjectId
from pydantic import BaseModel, Field


class Message(BaseModel):
    """Represents a single exchange in a conversation (question + answer)."""
    question: str = Field(..., json_schema_extra={"example": "How do I implement data governance?"})
    answer: str = Field(...,
                        json_schema_extra={"example": "Data governance can be implemented by following these steps..."})
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ConversationCreateRequest(BaseModel):
    """Request model for creating a new conversation with an initial message."""
    message: str = Field(...,
                         json_schema_extra={"description": "The initial user message that starts the conversation"})
    title: str | None = Field(
        None,
        json_schema_extra={
            "description": "Optional title for the conversation. If not provided, one will be generated from the first message"
        }
    )


class ConversationUpdateRequest(BaseModel):
    """Request model for updating a conversation."""
    title: str | None = Field(None, json_schema_extra={"example": "Updated Conversation Title"})


class ConversationResponse(BaseModel):
    """Response model for a single conversation."""
    id: str
    workspace_id: str
    title: str
    messages: list[Message]
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "workspace_id": "507f1f77bcf86cd799439012",
                "title": "Data Governance Implementation",
                "messages": [
                    {
                        "question": "How do I implement data governance?",
                        "answer": "Data governance can be implemented by following these steps...",
                        "timestamp": "2023-01-01T00:00:00"
                    },
                    {
                        "question": "What tools can I use?",
                        "answer": "There are several tools available such as...",
                        "timestamp": "2023-01-01T00:01:00"
                    }
                ],
                "created_at": "2023-01-01T00:00:00",
                "updated_at": "2023-01-01T00:01:00"
            }
        }


class ConversationListResponse(BaseModel):
    """Response model for a list of conversations."""
    conversations: list[ConversationResponse]
