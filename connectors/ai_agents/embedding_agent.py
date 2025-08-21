import logging
from typing import List, Union, Dict

import numpy as np
from numpy.typing import NDArray
from openai import OpenAI, AsyncOpenAI

from schemas.document import Document

logger = logging.getLogger(__name__)


class EmbeddingAgent:
    """Agent for generating and managing document embeddings using OpenAI's API.
    
    This agent handles the generation of vector embeddings for text content,
    which can be used for semantic search and similarity comparisons.
    """

    def __init__(self, api_key: str, model: str = 'text-embedding-3-small', batch_size: int = 32):
        """Initialize the EmbeddingAgent with OpenAI API credentials.
        
        Args:
            api_key: OpenAI API key for authentication
            model: Name of the OpenAI embedding model to use.
                  Defaults to 'text-embedding-3-small' which is cost-effective
                  and performs well for most use cases.
            batch_size: Number of texts to process in each batch for embedding generation
        """
        self.model_name = model
        self.batch_size = batch_size
        self.client = OpenAI(api_key=api_key)
        self.async_client = AsyncOpenAI(api_key=api_key)

        # Model-specific dimensions
        self._model_dimensions: Dict[str, int] = {
            'text-embedding-3-small': 1536,
            'text-embedding-3-large': 3072,
            'text-embedding-ada-002': 1536
        }

        self.embedding_dim = self._model_dimensions.get(model, 1536)
        if model not in self._model_dimensions:
            logger.warning(f"Unknown model {model}, using default dimensions {self.embedding_dim}")

    async def get_embeddings(self, texts: Union[str, List[str]],
                             batch_size: int = 32) -> List[NDArray]:
        """Generate embeddings for the input text(s).
        
        Args:
            texts: A single text string or a list of text strings to embed
            batch_size: Number of texts to process in each API call
            
        Returns:
            List of numpy arrays containing the embeddings
        """
        if isinstance(texts, str):
            texts = [texts]

        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                response = await self.async_client.embeddings.create(
                    input=batch,
                    model=self.model_name
                )

                # Extract embeddings from the response
                batch_embeddings = [np.array(data.embedding) for data in response.data]
                all_embeddings.extend(batch_embeddings)

            except Exception as e:
                logger.error(f"Error generating embeddings: {str(e)}")
                # Return empty embeddings for failed batches
                all_embeddings.extend([np.zeros(self.embedding_dim)] * len(batch))

        return all_embeddings

    async def get_document_embeddings(self, documents: List[Document]) -> List[NDArray]:
        """Generate embeddings for a list of documents.
        
        Args:
            documents: List of Document objects to generate embeddings for
            
        Returns:
            List of numpy arrays containing the document embeddings
        """
        # Extract text content from documents
        texts = [doc.content for doc in documents]
        return await self.get_embeddings(texts)

    def get_embedding_dimension(self) -> int:
        """Get the dimension of the embeddings produced by this model."""
        return self.embedding_dim

    async def get_similarity(self, embedding1: NDArray, embedding2: NDArray) -> float:
        """Calculate cosine similarity between two embeddings.
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Cosine similarity score between -1 and 1
        """
        return float(np.dot(embedding1, embedding2) /
                     (np.linalg.norm(embedding1) * np.linalg.norm(embedding2)))

    async def find_similar_documents(self, query_embedding: NDArray,
                                     document_embeddings: List[NDArray],
                                     top_k: int = 5) -> List[int]:
        """Find the most similar documents to the query embedding.
        
        Args:
            query_embedding: The query embedding to compare against
            document_embeddings: List of document embeddings to search through
            top_k: Number of similar documents to return
            
        Returns:
            List of indices of the top_k most similar documents
        """
        if not document_embeddings:
            return []

        # Calculate similarities
        similarities = [
            await self.get_similarity(query_embedding, doc_emb)
            for doc_emb in document_embeddings
        ]

        # Get indices of top_k most similar documents
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        return top_indices.tolist()
