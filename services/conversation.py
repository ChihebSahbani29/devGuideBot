import logging
from datetime import datetime
from typing import Any, Optional

from bson import ObjectId
from fastapi import HTTPException

from connectors.ai_agents.chat_agent import ChatAgent
from repositories.conversation import ConversationRepository
from schemas.conversation import (
    ConversationCreateRequest,
    ConversationUpdateRequest,
    Message
)
from schemas.document import DocumentSearchQuery
from services.document import DocumentService

logger = logging.getLogger(__name__)


class ConversationService:
    def __init__(self, repo: ConversationRepository, chat_agent: ChatAgent, document_service: DocumentService):
        """Initialize conversation service with repository and dependencies.
        
        Args:
            repo: Conversation repository instance
            chat_agent: Chat agent for generating responses
            document_service: Document service for retrieving relevant documents
        """
        self.repo = repo
        self.chat_agent = chat_agent
        self.document_service = document_service

    async def create_conversation(
            self,
            workspace_id: str,
            conversation_data: ConversationCreateRequest,
    ) -> dict[str, Any]:
        """Create a new conversation in the specified workspace with the first message.
        
        Args:
            workspace_id: ID of the workspace
            conversation_data: Contains the initial user message and chat parameters
            
        Returns:
            Dict: The created conversation data with LLM response
        """
        # Generate a title from the first message if not provided
        title = conversation_data.title or self._generate_title(conversation_data.message)

        # Generate response using chat agent if available
        answer = ""
        if self.chat_agent:
            try:
                # Search for relevant documents using vector search
                relevant_docs = []
                if conversation_data.message.strip():
                    try:
                        # Perform vector similarity search
                        search_query = DocumentSearchQuery(
                            query=conversation_data.message,
                            source_types=None,  # Search across all source types
                            source_ids=None,  # Search across all sources
                            workspace_id=workspace_id,
                            skip=0,
                            limit=3  # Limit to top 3 most relevant documents
                        )

                        search_results = await self.document_service.search_documents(
                            workspace_id=workspace_id,
                            query=search_query
                        )

                        if search_results and search_results.items:
                            relevant_docs = search_results.items
                            logger.info(f"Found {len(relevant_docs)} relevant documents for conversation start")
                    except Exception as e:
                        logger.error(f"Error during document search: {str(e)}", exc_info=True)

                # Generate response using the chat agent with the retrieved documents
                answer = await self.chat_agent.generate_response(
                    messages=[{"role": "user", "content": conversation_data.message}],
                    context_documents=relevant_docs,
                    temperature=0.1,  # Keep temperature low for more focused responses
                    max_tokens=1000,  # Limit response length
                    stream=False
                )
            except Exception as e:
                logger.error(f"Error generating LLM response: {str(e)}", exc_info=True)
                answer = "I apologize, but I encountered an error generating a response."

        # Create the initial message with the generated response
        first_message = Message(
            question=conversation_data.message,
            answer=answer,
            timestamp=datetime.utcnow()
        )

        # Prepare conversation data
        now = datetime.utcnow()
        conversation_data = {
            "workspace_id": ObjectId(workspace_id),
            "title": title,
            "messages": [first_message.model_dump()],
            "created_at": now,
            "updated_at": now
        }

        # Create the conversation in the database
        conversation_id = await self.repo.create_conversation(
            workspace_id=workspace_id,
            data={
                "title": title,
                "messages": [first_message.model_dump()]
            }
        )

        # Return the created conversation by fetching it back from the repository
        conversation = await self.repo.get_conversation(workspace_id, conversation_id)
        if not conversation:
            raise ValueError("Failed to retrieve created conversation")

        # Convert ObjectId to string for the response
        conversation["id"] = str(conversation["_id"])
        conversation["workspace_id"] = str(conversation["workspace_id"])
        return conversation

    async def get_conversation(
            self,
            workspace_id: str,
            conversation_id: str
    ) -> dict | None:
        """Get a specific conversation from a workspace.
        
        Args:
            workspace_id: ID of the workspace
            conversation_id: ID of the conversation to retrieve
            
        Returns:
            Optional[dict]: The conversation data formatted according to ConversationResponse schema,
                          or None if not found
            
        Raises:
            HTTPException: If there's an error retrieving the conversation
        """
        try:
            # Get the conversation from the repository
            conversation = await self.repo.get_conversation(workspace_id, conversation_id)

            if not conversation:
                return None

            # Format the conversation to match the ConversationResponse schema
            formatted_conv = {
                'id': str(conversation.get('_id', '')),
                'workspace_id': str(conversation.get('workspace_id', '')),
                'title': conversation.get('title', 'Untitled Conversation'),
                'messages': [],
                'created_at': conversation.get('created_at'),
                'updated_at': conversation.get('updated_at')
            }

            # Format messages to ensure they match the Message model
            if 'messages' in conversation and isinstance(conversation['messages'], list):
                for msg in conversation['messages']:
                    if not isinstance(msg, dict):
                        continue
                    # Only include valid messages with required fields
                    if 'question' in msg and 'answer' in msg:
                        formatted_msg = {
                            'question': msg.get('question', ''),
                            'answer': msg.get('answer', ''),
                            'timestamp': msg.get('timestamp')
                        }
                        formatted_conv['messages'].append(formatted_msg)

            return formatted_conv

        except Exception as e:
            # Return a 500 error with a generic message
            raise HTTPException(
                status_code=500,
                detail=f"An unexpected error occurred while retrieving the conversation: {str(e)}"
            )

    async def list_conversations(self, workspace_id: str) -> list[dict]:
        """List all conversations in a workspace.
        
        Args:
            workspace_id: ID of the workspace
            
        Returns:
            list[dict]: List of conversations in the format expected by the API,
                      or empty list if none found
            
        Raises:
            HTTPException: If there's an error retrieving conversations
        """
        from datetime import datetime

        try:
            # Get raw conversations from repository
            conversations = await self.repo.list_conversations(workspace_id)

            # Transform each conversation to match the expected API response format
            formatted_conversations = []
            for conv in conversations:
                # Ensure all required fields are present and properly formatted
                formatted_conv = {
                    'id': str(conv.get('_id', '')),
                    'workspace_id': str(conv.get('workspace_id', '')),
                    'title': conv.get('title', 'Untitled Conversation'),
                    'messages': conv.get('messages', []),
                    'created_at': conv.get('created_at', datetime.utcnow()),
                    'updated_at': conv.get('updated_at', datetime.utcnow())
                }

                # Ensure messages have the correct structure
                if formatted_conv['messages'] and isinstance(formatted_conv['messages'], list):
                    for msg in formatted_conv['messages']:
                        if not isinstance(msg, dict):
                            continue
                        # Ensure required message fields exist
                        msg.setdefault('question', '')
                        msg.setdefault('answer', '')
                        msg.setdefault('timestamp', datetime.utcnow())

                formatted_conversations.append(formatted_conv)

            return formatted_conversations

        except ValueError as e:
            # Log the error here if you have a logging setup
            raise HTTPException(
                status_code=400,
                detail=str(e)
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"An unexpected error occurred while retrieving conversations: {str(e)}"
            )

    async def update_conversation(
            self,
            workspace_id: str,
            conversation_id: str,
            update_data: ConversationUpdateRequest
    ) -> bool:
        """Update a conversation.
        
        Args:
            workspace_id: ID of the workspace
            conversation_id: ID of the conversation to update
            update_data: Fields to update
            
        Returns:
            bool: True if the update was successful, False otherwise
        """
        # Convert Pydantic model to dict and remove None values
        update_dict = update_data.model_dump(exclude_unset=True)
        if not update_dict:
            return False

        return await self.repo.update_conversation(
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            update_data=update_dict
        )

    async def delete_conversation(
            self,
            workspace_id: str,
            conversation_id: str
    ) -> bool:
        """Delete a conversation from a workspace.
        
        Args:
            workspace_id: ID of the workspace
            conversation_id: ID of the conversation to delete
            
        Returns:
            bool: True if the deletion was successful, False otherwise
        """
        return await self.repo.delete_conversation(workspace_id, conversation_id)

    def _generate_title(self, message: str, max_length: int = 50) -> str:
        """Generate a title from the first message.
        
        Args:
            message: The user's message
            max_length: Maximum length of the generated title
            
        Returns:
            str: Generated title
        """
        # Simple implementation - take first N characters
        # In a real app, you might want to use NLP to generate a better title
        title = message.strip()
        if len(title) > max_length:
            title = title[:max_length].rsplit(' ', 1)[0] + '...'
        return title or "New Conversation"

    async def add_message(
            self,
            workspace_id: str,
            conversation_id: str,
            question: str,
            answer: str
    ) -> dict[str, Any]:
        """Add a message exchange (question + answer) to a conversation.
        
        Args:
            workspace_id: ID of the workspace
            conversation_id: ID of the conversation
            question: The user's question
            answer: The assistant's answer
            
        Returns:
            Dict: Updated conversation data
            
        Raises:
            ValueError: If the conversation is not found or message addition fails
        """
        # Create the message
        message = Message(
            question=question,
            answer=answer,
            timestamp=datetime.utcnow()
        )

        try:
            # Add the message to the conversation using the repository method
            success = await self.repo.add_message(
                workspace_id=workspace_id,
                conversation_id=conversation_id,
                message=message.model_dump()
            )

            if not success:
                raise ValueError("Failed to add message to conversation - no documents were modified")

            # Return the updated conversation
            updated = await self.repo.get_conversation(workspace_id, conversation_id)

            if not updated:
                raise ValueError(f"Conversation {conversation_id} not found in workspace {workspace_id}")

            # Format the conversation for the response
            return {
                'id': str(updated.get('_id', '')),
                'workspace_id': str(updated.get('workspace_id', '')),
                'title': updated.get('title', 'Untitled Conversation'),
                'messages': [
                    {
                        'question': msg.get('question', ''),
                        'answer': msg.get('answer', ''),
                        'timestamp': msg.get('timestamp')
                    }
                    for msg in updated.get('messages', [])
                    if isinstance(msg, dict) and 'question' in msg and 'answer' in msg
                ],
                'created_at': updated.get('created_at'),
                'updated_at': updated.get('updated_at')
            }

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"An unexpected error occurred while adding message: {str(e)}"
            )

        return updated
