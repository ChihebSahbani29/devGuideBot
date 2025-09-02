import json
from pathlib import Path
from typing import Dict, List, Any, Optional

import toml
import yaml

from parsers.base_parser import BaseParser


class ConfigParser(BaseParser):
    """Parser for configuration files (YAML, JSON, TOML, .env).
    
    This parser handles various configuration file formats and extracts key-value pairs
    with appropriate metadata about their structure and hierarchy.
    """

    @classmethod
    def supported_formats(cls) -> List[str]:
        """Return a list of supported file extensions."""
        return ['yaml', 'yml', 'json', 'toml', 'env', 'ini', 'cfg', 'conf']
        
    @classmethod
    def get_parser_for_file(cls, file_path: str) -> Optional['ConfigParser']:
        """Get a parser instance if the file type is supported."""
        file_ext = Path(file_path).suffix.lstrip('.').lower()
        if file_ext in cls.supported_formats():
            return cls()
        return None
        
    def parse_content(self, content: str, metadata: Optional[Dict] = None) -> List[Dict[str, str]]:
        """Parse configuration content and return structured chunks.
        
        Args:
            content: The configuration content to parse
            metadata: Optional metadata about the content
            
        Returns:
            List of dictionaries containing parsed configuration chunks with metadata
        """
        if not content:
            return []
            
        file_ext = (metadata or {}).get('file_extension', '').lower()
        if not file_ext and metadata and 'content_type' in metadata:
            # Try to extract extension from content type
            content_type = metadata['content_type'].lower()
            if 'yaml' in content_type or 'yml' in content_type:
                file_ext = 'yaml'
            elif 'json' in content_type:
                file_ext = 'json'
            elif 'toml' in content_type:
                file_ext = 'toml'
                
        # Parse based on file extension
        if file_ext in ['yaml', 'yml']:
            parsed = self._parse_yaml(content)
        elif file_ext == 'json':
            parsed = self._parse_json(content)
        elif file_ext == 'toml':
            parsed = self._parse_toml(content)
        elif file_ext == 'env':
            parsed = self._parse_env(content)
        else:
            # Try to auto-detect format
            try:
                parsed = self._parse_json(content) or self._parse_yaml(content) or self._parse_toml(content)
            except:
                parsed = {}
                
        if not parsed:
            return [{
                'content': content,
                'type': 'config',
                'metadata': metadata or {}
            }]
            
        # Flatten nested structures and create chunks
        flat_config = self._flatten_dict(parsed)
        return [{
            'content': f"{k} = {v}",
            'type': 'config_entry',
            'metadata': {
                'key': k,
                'value': str(v),
                'file_type': file_ext,
                **(metadata or {})
            }
        } for k, v in flat_config.items()]

    def _parse_yaml(self, content: str) -> Dict[str, Any]:
        """Parse YAML content."""
        try:
            return yaml.safe_load(content)
        except yaml.YAMLError:
            return {}

    def _parse_toml(self, content: str) -> Dict[str, Any]:
        """Parse TOML content."""
        try:
            return toml.loads(content)
        except toml.TomlDecodeError:
            return {}

    def _parse_json(self, content: str) -> Dict[str, Any]:
        """Parse JSON content."""
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {}

    def _parse_env(self, content: str) -> Dict[str, str]:
        """Parse .env file content."""
        result = {}
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            result[key.strip()] = value.strip().strip('"\'')
        return result

    def _flatten_dict(self, d: Dict[str, Any], parent_key: str = '') -> Dict[str, str]:
        """Flatten a nested dictionary into a single level with dot notation."""
        items = {}
        for k, v in d.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(self._flatten_dict(v, new_key))
            elif isinstance(v, (list, tuple)):
                # Convert lists/tuples to JSON strings
                items[new_key] = json.dumps(v)
            else:
                items[new_key] = str(v)
        return items

    def _format_config_chunk(self, config: Dict[str, Any], file_path: str | Path) -> List[Dict[str, str]]:
        """Format configuration data into chunks."""
        chunks = []

        # Add a chunk for the entire config
        chunks.append({
            'content': json.dumps(config, indent=2),
            'type': 'config_full',
            'file': str(file_path)
        })

        # Add chunks for each top-level section
        if isinstance(config, dict):
            for section, section_data in config.items():
                if isinstance(section_data, dict):
                    chunks.append({
                        'content': f"[{section}]\n{json.dumps(section_data, indent=2)}",
                        'type': 'config_section',
                        'section': section,
                        'file': str(file_path)
                    })

        # Add chunks for each key-value pair (flattened)
        flat_config = self._flatten_dict(config)
        for key, value in flat_config.items():
            chunks.append({
                'content': f"{key} = {value}",
                'type': 'config_key',
                'key': key,
                'file': str(file_path)
            })

        return chunks

    async def parse(self, file_path: str | Path) -> List[Dict[str, str]]:
        """Parse a configuration file and return a list of chunks."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, 'r', encoding='latin-1') as f:
                content = f.read()

        file_ext = Path(file_path).suffix.lower().lstrip('.')

        try:
            if file_ext in ['yaml', 'yml']:
                config = self._parse_yaml(content)
            elif file_ext == 'json':
                config = self._parse_json(content)
            elif file_ext == 'toml':
                config = self._parse_toml(content)
            elif file_ext == 'env':
                config = self._parse_env(content)
            else:
                # Try to parse as INI-like format
                config = {}
                current_section = None
                for line in content.split('\n'):
                    line = line.strip()
                    if not line or line.startswith(('#', ';')):
                        continue
                    if line.startswith('[') and line.endswith(']'):
                        current_section = line[1:-1].strip()
                        config[current_section] = {}
                    elif '=' in line and current_section is not None:
                        key, value = line.split('=', 1)
                        config[current_section][key.strip()] = value.strip()
                    elif '=' in line:
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()

            return self._format_config_chunk(config, file_path)

        except Exception as e:
            # Fallback to simple content parsing if structured parsing fails
            return [{
                'content': content,
                'type': 'config_raw',
                'file': str(file_path),
                'error': str(e)
            }]
