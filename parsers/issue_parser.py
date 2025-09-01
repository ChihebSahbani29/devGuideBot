from pathlib import Path
from pathlib import Path
from typing import Dict, List, Any, Optional

from parsers.base_parser import BaseParser


class IssueParser(BaseParser):
    """Parser for GitHub issues, PRs, and commit messages.
    
    This parser extracts structured information from GitHub issues and pull requests,
    including metadata, descriptions, comments, and related content.
    """

    @classmethod
    def supported_formats(cls) -> List[str]:
        """Return a list of supported file extensions."""
        return ['md', 'markdown', 'txt', 'issue', 'pr']
        
    @classmethod
    def get_parser_for_file(cls, file_path: str) -> Optional['IssueParser']:
        """Get a parser instance if the file type is supported."""
        file_ext = Path(file_path).suffix.lstrip('.').lower()
        if file_ext in cls.supported_formats():
            return cls()
        return None
        
    def parse_content(self, content: str, metadata: Optional[Dict] = None) -> List[Dict[str, str]]:
        """Parse issue/PR content and return structured chunks.
        
        Args:
            content: The issue/PR content to parse
            metadata: Optional metadata about the content
            
        Returns:
            List of dictionaries containing parsed issue/PR chunks with metadata
        """
        if not content:
            return []
            
        # Parse the issue/PR content
        parsed = self._parse_issue_pr(content)
        chunks = []
        
        # Add title as a chunk
        if parsed.get('title'):
            chunks.append({
                'content': parsed['title'],
                'type': 'issue_title',
                'metadata': {
                    'issue_number': parsed.get('number'),
                    'state': parsed.get('state', 'open'),
                    'created_at': parsed.get('created_at'),
                    **(metadata or {})
                }
            })
        
        # Add description as a chunk
        if parsed.get('description'):
            chunks.append({
                'content': parsed['description'],
                'type': 'issue_description',
                'metadata': {
                    'issue_number': parsed.get('number'),
                    'state': parsed.get('state', 'open'),
                    **(metadata or {})
                }
            })
        
        # Add comments as chunks
        for comment in parsed.get('comments', []):
            if comment.get('body'):
                chunks.append({
                    'content': comment['body'],
                    'type': 'issue_comment',
                    'metadata': {
                        'issue_number': parsed.get('number'),
                        'comment_id': comment.get('id'),
                        'user': comment.get('user', {}).get('login'),
                        'created_at': comment.get('created_at'),
                        **(metadata or {})
                    }
                })
        
        # Add labels
        if parsed.get('labels'):
            chunks.append({
                'content': ', '.join(label.get('name', '') for label in parsed['labels']),
                'type': 'issue_labels',
                'metadata': {
                    'issue_number': parsed.get('number'),
                    'label_count': len(parsed['labels']),
                    **(metadata or {})
                }
            })
            
        return chunks

    def _parse_issue_pr(self, content: str) -> Dict[str, Any]:
        """Parse an issue or PR markdown content."""
        result = {
            'title': '',
            'description': '',
            'labels': [],
            'assignees': [],
            'milestone': None,
            'state': 'open',
            'created_at': None,
            'updated_at': None,
            'closed_at': None,
            'comments': [],
            'events': [],
            'diff_hunks': []
        }

        # Extract title (first line)
        lines = content.split('\n')
        if lines:
            result['title'] = lines[0].strip('# ')

            # Extract metadata from YAML front matter if present
            if lines[0].strip() == '---':
                yaml_content = []
                in_yaml = True
                for line in lines[1:]:
                    if line.strip() == '---':
                        in_yaml = False
                        break
                    yaml_content.append(line)

                # Parse YAML content
                if yaml_content:
                    import yaml
                    try:
                        metadata = yaml.safe_load('\n'.join(yaml_content))
                        if isinstance(metadata, dict):
                            for key in ['labels', 'assignees', 'milestone', 'state']:
                                if key in metadata:
                                    result[key] = metadata[key]
                    except:
                        pass

                # The rest is the description
                remaining_lines = lines[lines.index('---', 1) + 2:]
            else:
                # The rest is the description
                remaining_lines = lines[1:]

            # Extract description
            description_lines = []
            in_code_block = False

            for line in remaining_lines:
                # Skip metadata lines
                if line.startswith(('labels:', 'assignees:', 'milestone:', 'state:')):
                    continue

                # Handle code blocks
                if line.strip().startswith('```'):
                    in_code_block = not in_code_block

                description_lines.append(line)

            result['description'] = '\n'.join(description_lines).strip()

            # Extract diff hunks from the description
            self._extract_diff_hunks(result, result['description'])

        return result

    def _extract_diff_hunks(self, result: Dict[str, Any], content: str) -> None:
        """Extract diff hunks from content."""
        diff_start = None
        diff_content = []

        for i, line in enumerate(content.split('\n')):
            if line.startswith('```diff') or (line.startswith('```') and 'diff' in line.lower()):
                if diff_start is not None:
                    # End of previous diff
                    if diff_content:
                        result['diff_hunks'].append({
                            'content': '\n'.join(diff_content),
                            'start_line': diff_start,
                            'end_line': i - 1
                        })
                        diff_content = []
                diff_start = i + 1
            elif line.startswith('```') and diff_start is not None:
                # End of diff
                if diff_content:
                    result['diff_hunks'].append({
                        'content': '\n'.join(diff_content),
                        'start_line': diff_start,
                        'end_line': i - 1
                    })
                    diff_content = []
                diff_start = None
            elif diff_start is not None:
                diff_content.append(line)

    def _parse_commit_message(self, content: str) -> Dict[str, Any]:
        """Parse a git commit message."""
        lines = [line.strip() for line in content.split('\n') if line.strip()]

        result = {
            'summary': '',
            'description': '',
            'type': 'commit',
            'files_changed': [],
            'additions': 0,
            'deletions': 0
        }

        if not lines:
            return result

        # First line is the summary
        result['summary'] = lines[0]

        # The rest is the description
        if len(lines) > 1:
            result['description'] = '\n'.join(lines[1:])

        # Extract file changes from diff stats if present
        diff_start = None
        for i, line in enumerate(lines):
            if line.startswith('diff --git'):
                diff_start = i
                break

            # Try to parse diffstat line (e.g., "2 files changed, 10 insertions(+), 3 deletions(-)")
            if 'file' in line and 'change' in line.lower():
                # Extract numbers
                numbers = [int(s) for s in line.split() if s.isdigit()]
                if len(numbers) >= 1:
                    result['files_changed'] = numbers[0]
                if len(numbers) >= 2:
                    result['insertions'] = numbers[1]
                if len(numbers) >= 3:
                    result['deletions'] = numbers[2]

        return result

    def parse(self, file_path: str | Path) -> List[Dict[str, str]]:
        """Parse an issue, PR, or commit message file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, 'r', encoding='latin-1') as f:
                content = f.read()

        file_path = Path(file_path)
        file_name = file_path.name.lower()

        # Determine the type of content
        if file_name.startswith(('issue_', 'pr_')) or file_path.suffix in ['.md', '.markdown']:
            # Parse as issue or PR
            data = self._parse_issue_pr(content)
            issue_type = 'issue' if 'issue' in file_name.lower() else 'pull_request'

            chunks = [{
                'content': data['title'],
                'type': f'{issue_type}_title',
                'file': str(file_path)
            }]

            if data['description']:
                chunks.append({
                    'content': data['description'],
                    'type': f'{issue_type}_description',
                    'file': str(file_path)
                })

            for diff in data['diff_hunks']:
                chunks.append({
                    'content': diff['content'],
                    'type': 'diff_hunk',
                    'file': str(file_path),
                    'start_line': diff['start_line'],
                    'end_line': diff['end_line']
                })

            return chunks

        elif file_name.startswith(('commit_', 'cm_')) or 'commit' in file_name:
            # Parse as commit message
            data = self._parse_commit_message(content)

            return [{
                'content': data['summary'],
                'type': 'commit_summary',
                'description': data['description'],
                'files_changed': data['files_changed'],
                'additions': data['additions'],
                'deletions': data['deletions'],
                'file': str(file_path)
            }]

        else:
            # Fallback to simple text parsing
            return [{
                'content': content,
                'type': 'text',
                'file': str(file_path)
            }]
