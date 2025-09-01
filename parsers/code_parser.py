from pathlib import Path
from typing import Dict, List, Optional, Tuple

import tree_sitter_languages
from tree_sitter import Parser, Node

from parsers.base_parser import BaseParser

# Supported languages and their tree-sitter language names
SUPPORTED_LANGUAGES = {
    'python': 'python',
    'javascript': 'javascript',
    'typescript': 'typescript',
    'java': 'java',
    'go': 'go',
    'ruby': 'ruby',
    'rust': 'rust',
    'cpp': 'cpp',
    'c': 'c',
    'c_sharp': 'c-sharp',
}


class CodeParser(BaseParser):
    """Parser for source code files using tree-sitter.

    This parser uses tree-sitter to parse and extract meaningful chunks from source code files.
    It supports multiple programming languages and can extract functions, classes, and other
    code structures with proper metadata.
    """

    def __init__(self):
        """Initialize the CodeParser and set up language parsers."""
        self.parsers = {}
        self._setup_parsers()

    @classmethod
    def get_parser_for_file(cls, file_path: str) -> Optional['CodeParser']:
        """Get a parser instance if the file type is supported."""
        file_ext = Path(file_path).suffix.lstrip('.').lower()
        if file_ext in cls.supported_formats():
            return cls()
        return None

    def parse_content(self, content: str, metadata: Optional[Dict] = None) -> List[Dict[str, str]]:
        """Parse code content and return structured chunks.

        Args:
            content: The source code content to parse
            metadata: Optional metadata about the content

        Returns:
            List of dictionaries containing parsed code chunks with metadata
        """
        if not content:
            return []

        # Get language from metadata or try to detect it
        language = (metadata or {}).get('language', '').lower()
        if not language and 'file_extension' in (metadata or {}):
            language = metadata['file_extension'].lstrip('.').lower()

        if language not in self.parsers:
            # Try to find a matching parser
            for lang in self.parsers:
                if language in SUPPORTED_LANGUAGES.get(lang, '').lower():
                    language = lang
                    break
            else:
                # Default to first available parser if no match found
                language = next(iter(self.parsers.keys()), None)

        if not language or language not in self.parsers:
            return [{
                'content': content,
                'type': 'code',
                'metadata': metadata or {}
            }]

        # Parse the code using the appropriate parser
        tree = self.parsers[language].parse(bytes(content, 'utf8'))
        root_node = tree.root_node

        # Extract functions, classes, etc. based on language
        chunks = []
        if language == 'python':
            chunks = self._extract_python_nodes(root_node, content)
        # Add other language-specific extraction methods as needed
        else:
            # Default: just return the whole content as one chunk
            chunks = [{
                'content': content,
                'type': 'code',
                'metadata': {
                    'language': language,
                    **(metadata or {})
                }
            }]

        return chunks

    @classmethod
    def supported_formats(cls) -> List[str]:
        return list(SUPPORTED_LANGUAGES.keys()) + ['py', 'js', 'ts', 'jsx', 'tsx', 'java', 'go', 'rb', 'rs', 'cpp',
                                                     'c', 'cs']

    def _extract_python_nodes(self, root_node: Node, content: str) -> List[Dict[str, str]]:
        """Extract functions, classes, and other nodes from Python code.

        Args:
            root_node: The root node of the parsed syntax tree
            content: The original source code content (already decoded)

        Returns:
            List of dictionaries containing code chunks with metadata
        """
        chunks = []

        # Define the types of nodes we want to extract
        node_types = [
            'function_definition',
            'class_definition',
            'decorated_definition',
            'async_function_definition'
        ]

        # Get all nodes of interest
        def get_nodes(node: Node):
            if node.type in node_types:
                node_content = content[node.start_byte:node.end_byte]
                chunks.append({
                    'content': node_content,
                    'type': node.type,
                    'metadata': {
                        'name': self._get_node_name(node, content),
                        'line_start': node.start_point[0] + 1,  # 1-based line numbers
                        'line_end': node.end_point[0] + 1,
                        'language': 'python'
                    }
                })

            for child in node.children:
                get_nodes(child)

        # Start traversal from the root node
        get_nodes(root_node)

        # If no specific nodes were found, return the whole content as a single chunk
        if not chunks:
            return [{
                'content': content,
                'type': 'module',
                'metadata': {'language': 'python'}
            }]

        return chunks

    def _get_node_name(self, node: Node, content: str) -> str:
        """Extract the name of a node (function/class name).

        Args:
            node: The node to extract the name from
            content: The source code content (already decoded)

        Returns:
            The name of the node or 'anonymous' if not found
        """
        for child in node.children:
            if child.type == 'identifier':
                return content[child.start_byte:child.end_byte]
        return 'anonymous'

    def _setup_parsers(self):
        """Set up tree-sitter parsers for all supported languages using tree-sitter-languages."""
        for lang_key, lang_name in SUPPORTED_LANGUAGES.items():
            try:
                # Get the language parser from tree-sitter-languages
                parser = Parser()
                language = tree_sitter_languages.get_language(lang_name)
                if language is None:
                    continue

                # Set the language for the parser
                parser.language = language
                self.parsers[lang_key] = (parser, language)
            except Exception as e:
                # Skip if language is not available
                continue

    def _get_parser_for_file(self, file_path: str | Path) -> Optional[Tuple[Parser, str]]:
        """Get the appropriate parser for the given file."""
        ext = Path(file_path).suffix.lstrip('.').lower()

        # Map file extensions to language names
        ext_to_lang = {
            'py': 'python',
            'js': 'javascript',
            'jsx': 'javascript',
            'ts': 'typescript',
            'tsx': 'typescript',
            'java': 'java',
            'go': 'go',
            'rb': 'ruby',
            'rs': 'rust',
            'cpp': 'cpp',
            'c': 'c',
            'cs': 'c_sharp',
        }

        lang = ext_to_lang.get(ext)
        if not lang or lang not in self.parsers:
            return None

        return self.parsers[lang]

    def _get_node_text(self, node: Node, source: bytes) -> str:
        """Get the text content of a node."""
        return source[node.start_byte:node.end_byte].decode('utf-8')

    def _parse_code_file(self, file_path: str | Path, parser: Parser, language: str) -> List[Dict[str, str]]:
        """Parse a code file using the given parser and language."""
        with open(file_path, 'rb') as f:
            source = f.read()

        tree = parser.parse(source)
        root_node = tree.root_node

        chunks = []

        # Extract file-level docstring if it exists
        if language == 'python':
            module_docstring = next(
                (node for node in root_node.children
                 if node.type == 'expression_statement' and
                 node.children and
                 node.children[0].type == 'string'),
                None
            )
            if module_docstring:
                chunks.append({
                    'content': self._get_node_text(module_docstring, source),
                    'type': 'module_docstring',
                    'line_start': module_docstring.start_point[0] + 1,
                    'line_end': module_docstring.end_point[0] + 1
                })

        # Extract imports
        imports = []
        for node in root_node.children:
            if node.type in ('import_statement', 'import_from_statement'):
                imports.append({
                    'content': self._get_node_text(node, source),
                    'type': 'import',
                    'line_start': node.start_point[0] + 1,
                    'line_end': node.end_point[0] + 1
                })

        if imports:
            chunks.extend(imports)

        # Extract functions and classes
        def walk(node: Node):
            if node.type in ('function_definition', 'class_definition', 'method_definition'):
                # Get the docstring if it exists
                docstring = None
                body = next((child for child in node.children if child.type == 'block'), None)
                if body and language == 'python':
                    first_stmt = next(iter(body.children), None)
                    if first_stmt and first_stmt.type == 'expression_statement':
                        first_child = first_stmt.children[0] if first_stmt.children else None
                        if first_child and first_child.type == 'string':
                            docstring = first_child

                # Get the function/class signature
                name_node = next((child for child in node.children
                                  if child.type == 'identifier'), None)
                name = self._get_node_text(name_node, source) if name_node else 'anonymous'

                # Get the full content
                content = self._get_node_text(node, source)

                chunks.append({
                    'content': content,
                    'type': node.type,
                    'name': name,
                    'line_start': node.start_point[0] + 1,
                    'line_end': node.end_point[0] + 1,
                    'docstring': self._get_node_text(docstring, source) if docstring else None
                })

            for child in node.children:
                walk(child)

        walk(root_node)

        return chunks

    def parse(self, file_path: str | Path) -> List[Dict[str, str]]:
        """Parse a code file and return a list of chunks."""
        parser_lang = self._get_parser_for_file(file_path)
        if not parser_lang:
            # Fall back to simple line-based parsing for unsupported languages
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            return [{
                'content': content,
                'type': 'code',
                'language': Path(file_path).suffix.lstrip('.').lower(),
                'line_start': 1,
                'line_end': len(content.split('\n'))
            }]

        parser, language = parser_lang
        return self._parse_code_file(file_path, parser, language)
