import logging
from typing import List, Dict, Any, Optional

from openai import OpenAI, AsyncOpenAI

from schemas.document import Document

logger = logging.getLogger(__name__)


class ChatAgent:
    """Agent for generating chat responses using OpenAI's chat completions API."""

    def __init__(
            self,
            api_key: str,
            model: str = 'gpt-4-turbo-preview',
            temperature: float = 0.7,
            max_tokens: Optional[int] = None,
            system_message: Optional[str] = None
    ):
        """Initialize the ChatAgent with OpenAI API credentials.
        
        Args:
            api_key: OpenAI API key for authentication
            model: Name of the OpenAI model to use for chat completions.
                  Defaults to 'gpt-4-turbo-preview' which is the latest model.
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum number of tokens to generate
            system_message: Optional custom system message
        """
        self.model_name = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = OpenAI(api_key=api_key)
        self.async_client = AsyncOpenAI(api_key=api_key)

        # Default system message
        self.system_message = {
            "role": "system",
            "content": system_message or (
                "You are a helpful AI assistant that provides accurate and concise "
                "information based on the provided context. If you don't know the answer "
                "based on the context, simply state that you don't have enough information."
            )
        }

    def format_context(self, documents: List[Document]) -> str:
        """Format document context for the chat prompt.
        
        Args:
            documents: List of relevant documents to include as context
            
        Returns:
            Formatted context string
        """
        if not documents:
            return "No relevant context available."

        context_parts = ["Relevant context for your response:"]
        for i, doc in enumerate(documents, 1):
            context_parts.append(f"\n--- Document {i} (Source: {doc.source_id or 'N/A'}) ---")
            context_parts.append(doc.content)

        return "\n".join(context_parts)

    async def generate_response(
            self,
            messages: List[Dict[str, str]],
            context_documents: Optional[List[Document]] = None,
            temperature: float = 0.7,
            max_tokens: int = 1000,
            **kwargs
    ) -> str:
        """Generate a response to the user's message with optional context.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content' keys
            context_documents: Optional list of documents to use as context
            temperature: Controls randomness (0.0 to 2.0)
            max_tokens: Maximum number of tokens to generate
            **kwargs: Additional arguments to pass to the API
            
        Returns:
            Generated response text
        """
        # Prepare messages with system message and context
        chat_messages = [self.system_message]

        # Add context if provided
        if context_documents:
            context = self.format_context(context_documents)
            chat_messages.append({
                "role": "system",
                "name": "context",
                "content": context
            })

        # Add user/assistant messages
        chat_messages.extend(messages)

        try:
            response = await self.async_client.chat.completions.create(
                model=self.model_name,
                messages=chat_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Error generating chat response: {str(e)}")
            return "I'm sorry, I encountered an error while processing your request. Please try again later."

    async def get_structured_response(
            self,
            messages: List[Dict[str, str]],
            response_format: Dict[str, Any],
            context_documents: Optional[List[Document]] = None,
            **kwargs
    ) -> Dict[str, Any]:
        """Generate a structured response based on a provided JSON schema.
        
        Args:
            messages: List of message dictionaries
            response_format: JSON schema for the expected response format
            context_documents: Optional list of documents to use as context
            **kwargs: Additional arguments to pass to the API
            
        Returns:
            Dictionary containing the structured response
        """
        # Prepare messages with system message and context
        chat_messages = [self.system_message]

        # Add context if provided
        if context_documents:
            context = self.format_context(context_documents)
            chat_messages.append({
                "role": "system",
                "name": "context",
                "content": context
            })

        # Add user/assistant messages
        chat_messages.extend(messages)

        try:
            response = await self.async_client.chat.completions.create(
                model=self.model_name,
                messages=chat_messages,
                response_format={"type": "json_schema", "schema": response_format},
                **kwargs
            )

            # Parse and return the JSON response
            import json
            return json.loads(response.choices[0].message.content)

        except Exception as e:
            logger.error(f"Error generating structured response: {str(e)}")
            return {"error": "Failed to generate structured response"}
