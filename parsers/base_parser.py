from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class BaseParser(ABC):
    """Base class for all document parsers.
    
    This class defines the interface that all parsers must implement.
    """

    @classmethod
    @abstractmethod
    def supported_formats(cls) -> List[str]:
        """Return a list of file extensions this parser supports (without leading .)"""
        raise NotImplementedError

    @abstractmethod
    async def parse(self, file_path: Union[str, Path]) -> List[Dict[str, str]]:
        """Parse a file and return a list of chunks with metadata.
        
        Args:
            file_path: Path to the file to parse
            
        Returns:
            List of dictionaries, each containing:
            - content: The parsed content
            - type: Type of content (e.g., 'code', 'text', 'header')
            - metadata: Additional metadata (e.g., line numbers, section)
        """
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def get_parser_for_file(cls, file_path: Union[str, Path]) -> Optional['BaseParser']:
        """Get the appropriate parser for the given file.
        
        Args:
            file_path: Path to the file to parse
            
        Returns:
            An instance of the appropriate parser, or None if no parser is found
        """
        raise NotImplementedError

    @abstractmethod
    def parse_content(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Parse content from a string and return structured chunks.
        
        Args:
            content: The content to parse as a string
            metadata: Optional dictionary containing metadata about the content
            
        Returns:
            List of dictionaries containing parsed chunks with metadata
        """
        pass
