"""Service for testing and working with document parsers."""
import logging
from typing import Dict, Any, Optional, List

from chunkers.base_chunker import BaseChunker
from parsers.base_parser import BaseParser
from schemas.parser import ParserTestResult, ChunkResult

logger = logging.getLogger(__name__)


class ParserService:
    """Service for testing and working with document parsers."""

    def __init__(
        self,
        parsers: Dict[str, BaseParser],
        chunkers: Dict[str, BaseChunker]
    ):
        """Initialize with available parsers and chunkers.
        
        Args:
            parsers: Dictionary of available parsers by name
            chunkers: Dictionary of available chunkers by name
        """
        self.parsers = parsers
        self.chunkers = chunkers

    async def test_parse(
        self,
        content: str,
        content_type: str,
        parser_type: Optional[str] = None,
        chunker_type: Optional[str] = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 100,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ParserTestResult:
        """Test parsing and chunking of content without persistence.
        
        Args:
            content: The content to parse
            content_type: MIME type or file extension of the content
            parser_type: Optional specific parser to use
            chunker_type: Optional specific chunker to use
            chunk_size: Maximum size of chunks in characters
            chunk_overlap: Number of characters to overlap between chunks
            metadata: Additional metadata to include
            
        Returns:
            ParserTestResult with parsed and chunked content
        """
        metadata = metadata or {}
        
        # Get the appropriate parser
        parser = self._get_parser(content_type, parser_type)
        if not parser:
            raise ValueError(f"No suitable parser found for content type: {content_type}")
        
        # Parse the content
        parsed_chunks = parser.parse_content(content, {
            'content_type': content_type,
            'file_extension': content_type.split('/')[-1] if '/' in content_type else content_type,
            **metadata
        })
        
        # Get the appropriate chunker
        chunker = self._get_chunker(content_type, chunker_type)
        if not chunker:
            raise ValueError(f"No suitable chunker found for content type: {content_type}")
        
        # Chunk the content
        chunker.chunk_size = chunk_size
        chunker.chunk_overlap = chunk_overlap
        all_chunks = []
        for parsed in parsed_chunks:
            chunks = chunker.chunk(parsed['content'], {
                'content_type': content_type,
                'chunk_type': parsed.get('type', 'text'),
                **parsed.get('metadata', {})
            })
            all_chunks.extend(chunks)
        # Prepare the result
        chunk_results = [
            ChunkResult(
                content=chunk['content'],
                metadata=chunk.get('metadata', {}),
                type=chunk.get('type', 'text'),
                token_count=len(chunk['content'].split())  # Simple token estimation
            )
            for chunk in all_chunks
        ]
        
        return ParserTestResult(
            content_type=content_type,
            parser_used=parser.__class__.__name__,
            chunker_used=chunker.__class__.__name__,
            chunks=chunk_results,
            metadata={
                'original_length': len(content),
                'chunk_count': len(chunk_results),
                **metadata
            },
            stats={
                'char_count': len(content),
                'chunk_count': len(chunk_results),
                'avg_chunk_size': sum(len(c.content) for c in chunk_results) / len(chunk_results) if chunk_results else 0,
            }
        )
    
    def _get_parser(self, content_type: str, parser_type: Optional[str] = None) -> Optional[BaseParser]:
        """Get the appropriate parser for the given content type."""
        if parser_type:
            return self.parsers.get(parser_type)
        
        # Try to find a parser that supports this content type
        for parser in self.parsers.values():
            if hasattr(parser, 'supported_formats'):
                supported = parser.supported_formats()
                if content_type.lower() in [fmt.lower() for fmt in supported]:
                    return parser
        
        return None
    
    def _get_chunker(self, content_type: str, chunker_type: Optional[str] = None) -> Optional[BaseChunker]:
        """Get the appropriate chunker for the given content type."""
        if chunker_type:
            return self.chunkers.get(chunker_type)
        
        # Default to text chunker if no specific chunker is specified
        return self.chunkers.get('text') or next(iter(self.chunkers.values()), None)
