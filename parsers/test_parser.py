import re
from pathlib import Path
from typing import Dict, List, Optional

from parsers.code_parser import CodeParser


class TestParser(CodeParser):
    """Parser for test files that links tests to their implementation."""

    @classmethod
    def supported_formats(cls) -> List[str]:
        # Support all code formats plus common test file patterns
        base_formats = super().supported_formats()
        test_suffixes = ['_test', 'test_', 'spec', '_spec', 'test']
        return base_formats + [f"{ext}.{suffix}" for ext in base_formats for suffix in test_suffixes]

    def _find_implementation_file(self, test_file_path: str | Path) -> Optional[Path]:
        """Find the implementation file corresponding to a test file."""
        test_path = Path(test_file_path)
        test_name = test_path.stem
        test_dir = test_path.parent

        # Common test file patterns to implementation file mappings
        test_patterns = [
            (r'^test_(.+)\.py$', r'\1.py'),  # test_*.py -> *.py
            (r'^(.+)_test\.py$', r'\1.py'),  # *_test.py -> *.py
            (r'^test_(.+)', r'\1'),  # test_* -> *
            (r'^(.+)_test$', r'\1'),  # *_test -> *
            (r'^(.+)\.spec\.([^.]+)$', r'\1.\2'),  # *.spec.ext -> *.ext
            (r'^(.+)\.test\.([^.]+)$', r'\1.\2'),  # *.test.ext -> *.ext
        ]

        # Check for implementation file in the same directory
        for pattern, replacement in test_patterns:
            if re.match(pattern, test_path.name):
                impl_name = re.sub(pattern, replacement, test_path.name)
                impl_path = test_dir / impl_name
                if impl_path.exists():
                    return impl_path

        # Check in parent directories (e.g., tests/foo/bar_test.py -> src/foo/bar.py)
        for pattern, replacement in test_patterns:
            if re.match(pattern, test_path.name):
                impl_name = re.sub(pattern, replacement, test_path.name)

                # Common directory structures
                test_dirs = ['tests', 'test', 'spec', 'tests/unit', 'tests/integration']
                impl_dirs = ['src', 'lib', 'app', '']

                for test_dir in test_dirs:
                    if test_dir in str(test_path):
                        for impl_dir in impl_dirs:
                            # Replace test dir with implementation dir
                            parts = list(test_path.parts)
                            try:
                                test_dir_idx = parts.index(test_dir)
                                if impl_dir:
                                    parts[test_dir_idx] = impl_dir
                                else:
                                    parts.pop(test_dir_idx)

                                # Try to find the file
                                impl_path = Path(*parts[:-1]) / impl_name
                                if impl_path.exists():
                                    return impl_path

                                # Try with different directory structures
                                for depth in range(1, 3):  # Look up to 3 levels up
                                    parent = test_path.parents[depth - 1]
                                    for parent_dir in test_dirs:
                                        if parent_dir in parent.parts:
                                            rel_path = test_path.relative_to(parent)
                                            for impl_dir in impl_dirs:
                                                impl_path = parent.parent / impl_dir / rel_path
                                                impl_path = impl_path.with_name(impl_name)
                                                if impl_path.exists():
                                                    return impl_path
                            except (ValueError, IndexError):
                                continue

        return None

    def _extract_test_functions(self, content: str, language: str) -> List[Dict[str, str]]:
        """Extract test functions from test file content."""
        tests = []

        # Python test patterns
        if language == 'python':
            # Match test functions and methods
            pattern = r'^\s*(async\s+)?def\s+(test_[^\s(]+)'
            for match in re.finditer(pattern, content, re.MULTILINE):
                test_name = match.group(2)
                tests.append({
                    'name': test_name,
                    'type': 'test_function',
                    'line': content[:match.start()].count('\n') + 1
                })

            # Match test classes
            pattern = r'^class\s+(Test\w+|\w+Test)\s*[(:]'
            for match in re.finditer(pattern, content, re.MULTILINE):
                class_name = match.group(1)
                tests.append({
                    'name': class_name,
                    'type': 'test_class',
                    'line': content[:match.start()].count('\n') + 1
                })

        # JavaScript/TypeScript test patterns
        elif language in ['javascript', 'typescript']:
            # Match test/it/describe blocks
            pattern = r'(?:test|it|describe)\s*\(\s*["\']([^"\']+)["\']'
            for match in re.finditer(pattern, content):
                test_name = match.group(1)
                tests.append({
                    'name': test_name,
                    'type': 'test_case',
                    'line': content[:match.start()].count('\n') + 1
                })

        # Java test patterns (JUnit)
        elif language == 'java':
            # Match @Test methods
            pattern = r'@Test\s+.*?\s+(?:public\s+)?(?:void|Void)\s+(test\w+)\s*\('
            for match in re.finditer(pattern, content):
                test_name = match.group(1)
                tests.append({
                    'name': test_name,
                    'type': 'test_method',
                    'line': content[:match.start()].count('\n') + 1
                })

        return tests

    def parse(self, file_path: str | Path) -> List[Dict[str, str]]:
        """Parse a test file and link it to its implementation."""
        # First, use the parent class to parse the test file
        chunks = super().parse(file_path)

        # Add test-specific metadata
        test_file_path = Path(file_path)
        language = test_file_path.suffix.lstrip('.').lower()

        # Find the implementation file
        impl_path = self._find_implementation_file(test_file_path)

        # If we found an implementation file, add a reference to it
        if impl_path and impl_path.exists():
            for chunk in chunks:
                chunk['implements'] = str(impl_path.relative_to(Path.cwd()))

        # Extract test functions and add them as separate chunks
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        test_functions = self._extract_test_functions(content, language)
        for test in test_functions:
            chunks.append({
                'content': test['name'],
                'type': test['type'],
                'name': test['name'],
                'line': test['line'],
                'file': str(file_path),
                'implements': str(impl_path.relative_to(Path.cwd())) if impl_path and impl_path.exists() else None
            })

        return chunks
