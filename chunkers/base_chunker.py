from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class BaseChunker(ABC):
    """Base class for all chunkers."""

    def __init__(self, max_chunk_size: int = 1000, overlap: int = 100):
        """Initialize the chunker with size and overlap parameters.
        
        Args:
            max_chunk_size: Maximum size of each chunk in tokens
            overlap: Number of tokens to overlap between chunks
        """
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap

    @abstractmethod
    async def chunk(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Chunk the given content into smaller pieces.
        
        Args:
            content: The content to chunk
            metadata: Optional metadata about the content
            
        Returns:
            List of chunks, each with content and metadata
        """
        raise NotImplementedError

    @classmethod
    def get_chunker_for_type(cls, content_type: str, **kwargs) -> 'BaseChunker':
        """Get the appropriate chunker for the given content type.
        
        Args:
            content_type: Type of content to chunk (e.g., 'markdown', 'code')
            **kwargs: Additional arguments to pass to the chunker
            
        Returns:
            An instance of the appropriate chunker
        """
        raise NotImplementedError
