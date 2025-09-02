from typing import Dict, List, Any, Optional, Tuple
import re

from .base_chunker import BaseChunker

class CodeChunker(BaseChunker):
    """Chunker for source code files."""
    
    def __init__(self, max_chunk_size: int = 800, overlap: int = 50):
        super().__init__(max_chunk_size, overlap)
        
    async def chunk(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Chunk source code into functions, classes, or logical blocks.
        
        Args:
            content: Source code to chunk
            metadata: Optional metadata about the code
            
        Returns:
            List of code chunks with metadata
        """
        if not content.strip():
            return []
            
        metadata = metadata or {}
        chunks = []
        
        # First, try to split by functions/classes
        language = metadata.get('language', 'python').lower()
        
        if language == 'python':
            chunks = self._chunk_python(content, metadata)
        elif language in ['javascript', 'typescript', 'java', 'c', 'cpp', 'csharp']:
            chunks = self._chunk_braced_language(content, metadata, language)
        else:
            # Fallback to generic code chunking
            chunks = self._chunk_generic_code(content, metadata)
        
        # Process chunks to ensure they're within size limits
        processed_chunks = []
        for chunk in chunks:
            chunk_text = chunk['content']
            chunk_metadata = chunk['metadata']
            
            # If chunk is too large, try to split it further
            if len(chunk_text.split()) > self.max_chunk_size:
                sub_chunks = self._split_large_code_chunk(chunk_text, chunk_metadata)
                processed_chunks.extend(sub_chunks)
            else:
                processed_chunks.append({
                    'content': chunk_text,
                    'metadata': chunk_metadata,
                    'type': chunk.get('type', 'code')
                })
        
        return processed_chunks
    
    def _chunk_python(self, content: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Chunk Python code into functions, classes, and top-level code."""
        chunks = []
        lines = content.split('\n')
        
        # Patterns for Python functions and classes
        func_pattern = re.compile(r'^\s*(async\s+)?def\s+(\w+)\s*\(')
        class_pattern = re.compile(r'^\s*class\s+(\w+)')
        
        current_chunk = []
        current_scope = []  # Track nested scopes
        in_docstring = False
        docstring_quotes = None
        
        for i, line in enumerate(lines):
            # Skip empty lines at the start of a chunk
            if not current_chunk and not line.strip():
                continue
                
            # Handle docstrings
            line, in_docstring, docstring_quotes = self._handle_docstring(
                line, in_docstring, docstring_quotes)
                
            # Check for function or class definition
            is_func = func_pattern.match(line)
            is_class = class_pattern.match(line)
            
            if is_func or is_class:
                # If we have a chunk in progress, save it
                if current_chunk:
                    self._add_code_chunk(chunks, current_chunk, current_scope, metadata)
                    current_chunk = []
                
                # Start a new chunk
                current_chunk.append(line)
                
                # Update scope
                if is_class:
                    class_name = is_class.group(1)
                    current_scope = [f"class {class_name}"]
                else:
                    func_name = is_func.group(2)
                    scope = f"def {func_name}"
                    if current_scope:
                        scope = f"{current_scope[-1]}.{scope}"
                    current_scope.append(scope)
            else:
                current_chunk.append(line)
        
        # Add the last chunk if it exists
        if current_chunk:
            self._add_code_chunk(chunks, current_chunk, current_scope, metadata)
        
        return chunks
    
    def _chunk_braced_language(self, content: str, metadata: Dict[str, Any], language: str) -> List[Dict[str, Any]]:
        """Chunk languages that use braces for blocks (C-style syntax)."""
        chunks = []
        lines = content.split('\n')
        
        # Patterns for function/class definitions
        func_pattern = re.compile(r'^\s*(?:\w+\s+)+\**\s*(\w+)\s*\(')
        class_pattern = re.compile(r'^\s*class\s+(\w+)')
        
        current_chunk = []
        current_scope = []
        brace_count = 0
        in_block_comment = False
        
        for i, line in enumerate(lines):
            # Skip empty lines at the start of a chunk
            if not current_chunk and not line.strip():
                continue
                
            # Handle block comments
            if '/*' in line and '*/' in line:
                # Single-line block comment
                pass
            elif '/*' in line:
                in_block_comment = True
            elif '*/' in line:
                in_block_comment = False
                continue
                
            if in_block_comment:
                continue
                
            # Check for function or class definition at the start of a new scope
            if brace_count == 0:
                is_func = func_pattern.match(line)
                is_class = class_pattern.match(line)
                
                if is_func or is_class:
                    if current_chunk:
                        self._add_code_chunk(chunks, current_chunk, current_scope, metadata)
                        current_chunk = []
                    
                    current_chunk.append(line)
                    
                    if is_class:
                        class_name = is_class.group(1)
                        current_scope = [f"class {class_name}"]
                    else:
                        func_name = is_func.group(1)
                        scope = f"function {func_name}"
                        if current_scope:
                            scope = f"{current_scope[-1]}.{scope}"
                        current_scope.append(scope)
                else:
                    current_chunk.append(line)
            else:
                current_chunk.append(line)
            
            # Update brace count
            brace_count += line.count('{') - line.count('}')
        
        # Add the last chunk if it exists
        if current_chunk:
            self._add_code_chunk(chunks, current_chunk, current_scope, metadata)
        
        return chunks
    
    def _chunk_generic_code(self, content: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback chunker for other programming languages."""
        # Simple line-based chunking as a fallback
        lines = content.split('\n')
        chunks = []
        current_chunk = []
        
        for line in lines:
            current_chunk.append(line)
            
            # Start a new chunk after a certain number of lines
            if len(current_chunk) >= 50:  # Arbitrary number
                chunks.append({
                    'content': '\n'.join(current_chunk),
                    'metadata': metadata.copy(),
                    'type': 'code_block'
                })
                current_chunk = []
        
        # Add the last chunk if it exists
        if current_chunk:
            chunks.append({
                'content': '\n'.join(current_chunk),
                'metadata': metadata.copy(),
                'type': 'code_block'
            })
        
        return chunks
    
    def _add_code_chunk(self, 
                       chunks: List[Dict[str, Any]], 
                       lines: List[str], 
                       scope: List[str],
                       metadata: Dict[str, Any]) -> None:
        """Add a code chunk to the chunks list."""
        if not lines:
            return
            
        chunk_text = '\n'.join(lines).strip()
        if not chunk_text:
            return
            
        chunk_metadata = metadata.copy()
        if scope:
            chunk_metadata['scope'] = scope[-1]
            
        # Determine chunk type
        chunk_type = 'code_block'
        if scope:
            if scope[-1].startswith('class '):
                chunk_type = 'class_definition'
            elif scope[-1].startswith(('def ', 'function ')):
                chunk_type = 'function_definition'
        
        chunks.append({
            'content': chunk_text,
            'metadata': chunk_metadata,
            'type': chunk_type
        })
    
    def _handle_docstring(self, line: str, in_docstring: bool, docstring_quotes: Optional[str]) -> Tuple[str, bool, Optional[str]]:
        """Handle docstring detection and processing."""
        if not in_docstring:
            # Check for start of docstring
            if '"""' in line or "'''" in line:
                in_docstring = True
                # Find the first occurrence of either type of quotes
                triple_quotes = ['"""', "'''"]
                quote_positions = [(line.find(q), q) for q in triple_quotes if q in line]
                if quote_positions:
                    first_quote = min(quote_positions, key=lambda x: x[0] if x[0] >= 0 else float('inf'))
                    docstring_quotes = first_quote[1]
                    # Check if the docstring ends on the same line
                    if line.count(docstring_quotes) >= 2:
                        in_docstring = False
                        docstring_quotes = None
        else:
            # Check for end of docstring
            if docstring_quotes in line:
                in_docstring = False
                docstring_quotes = None
        
        return line, in_docstring, docstring_quotes
    
    def _split_large_code_chunk(self, content: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Split a large code chunk into smaller chunks."""
        lines = content.split('\n')
        chunks = []
        current_chunk = []
        current_size = 0
        
        for line in lines:
            line_size = len(line.split())
            
            if current_chunk and current_size + line_size > self.max_chunk_size:
                chunks.append({
                    'content': '\n'.join(current_chunk),
                    'metadata': metadata.copy(),
                    'type': 'code_block'
                })
                current_chunk = [line]
                current_size = line_size
            else:
                current_chunk.append(line)
                current_size += line_size
        
        if current_chunk:
            chunks.append({
                'content': '\n'.join(current_chunk),
                'metadata': metadata.copy(),
                'type': 'code_block'
            })
        
        return chunks
