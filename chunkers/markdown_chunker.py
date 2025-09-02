import re
from typing import Dict, List, Any, Optional, Tuple

from chunkers.base_chunker import BaseChunker

class MarkdownChunker(BaseChunker):
    """Chunker for Markdown and documentation content."""
    
    def __init__(self, max_chunk_size: int = 1000, overlap: int = 100):
        super().__init__(max_chunk_size, overlap)
        self.header_pattern = re.compile(r'^(#+)\s*(.*)')
    
    async def chunk(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Chunk markdown content by sections.
        
        Args:
            content: Markdown content to chunk
            metadata: Optional metadata about the content
            
        Returns:
            List of chunks with content and metadata
        """
        if not content.strip():
            return []
            
        metadata = metadata or {}
        lines = content.split('\n')
        chunks = []
        current_chunk = []
        current_header = None
        header_level = 0
        
        for i, line in enumerate(lines):
            # Check if this is a header
            header_match = self.header_pattern.match(line)
            if header_match:
                # If we have content in the current chunk, save it first
                if current_chunk:
                    self._add_chunk(chunks, current_chunk, current_header, header_level, metadata)
                    current_chunk = []
                
                # Start a new chunk with this header
                current_header = header_match.group(2).strip()
                header_level = len(header_match.group(1))
                current_chunk.append(line)
            else:
                current_chunk.append(line)
                
                # Check if we've exceeded the max chunk size
                chunk_text = '\n'.join(current_chunk)
                if len(chunk_text.split()) > self.max_chunk_size:
                    self._split_large_chunk(chunks, current_chunk, current_header, header_level, metadata)
                    current_chunk = []
        
        # Add the last chunk if there's any content
        if current_chunk:
            self._add_chunk(chunks, current_chunk, current_header, header_level, metadata)
        
        return chunks
    
    def _add_chunk(self, 
                  chunks: List[Dict[str, Any]], 
                  lines: List[str], 
                  header: Optional[str],
                  header_level: int,
                  metadata: Dict[str, Any]) -> None:
        """Add a chunk to the chunks list."""
        if not lines:
            return
            
        chunk_text = '\n'.join(lines).strip()
        if not chunk_text:
            return
            
        chunk_metadata = metadata.copy()
        if header:
            chunk_metadata['header'] = header
            chunk_metadata['header_level'] = header_level
            
        chunks.append({
            'content': chunk_text,
            'metadata': chunk_metadata,
            'type': 'markdown_section'
        })
    
    def _split_large_chunk(self,
                         chunks: List[Dict[str, Any]], 
                         lines: List[str],
                         header: Optional[str],
                         header_level: int,
                         metadata: Dict[str, Any]) -> None:
        """Split a chunk that's too large into smaller chunks."""
        if not lines:
            return
            
        # If it's just one line that's too long, we have to include it as is
        if len(lines) == 1:
            self._add_chunk(chunks, lines, header, header_level, metadata)
            return
            
        # Try to split on paragraphs first
        paragraphs = []
        current_para = []
        
        for line in lines:
            if not line.strip() and current_para:
                paragraphs.append('\n'.join(current_para))
                current_para = []
            elif line.strip():
                current_para.append(line)
        
        if current_para:
            paragraphs.append('\n'.join(current_para))
        
        # If we can't split into paragraphs, split by lines
        if len(paragraphs) <= 1:
            mid = len(lines) // 2
            self._add_chunk(chunks, lines[:mid], header, header_level, metadata)
            self._add_chunk(chunks, lines[mid:], header, header_level, metadata)
            return
            
        # Otherwise, try to combine paragraphs into chunks
        current_chunk = []
        current_size = 0
        
        for para in paragraphs:
            para_size = len(para.split())
            
            if current_chunk and current_size + para_size > self.max_chunk_size:
                self._add_chunk(chunks, current_chunk, header, header_level, metadata)
                current_chunk = [para]
                current_size = para_size
            else:
                current_chunk.append(para)
                current_size += para_size
        
        if current_chunk:
            self._add_chunk(chunks, current_chunk, header, header_level, metadata)
