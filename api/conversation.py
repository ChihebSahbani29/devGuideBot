import logging

from fastapi import APIRouter, Depends, HTTPException, Path

logger = logging.getLogger(__name__)

from config.dependencies import get_conversation_service, get_chat_agent
from connectors.ai_agents.chat_agent import ChatAgent
from schemas.conversation import (
    ConversationCreateRequest,
    ConversationResponse,
    ConversationListResponse,
    ConversationUpdateRequest,
    Message
)
from services.conversation import ConversationService

router = APIRouter(prefix="/conversations/{workspace_id}/conversations", tags=["Conversations"])


@router.post("/", response_model=ConversationResponse, status_code=201)
async def create_conversation(
        workspace_id: str,
        req: ConversationCreateRequest,
        svc: ConversationService = Depends(get_conversation_service),
        chat_agent: ChatAgent = Depends(get_chat_agent)
):
    """Create a new conversation in the specified workspace with the first message.
    
    The conversation will be created with a title generated from the first message
    if not explicitly provided. The first message will be processed by the chat agent
    to generate an immediate response.
    """
    try:
        logger.info(f"Creating new conversation in workspace: {workspace_id}")
        # Pass the chat agent to generate a response for the first message
        conversation = await svc.create_conversation(workspace_id, req)
        logger.debug(f"Created conversation with ID: {conversation.get('id', 'unknown')}")
        return conversation
    except Exception as e:
        logger.error(f"Error creating conversation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create conversation: {str(e)}"
        )


@router.get("/", response_model=ConversationListResponse)
async def list_conversations(
        workspace_id: str,
        svc: ConversationService = Depends(get_conversation_service)
):
    """List all conversations in a workspace.
    
    Args:
        workspace_id: ID of the workspace to list conversations from
        
    Returns:
        ConversationListResponse: List of conversations
        
    Raises:
        HTTPException: If there's an error retrieving conversations
    """
    try:
        logger.info(f"Fetching conversations for workspace: {workspace_id}")
        conversations = await svc.list_conversations(workspace_id)
        logger.debug(f"Retrieved {len(conversations)} conversations")

        # Log the first conversation for debugging (if any)
        if conversations:
            logger.debug(f"First conversation sample: {conversations[0]}")

        response = {"conversations": conversations}
        logger.debug("Response prepared")
        return response

    except HTTPException as he:
        # Re-raise HTTP exceptions as they are
        logger.error(f"HTTP Exception in list_conversations: {str(he)}", exc_info=True)
        raise
    except Exception as e:

        # Return a 500 error with a generic message
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while retrieving conversations"
        )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
        workspace_id: str = Path(..., description="ID of the workspace"),
        conversation_id: str = Path(..., description="ID of the conversation"),
        svc: ConversationService = Depends(get_conversation_service)
):
    """Get a specific conversation from a workspace."""
    try:
        logger.info(f"Fetching conversation {conversation_id} from workspace {workspace_id}")
        conversation = await svc.get_conversation(workspace_id, conversation_id)
        if not conversation:
            logger.warning(f"Conversation {conversation_id} not found in workspace {workspace_id}")
            raise HTTPException(status_code=404, detail="Conversation not found")
        logger.debug(f"Successfully retrieved conversation {conversation_id}")
        return conversation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving conversation {conversation_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve conversation")


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
        workspace_id: str,
        conversation_id: str,
        req: ConversationUpdateRequest,
        svc: ConversationService = Depends(get_conversation_service)
):
    """Update a conversation."""
    try:
        logger.info(f"Updating conversation {conversation_id} in workspace {workspace_id}")
        logger.debug(f"Update data: {req.dict(exclude_unset=True)}")

        # Check if conversation exists first
        conversation = await svc.get_conversation(workspace_id, conversation_id)
        if not conversation:
            logger.warning(f"Conversation {conversation_id} not found in workspace {workspace_id}")
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Update the conversation
        updated = await svc.update_conversation(workspace_id, conversation_id, req)
        if not updated:
            logger.warning(f"No valid fields to update for conversation {conversation_id}")
            raise HTTPException(status_code=400, detail="No valid fields to update")

        # Return the updated conversation
        updated_conversation = await svc.get_conversation(workspace_id, conversation_id)
        if not updated_conversation:
            logger.error(f"Failed to retrieve updated conversation {conversation_id}")
            raise HTTPException(status_code=500, detail="Failed to retrieve updated conversation")

        logger.info(f"Successfully updated conversation {conversation_id}")
        return updated_conversation

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating conversation {conversation_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update conversation")


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
        workspace_id: str,
        conversation_id: str,
        svc: ConversationService = Depends(get_conversation_service)
):
    """Delete a conversation from a workspace."""
    try:
        logger.info(f"Deleting conversation {conversation_id} from workspace {workspace_id}")

        # Check if conversation exists first
        conversation = await svc.get_conversation(workspace_id, conversation_id)
        if not conversation:
            logger.warning(f"Conversation {conversation_id} not found in workspace {workspace_id}")
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Delete the conversation
        deleted = await svc.delete_conversation(workspace_id, conversation_id)
        if not deleted:
            logger.error(f"Failed to delete conversation {conversation_id}")
            raise HTTPException(status_code=500, detail="Failed to delete conversation")

        logger.info(f"Successfully deleted conversation {conversation_id}")
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversation {conversation_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete conversation")


@router.post("/{conversation_id}/messages", status_code=200, response_model=ConversationResponse)
async def add_message(
        workspace_id: str,
        conversation_id: str,
        message: Message,
        svc: ConversationService = Depends(get_conversation_service)
):
    """Add a message exchange (question + answer) to a conversation.
    
    This endpoint adds both the user's question and the assistant's answer
    as a single message exchange to maintain conversation context.
    """
    try:
        logger.info(f"Adding message to conversation {conversation_id} in workspace {workspace_id}")
        logger.debug(f"Message data: question={message.question[:50]}..., answer={message.answer[:50]}...")

        # Add the message to the conversation
        conversation = await svc.add_message(
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            question=message.question,
            answer=message.answer
        )

        logger.debug(f"Successfully added message to conversation {conversation_id}")
        return conversation

    except ValueError as e:
        if "not found" in str(e).lower():
            logger.warning(f"Conversation {conversation_id} not found: {str(e)}")
            raise HTTPException(status_code=404, detail=str(e))
        logger.warning(f"Invalid request for conversation {conversation_id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error adding message to conversation {conversation_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to add message to conversation")
