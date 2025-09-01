from typing import Dict, List, Any, Optional
import re

from .base_chunker import BaseChunker

class ConfigChunker(BaseChunker):
    """Chunker for configuration files (YAML, JSON, TOML, .env, etc.)."""
    
    def __init__(self, max_chunk_size: int = 500, overlap: int = 50):
        super().__init__(max_chunk_size, overlap)
    
    def chunk(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Chunk configuration content into logical sections.
        
        Args:
            content: Configuration content to chunk
            metadata: Optional metadata about the configuration
            
        Returns:
            List of configuration chunks with metadata
        """
        if not content.strip():
            return []
            
        metadata = metadata or {}
        chunks = []
        
        # Determine config type from metadata or content
        config_type = metadata.get('config_type')
        if not config_type:
            # Try to infer from content
            config_type = self._infer_config_type(content)
        
        # Use appropriate chunking strategy
        if config_type == 'yaml':
            chunks = self._chunk_yaml(content, metadata)
        elif config_type == 'json':
            chunks = self._chunk_json(content, metadata)
        elif config_type == 'toml':
            chunks = self._chunk_toml(content, metadata)
        elif config_type == 'env':
            chunks = self._chunk_env(content, metadata)
        else:
            # Fallback to generic chunking
            chunks = self._chunk_generic(content, metadata)
        
        # Process chunks to ensure they're within size limits
        processed_chunks = []
        for chunk in chunks:
            if len(chunk['content'].split()) > self.max_chunk_size:
                # If a chunk is too large, split it further
                sub_chunks = self._split_large_chunk(chunk['content'], chunk['metadata'])
                processed_chunks.extend(sub_chunks)
            else:
                processed_chunks.append(chunk)
        
        return processed_chunks
    
    def _infer_config_type(self, content: str) -> str:
        """Infer the configuration type from the content."""
        first_line = content.split('\n', 1)[0].strip()
        
        # Check for JSON
        if content.strip().startswith('{') or content.strip().startswith('['):
            return 'json'
            
        # Check for TOML
        if '=' in first_line and ('[' in first_line or '"' in first_line or '#' in first_line):
            return 'toml'
            
        # Check for YAML
        if (':' in first_line and (' ' in first_line or '\t' in first_line)) or \
           first_line.startswith('---'):
            return 'yaml'
            
        # Check for .env
        if '=' in first_line and not any(c in first_line for c in ['{', '}', '[', ']', ':']):
            return 'env'
            
        # Default to generic
        return 'generic'
    
    def _chunk_yaml(self, content: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Chunk YAML content by top-level keys."""
        try:
            import yaml
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                return self._chunk_generic(content, metadata)
                
            chunks = []
            for key, value in data.items():
                chunk_metadata = metadata.copy()
                chunk_metadata['section'] = str(key)
                
                # Convert the section back to YAML
                chunk_content = yaml.dump({key: value}, default_flow_style=False)
                
                chunks.append({
                    'content': chunk_content,
                    'metadata': chunk_metadata,
                    'type': 'yaml_section'
                })
                
            return chunks
            
        except Exception:
            # If YAML parsing fails, fall back to generic chunking
            return self._chunk_generic(content, metadata)
    
    def _chunk_json(self, content: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Chunk JSON content by top-level keys."""
        try:
            import json
            data = json.loads(content)
            if not isinstance(data, dict):
                return self._chunk_generic(content, metadata)
                
            chunks = []
            for key, value in data.items():
                chunk_metadata = metadata.copy()
                chunk_metadata['section'] = str(key)
                
                # Convert the section back to JSON
                chunk_content = json.dumps({key: value}, indent=2)
                
                chunks.append({
                    'content': chunk_content,
                    'metadata': chunk_metadata,
                    'type': 'json_section'
                })
                
            return chunks
            
        except Exception:
            # If JSON parsing fails, fall back to generic chunking
            return self._chunk_generic(content, metadata)
    
    def _chunk_toml(self, content: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Chunk TOML content by sections."""
        try:
            import toml
            data = toml.loads(content)
            
            chunks = []
            
            # Handle top-level key-value pairs
            top_level = {k: v for k, v in data.items() if not isinstance(v, dict)}
            if top_level:
                chunk_metadata = metadata.copy()
                chunk_metadata['section'] = 'top_level'
                
                chunks.append({
                    'content': toml.dumps(top_level),
                    'metadata': chunk_metadata,
                    'type': 'toml_section'
                })
            
            # Handle tables
            for section, section_data in data.items():
                if isinstance(section_data, dict):
                    chunk_metadata = metadata.copy()
                    chunk_metadata['section'] = section
                    
                    chunks.append({
                        'content': f"[{section}]\n{toml.dumps(section_data)}",
                        'metadata': chunk_metadata,
                        'type': 'toml_section'
                    })
            
            return chunks
            
        except Exception:
            # If TOML parsing fails, fall back to generic chunking
            return self._chunk_generic(content, metadata)
    
    def _chunk_env(self, content: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Chunk .env files by grouping related variables."""
        lines = content.split('\n')
        chunks = []
        current_chunk = []
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            current_chunk.append(line)
            
            # Start a new chunk after a certain number of lines
            if len(current_chunk) >= 10:  # Arbitrary number
                chunks.append({
                    'content': '\n'.join(current_chunk),
                    'metadata': metadata.copy(),
                    'type': 'env_vars'
                })
                current_chunk = []
        
        # Add the last chunk if it exists
        if current_chunk:
            chunks.append({
                'content': '\n'.join(current_chunk),
                'metadata': metadata.copy(),
                'type': 'env_vars'
            })
        
        return chunks
    
    def _chunk_generic(self, content: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback chunker for unknown configuration formats."""
        # Simple line-based chunking
        lines = content.split('\n')
        chunks = []
        current_chunk = []
        
        for line in lines:
            current_chunk.append(line)
            
            # Start a new chunk after a certain number of lines
            if len(current_chunk) >= 20:  # Arbitrary number
                chunks.append({
                    'content': '\n'.join(current_chunk),
                    'metadata': metadata.copy(),
                    'type': 'config_section'
                })
                current_chunk = []
        
        # Add the last chunk if it exists
        if current_chunk:
            chunks.append({
                'content': '\n'.join(current_chunk),
                'metadata': metadata.copy(),
                'type': 'config_section'
            })
        
        return chunks
    
    def _split_large_chunk(self, content: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Split a large configuration chunk into smaller chunks."""
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
                    'type': 'config_section'
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
                'type': 'config_section'
            })
        
        return chunks
