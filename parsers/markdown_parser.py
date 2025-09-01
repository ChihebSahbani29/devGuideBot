import re
from pathlib import Path
from typing import Dict, List, Optional

from parsers.base_parser import BaseParser


class MarkdownParser(BaseParser):
    """Parser for Markdown files, READMEs, and documentation.
    
    This parser processes Markdown content, extracting text and code blocks with proper
    metadata about their structure, headers, and formatting.
    """

    @classmethod
    def supported_formats(cls) -> List[str]:
        """Return a list of supported file extensions."""
        return ['md', 'markdown', 'mdx', 'rst']
        
    @classmethod
    def get_parser_for_file(cls, file_path: str) -> Optional['MarkdownParser']:
        """Get a parser instance if the file type is supported."""
        file_ext = Path(file_path).suffix.lstrip('.').lower()
        if file_ext in cls.supported_formats():
            return cls()
        return None
        
    def parse_content(self, content: str, metadata: Optional[Dict] = None) -> List[Dict[str, str]]:
        """Parse markdown content and return structured chunks.
        
        Args:
            content: The markdown content to parse
            metadata: Optional metadata about the content
            
        Returns:
            List of dictionaries containing parsed markdown chunks with metadata
        """
        if not content:
            return []
            
        chunks = []
        current_chunk = []
        in_code_block = False
        code_block_lang = ''
        current_heading = ''
        current_heading_level = 0
        
        lines = content.split('\n')
        for i, line in enumerate(lines):
            # Handle code blocks
            if line.strip().startswith('```'):
                if in_code_block:
                    # End of code block
                    if current_chunk:
                        chunks.append({
                            'content': '\n'.join(current_chunk),
                            'type': 'code',
                            'metadata': {
                                'language': code_block_lang,
                                'heading': current_heading,
                                'heading_level': current_heading_level,
                                'line_start': i - len(current_chunk),
                                'line_end': i,
                                **(metadata or {})
                            }
                        })
                        current_chunk = []
                    in_code_block = False
                else:
                    # Start of code block
                    if current_chunk:
                        chunks.append({
                            'content': '\n'.join(current_chunk),
                            'type': 'text',
                            'metadata': {
                                'heading': current_heading,
                                'heading_level': current_heading_level,
                                'line_start': i - len(current_chunk),
                                'line_end': i - 1,
                                **(metadata or {})
                            }
                        })
                        current_chunk = []
                    in_code_block = True
                    code_block_lang = line.strip().strip('`').strip()
            else:
                # Handle headings
                heading_match = re.match(r'^(#+)\s+(.*)', line)
                if heading_match:
                    if current_chunk:
                        chunks.append({
                            'content': '\n'.join(current_chunk),
                            'type': 'text',
                            'metadata': {
                                'heading': current_heading,
                                'heading_level': current_heading_level,
                                'line_start': i - len(current_chunk),
                                'line_end': i - 1,
                                **(metadata or {})
                            }
                        })
                        current_chunk = []
                    
                    current_heading_level = len(heading_match.group(1))
                    current_heading = heading_match.group(2).strip()
                    
                    chunks.append({
                        'content': current_heading,
                        'type': 'heading',
                        'metadata': {
                            'level': current_heading_level,
                            'line_number': i,
                            **(metadata or {})
                        }
                    })
                else:
                    current_chunk.append(line)
        
        # Add any remaining content
        if current_chunk:
            chunks.append({
                'content': '\n'.join(current_chunk),
                'type': 'code' if in_code_block else 'text',
                'metadata': {
                    'language': code_block_lang if in_code_block else None,
                    'heading': current_heading,
                    'heading_level': current_heading_level,
                    'line_start': len(lines) - len(current_chunk),
                    'line_end': len(lines) - 1,
                    **(metadata or {})
                }
            })
            
        return chunks

    def parse(self, file_path: str | Path) -> List[Dict[str, str]]:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        chunks = []
        current_chunk = []
        in_code_block = False
        code_block_lang = ''

        lines = content.split('\n')
        for i, line in enumerate(lines):
            # Handle code blocks
            if line.strip().startswith('```'):
                if in_code_block:
                    # End of code block
                    if current_chunk:
                        chunks.append({
                            'content': '\n'.join(current_chunk),
                            'type': 'code',
                            'language': code_block_lang,
                            'line_start': i - len(current_chunk),
                            'line_end': i
                        })
                        current_chunk = []
                    in_code_block = False
                else:
                    # Start of code block
                    if current_chunk:
                        chunks.append({
                            'content': '\n'.join(current_chunk),
                            'type': 'text',
                            'line_start': i - len(current_chunk),
                            'line_end': i - 1
                        })
                        current_chunk = []
                    in_code_block = True
                    code_block_lang = line.strip().strip('`').strip()
                continue

            if in_code_block:
                current_chunk.append(line)
                continue

            # Handle headers
            header_match = re.match(r'^(#+)\s*(.*)', line)
            if header_match:
                if current_chunk:
                    chunks.append({
                        'content': '\n'.join(current_chunk),
                        'type': 'text',
                        'line_start': i - len(current_chunk),
                        'line_end': i - 1
                    })
                    current_chunk = []

                level = len(header_match.group(1))
                header_text = header_match.group(2).strip()
                chunks.append({
                    'content': header_text,
                    'type': f'header_{min(level, 6)}',  # h1-h6
                    'line_start': i,
                    'line_end': i
                })
                continue

            # Handle lists
            if re.match(r'^\s*[-*+]\s+', line) or re.match(r'^\s*\d+\.\s+', line):
                if current_chunk and not current_chunk[-1].startswith(('  ', '\t')):
                    if current_chunk:
                        chunks.append({
                            'content': '\n'.join(current_chunk),
                            'type': 'text',
                            'line_start': i - len(current_chunk),
                            'line_end': i - 1
                        })
                        current_chunk = []

            current_chunk.append(line)

        # Add the last chunk if any
        if current_chunk:
            chunks.append({
                'content': '\n'.join(current_chunk),
                'type': 'code' if in_code_block else 'text',
                'line_start': len(lines) - len(current_chunk),
                'line_end': len(lines) - 1
            })

        return chunks
