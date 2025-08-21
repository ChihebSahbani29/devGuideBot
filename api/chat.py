"""Chat API endpoints."""
import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse

from config.dependencies import get_chat_agent, get_document_service, get_conversation_service
from connectors.ai_agents.chat_agent import ChatAgent
from schemas.chat import (
    ChatRequest,
    ChatResponse,
    DocumentReference,
    ChatStreamChunk, TestChatRequest
)
from schemas.document import DocumentSearchQuery
from services.conversation import ConversationService
from services.document import DocumentService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat"])


def _format_document_reference(doc: Any) -> DocumentReference:
    """Convert a document object to a DocumentReference.
    
    Args:
        doc: Can be either a Document model instance or a dictionary
        
    Returns:
        DocumentReference with document details and similarity score
    """
    if hasattr(doc, 'model_dump'):
        doc_dict = doc.model_dump()
    else:
        doc_dict = dict(doc)
        
    return DocumentReference(
        document_id=doc_dict.get("id") or doc_dict.get("document_id") or doc_dict.get("id"),
        source=doc_dict.get("source_type", ""),
        title=doc_dict.get("title", ""),
        url=str(doc_dict.get("url")) or str(doc_dict.get("source_url")),
        content=doc_dict.get("content", ""),
        similarity_score=doc_dict.get("similarity_score")
    )


@router.post("/")
async def chat(
        chat_request: ChatRequest,
        workspace_id: str,
        conversation_id: str,
        chat_agent: Optional[ChatAgent] = Depends(get_chat_agent),
        document_service: DocumentService = Depends(get_document_service),
        conversation_service: ConversationService = Depends(get_conversation_service),
):
    """
    Handle a chat request and return a response, with optional streaming.
    
    This endpoint processes a chat message, retrieves relevant context from documents,
    and generates a response using the chat agent. It supports both streaming and non-streaming responses.
    
    Args:
        chat_request: The chat request containing the message and parameters
        workspace_id: Required ID of the workspace for the chat
        conversation_id: Required ID of the conversation to continue
        chat_agent: The chat agent for generating responses
        document_service: Service for document retrieval
        conversation_service: Service for conversation management
        
    Returns:
        ChatResponse: The generated response with metadata
        StreamingResponse: If streaming is enabled, returns a streaming response
    """
    logger.info(f"Received chat request for workspace {workspace_id}")

    try:
        # Get relevant documents using vector similarity search
        relevant_docs = []
        if chat_request.message.strip():
            try:
                search_query = DocumentSearchQuery(
                    query=chat_request.message,
                    source_types=chat_request.source_types,
                    source_ids=chat_request.source_ids,
                    workspace_id=workspace_id,
                    skip=0,  # Start from the first result
                    limit=min(chat_request.max_results, 3)  # Limit to a reasonable number of results
                )
                
                # Perform vector similarity search
                search_results = await document_service.search_documents(
                    workspace_id=workspace_id,
                    query=search_query
                )
                
                # Log search results for debugging
                logger.info(f"Found {len(search_results.items) if search_results else 0} relevant documents")
                if search_results and search_results.items:
                    for i, doc in enumerate(search_results.items[:3]):  # Log first 3 docs for debugging
                        logger.debug(f"Doc {i+1} - Score: {getattr(doc, 'similarity_score', 0.0):.3f} - {getattr(doc, 'title', 'No title')}")
                
                relevant_docs = search_results.items if search_results else []
                
            except Exception as e:
                logger.error(f"Error searching documents: {str(e)}", exc_info=True)
                # Continue with empty context rather than failing the request

        # Prepare conversation history
        messages = []
        if chat_request.system_prompt:
            messages.append({"role": "system", "content": chat_request.system_prompt})
        messages.append({"role": "user", "content": chat_request.message})

        # Generate response using the chat agent with relevant documents as context
        try:
            response = await chat_agent.generate_response(
                messages=messages,
                context_documents=relevant_docs,
                temperature=chat_request.temperature,
                max_tokens=chat_request.max_tokens,
                stream=chat_request.stream
            )
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate response: {str(e)}"
            )

        # Handle streaming response
        if chat_request.stream:
            async def stream_response():
                try:
                    if hasattr(response, '__aiter__'):
                        async for chunk in response:
                            yield f"data: {chunk}\n\n".encode('utf-8')
                    else:
                        # Handle case where response is a string
                        yield f"data: {response}\n\n".encode('utf-8')
                except Exception as e:
                    error_msg = f"Error in streaming response: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    yield f"data: {{\"error\": \"{error_msg}\"}}\n\n".encode('utf-8')
                
                # Add the message and response to the conversation after streaming is complete
                try:
                    await conversation_service.add_message(
                        workspace_id=workspace_id,
                        conversation_id=conversation_id,
                        question=chat_request.message,
                        answer=response
                    )
                except Exception as e:
                    logger.error(f"Failed to update conversation: {str(e)}", exc_info=True)
                    # Don't fail the request if conversation update fails
                
                yield "data: [DONE]\n\n".encode('utf-8')

            return StreamingResponse(
                stream_response(),
                media_type="text/event-stream"
            )

        # Add the message and response to the conversation
        try:
            await conversation_service.add_message(
                workspace_id=workspace_id,
                conversation_id=conversation_id,
                question=chat_request.message,
                answer=response
            )
        except Exception as e:
            logger.error(f"Failed to update conversation: {str(e)}", exc_info=True)
            # Don't fail the request if conversation update fails

        # Format document references with similarity scores
        formatted_docs = [
            _format_document_reference(doc) 
            for doc in relevant_docs
            if hasattr(doc, 'content') and doc.content  # Only include documents with content
        ]
        
        # Log the response for debugging
        logger.info(f"Sending response with {len(formatted_docs)} document references")
        
        # Handle non-streaming response
        return ChatResponse(
            response=response,
            conversation_id=conversation_id,
            documents=formatted_docs
        )

    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred: {str(e)}"
        )


@router.post("/test", response_model=dict)
async def test_chat(
        test_request: TestChatRequest,
        workspace_id: str,
        chat_agent: Optional[ChatAgent] = Depends(get_chat_agent)
) -> dict:
    """
    Test endpoint for chat functionality with a simple message.
    
    This endpoint allows quick testing of the chat agent with a single message
    without requiring document context or conversation history.
    
    Args:
        test_request: The test chat request containing the message and parameters
        workspace_id: Required ID of the workspace for the chat
        chat_agent: The chat agent for generating responses
        
    Returns:
        dict: The generated response with metadata
    """
    if not chat_agent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat agent is not available"
        )

    try:
        # Generate response using the chat agent directly
        messages = [{"role": "user", "content": test_request.message}]
        if test_request.system_prompt:
            messages.insert(0, {"role": "system", "content": test_request.system_prompt})
            
        response = await chat_agent.generate_response(
            messages=messages,
            temperature=test_request.temperature,
            max_tokens=test_request.max_tokens
        )

        return {
            "message": test_request.message,
            "response": response,
            "parameters": {
                "temperature": test_request.temperature,
                "max_tokens": test_request.max_tokens,
                "used_system_prompt": test_request.system_prompt is not None
            }
        }

    except Exception as e:
        logger.error(f"Error in test chat: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating response: {str(e)}"
        )