"""GitLab agent for interacting with GitLab repositories.

This module provides functionality to interact with GitLab's API, including listing projects,
retrieving file contents, and searching code across repositories.
"""
import base64
import logging
import os
from datetime import datetime
from typing import Dict, Any

import aiohttp

from connectors.base_agent import BaseAgent
from schemas.agent import AgentType, AgentResponse, AgentStatus
from schemas.document import DocumentSourceType, IngestedDocument

logger = logging.getLogger(__name__)

# File extensions to include in ingestion
SUPPORTED_EXTENSIONS = {
    '.md', '.txt', '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp',
    '.h', '.hpp', '.go', '.rb', '.php', '.rs', '.swift', '.kt', '.dart', '.sh',
    '.yaml', '.yml', '.json', '.xml', '.html', '.css', '.scss', '.less', '.vue'
}

# File patterns to exclude
EXCLUDE_PATTERNS = {
    'node_modules/', 'vendor/', 'dist/', 'build/', '__pycache__/', '.git/',
    '*.min.js', '*.min.css', '*.bundle.js', 'package-lock.json', 'yarn.lock',
    '*.log', '*.tmp', '*.swp', '*.swo', '.DS_Store', 'Thumbs.db'
}


class GitLabAgent(BaseAgent):
    """Agent for interacting with GitLab repositories."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the GitLab agent with configuration.
        
        Args:
            config: Configuration dictionary containing:
                - access_token: GitLab personal access token (required)
                - base_url: GitLab instance URL (default: https://gitlab.com)
                - project_id: Default project ID (optional)
                - group_id: Default group ID (optional)
        """
        if not config.get('access_token'):
            raise ValueError("GitLab access token is required in the configuration")

        super().__init__(
            name="gitlab_agent",
            description="Agent for fetching and processing data from GitLab repositories",
            config=config
        )
        self._initialized = False

        self.access_token = config.get('access_token')
        self.base_url = config.get('base_url', 'https://gitlab.com').rstrip('/')
        self.project_id = config.get('project_id')
        self.group_id = config.get('group_id')
        self.source_type = AgentType.GITLAB
        self.session = None

    async def initialize(self, **kwargs) -> AgentResponse:
        """Initialize the GitLab agent.
        
        Args:
            **kwargs: Additional arguments
                - workspace_id: ID of the workspace
                
        Returns:
            AgentResponse: Initialization status
        """
        if self._initialized:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITLAB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ACTIVE,
                enabled=True,
                config=self.config,
                capabilities=await self.get_capabilities(),
                workspace_id=kwargs.get('workspace_id', ''),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                data={"message": "Agent already initialized"}
            )

        try:
            headers = {
                "PRIVATE-TOKEN": self.access_token,
                "Content-Type": "application/json"
            }
            self.session = aiohttp.ClientSession(headers=headers)
            self._initialized = True

            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITLAB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ACTIVE,
                enabled=True,
                config=self.config,
                capabilities=await self.get_capabilities(),
                workspace_id=kwargs.get('workspace_id', ''),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                data={"message": "GitLab agent initialized successfully"}
            )
        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITLAB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ERROR,
                enabled=True,
                config=self.config,
                capabilities=await self.get_capabilities(),
                workspace_id=kwargs.get('workspace_id', ''),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=f"Failed to initialize GitLab agent: {str(e)}",
                data={"action": "initialize"}
            )

    async def verify_connection(self) -> AgentResponse:
        """Verify the connection to GitLab API.
        
        Returns:
            AgentResponse: Contains the verification result
        """
        if not self.session:
            try:
                headers = {
                    "PRIVATE-TOKEN": self.access_token,
                    "Content-Type": "application/json"
                }
                self.session = aiohttp.ClientSession(headers=headers)
            except Exception as e:
                return AgentResponse(
                    id=str(id(self)),
                    type=AgentType.GITLAB,
                    name=self.name,
                    description=self.description,
                    status=AgentStatus.ERROR,
                    enabled=True,
                    config=self.config,
                    capabilities=[],
                    workspace_id="",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                    last_active_at=datetime.utcnow(),
                    error=f"Failed to create session: {str(e)}",
                    data={"status": "connection_failed"}
                )

        try:
            url = f"{self.base_url}/api/v4/user"
            async with self.session.get(url) as response:
                if response.status == 200:
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.GITLAB,
                        name=self.name,
                        description=self.description,
                        status=AgentStatus.ACTIVE,
                        enabled=True,
                        config=self.config,
                        capabilities=await self.get_capabilities(),
                        workspace_id="",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        last_active_at=datetime.utcnow(),
                        data={"status": "connected"}
                    )
                else:
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.GITLAB,
                        name=self.name,
                        description=self.description,
                        status=AgentStatus.ERROR,
                        enabled=True,
                        config=self.config,
                        capabilities=[],
                        workspace_id="",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        last_active_at=datetime.utcnow(),
                        error=f"Connection failed with status {response.status}",
                        data={"status": "connection_failed"}
                    )
        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITLAB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ERROR,
                enabled=True,
                config=self.config,
                capabilities=[],
                workspace_id="",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=f"Connection error: {str(e)}",
                data={"status": "connection_error"}
            )

    async def health_check(self) -> AgentResponse:
        """Check the health of the GitLab agent and its connection.
        
        Returns:
            AgentResponse: The health status of the agent
        """
        # Verify connection first
        connection = await self.verify_connection()
        if connection.status == AgentStatus.ERROR:
            return connection

        try:
            # Try to get a list of projects to verify full API access
            url = f"{self.base_url}/api/v4/projects?per_page=1"
            async with self.session.get(url) as response:
                if response.status == 200:
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.GITLAB,
                        name=self.name,
                        description=self.description,
                        status=AgentStatus.ACTIVE,
                        enabled=True,
                        config=self.config,
                        capabilities=await self.get_capabilities(),
                        workspace_id="",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        last_active_at=datetime.utcnow(),
                        data={"status": "healthy"}
                    )
                else:
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.GITLAB,
                        name=self.name,
                        description=self.description,
                        status=AgentStatus.ERROR,
                        enabled=True,
                        config=self.config,
                        capabilities=await self.get_capabilities(),
                        workspace_id="",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        last_active_at=datetime.utcnow(),
                        error=f"Health check failed with status {response.status}",
                        data={"status": "unhealthy"}
                    )
        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITLAB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ERROR,
                enabled=True,
                config=self.config,
                capabilities=await self.get_capabilities(),
                workspace_id="",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=f"Health check failed: {str(e)}",
                data={"status": "error"}
            )

    async def execute(self, action: str, **kwargs) -> AgentResponse:
        """Execute an action with the agent.
        
        Args:
            action: The action to execute (e.g., 'list_projects', 'get_file')
            **kwargs: Action-specific parameters
            
        Returns:
            AgentResponse: The result of the action
        """
        if not self._initialized:
            await self.initialize()

        action_handlers = {
            'list_projects': self._list_projects,
            'get_file': self._get_file,
            'list_files': self._list_files,
            'search_code': self._search_code
        }

        handler = action_handlers.get(action)
        if not handler:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITLAB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ERROR,
                enabled=True,
                config=self.config,
                capabilities=await self.get_capabilities(),
                workspace_id=kwargs.get('workspace_id', ''),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=f"Unknown action: {action}",
                data={"available_actions": list(action_handlers.keys())}
            )

        try:
            result = await handler(**kwargs)
            # Ensure the response has the required fields if not already set
            if not hasattr(result, 'id'):
                result.id = str(id(self))
            if not hasattr(result, 'type'):
                result.type = AgentType.GITLAB
            if not hasattr(result, 'name'):
                result.name = self.name
            if not hasattr(result, 'description'):
                result.description = self.description
            if not hasattr(result, 'enabled'):
                result.enabled = True
            if not hasattr(result, 'config'):
                result.config = self.config
            if not hasattr(result, 'capabilities'):
                result.capabilities = await self.get_capabilities()
            if not hasattr(result, 'workspace_id'):
                result.workspace_id = kwargs.get('workspace_id', '')
            if not hasattr(result, 'created_at'):
                result.created_at = datetime.utcnow()
            if not hasattr(result, 'updated_at'):
                result.updated_at = datetime.utcnow()
            if not hasattr(result, 'last_active_at'):
                result.last_active_at = datetime.utcnow()
            return result
        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITLAB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ERROR,
                enabled=True,
                config=self.config,
                capabilities=await self.get_capabilities(),
                workspace_id=kwargs.get('workspace_id', ''),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=f"Error executing {action}: {str(e)}",
                data={"action": action}
            )

    async def get_capabilities(self) -> list[Dict[str, str]]:
        """Return the capabilities of this agent.
        
        Returns:
            List[Dict[str, str]]: List of capabilities with name and description
        """
        return [
            {"name": "list_projects", "description": "List all accessible projects"},
            {"name": "get_file", "description": "Get file content from a repository"},
            {"name": "list_files", "description": "List files in a repository"},
            {"name": "search_code", "description": "Search code across repositories"}
        ]

    async def ingest_data(self, **kwargs) -> AgentResponse:
        """Ingest data from GitLab repositories.
        
        Args:
            **kwargs: Additional parameters for ingestion
                - project_id: Project ID or path (default: uses instance project_id)
                - path: Path within the repository (default: '')
                - recursive: Whether to include subdirectories (default: True)
                
        Returns:
            AgentResponse: Contains list of IngestedDocument in the data field
        """
        project_id = kwargs.get('project_id', self.project_id)
        if not project_id:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITLAB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ERROR,
                enabled=True,
                config=self.config,
                capabilities=await self.get_capabilities(),
                workspace_id=kwargs.get('workspace_id', ''),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error="Project ID is required for ingestion",
                data={"action": "ingest_data"}
            )

        path = kwargs.get('path', '')
        recursive = kwargs.get('recursive', True)

        try:
            # Get all files from the repository
            files = await self._list_files(project_id=project_id, path=path, recursive=recursive)

            # Convert to IngestedDocument format
            documents = []
            for file in files.get('items', []):
                if file.get('type') != 'blob':
                    continue

                try:
                    file_content = await self._get_file(project_id=project_id, file_path=file['path'])
                    if not hasattr(file_content, 'data') or not file_content.data.get('content'):
                        continue

                    file_path = file.get('path', '')
                    file_name = os.path.basename(file_path)
                    last_modified = file.get('last_commit_date', datetime.utcnow().isoformat())
                    
                    documents.append(IngestedDocument(
                        id=file['id'],
                        source_id=str(project_id),  # Using project_id as source_id
                        source_type=DocumentSourceType.GITLAB,
                        title=file_name,
                        content=file_content.data.get('content', ''),
                        created_at=datetime.fromisoformat(last_modified) if last_modified else datetime.utcnow(),
                        updated_at=datetime.fromisoformat(last_modified) if last_modified else datetime.utcnow(),
                        metadata={
                            'name': os.path.basename(file['path']),
                            'path': file['path'],
                            'size': file.get('size', 0),
                            'last_modified': file.get('last_commit_date')
                        }
                    ))
                except Exception as e:
                    logger.error(f"Failed to process file {file.get('path')}: {str(e)}")

            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITLAB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ACTIVE,
                enabled=True,
                config=self.config,
                capabilities=await self.get_capabilities(),
                workspace_id=kwargs.get('workspace_id', ''),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                data={"documents": documents}
            )

        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITLAB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ERROR,
                enabled=True,
                config=self.config,
                capabilities=await self.get_capabilities(),
                workspace_id=kwargs.get('workspace_id', ''),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=f"Failed to ingest data: {str(e)}",
                data={"documents": [], "action": "ingest_data"}
            )

    async def _list_projects(self, **kwargs) -> AgentResponse:
        """List all accessible projects.
        
        Args:
            **kwargs: Additional parameters
                - search: Search query
                - owned: Only show projects owned by the current user
                - membership: Only show projects the user is a member of
                
        Returns:
            AgentResponse: List of projects
        """
        params = {k: v for k, v in kwargs.items() if v is not None}
        url = f"{self.base_url}/api/v4/projects"

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    projects = await response.json()
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.GITLAB,
                        name=self.name,
                        description=self.description,
                        status=AgentStatus.ACTIVE,
                        enabled=True,
                        config=self.config,
                        capabilities=await self.get_capabilities(),
                        workspace_id=kwargs.get('workspace_id', ''),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        last_active_at=datetime.utcnow(),
                        data={"projects": projects}
                    )
                else:
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.GITLAB,
                        name=self.name,
                        description=self.description,
                        status=AgentStatus.ERROR,
                        enabled=True,
                        config=self.config,
                        capabilities=await self.get_capabilities(),
                        workspace_id=kwargs.get('workspace_id', ''),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        last_active_at=datetime.utcnow(),
                        error=f"Failed to list projects: {response.status}",
                        data={"status_code": response.status}
                    )
        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITLAB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ERROR,
                enabled=True,
                config=self.config,
                capabilities=await self.get_capabilities(),
                workspace_id=kwargs.get('workspace_id', ''),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=f"Error listing projects: {str(e)}",
                data={"action": "list_projects"}
            )

    async def _get_file(self, project_id: str, file_path: str, ref: str = 'main', **kwargs) -> AgentResponse:
        """Get file content from a repository.
        
        Args:
            project_id: Project ID or path
            file_path: Path to the file in the repository
            ref: Branch, tag or commit SHA (default: main)
            
        Returns:
            AgentResponse: File content and metadata
        """
        # URL-encode the file path
        encoded_path = file_path.replace('/', '%2F')
        url = f"{self.base_url}/api/v4/projects/{project_id}/repository/files/{encoded_path}"
        params = {
            'ref': ref
        }

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    file_data = await response.json()
                    # Decode base64 content
                    if 'content' in file_data:
                        file_data['content'] = base64.b64decode(file_data['content']).decode('utf-8')
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.GITLAB,
                        name=self.name,
                        description=self.description,
                        status=AgentStatus.ACTIVE,
                        enabled=True,
                        config=self.config,
                        capabilities=await self.get_capabilities(),
                        workspace_id=kwargs.get('workspace_id', ''),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        last_active_at=datetime.utcnow(),
                        data=file_data
                    )
                else:
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.GITLAB,
                        name=self.name,
                        description=self.description,
                        status=AgentStatus.ERROR,
                        enabled=True,
                        config=self.config,
                        capabilities=await self.get_capabilities(),
                        workspace_id=kwargs.get('workspace_id', ''),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        last_active_at=datetime.utcnow(),
                        error=f"Failed to get file: {response.status}",
                        data={"status_code": response.status}
                    )
        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITLAB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ERROR,
                enabled=True,
                config=self.config,
                capabilities=await self.get_capabilities(),
                workspace_id=kwargs.get('workspace_id', ''),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=f"Error getting file: {str(e)}",
                data={"action": "get_file", "project_id": project_id, "file_path": file_path}
            )

    async def _list_files(self, project_id: str, path: str = '', recursive: bool = True, **kwargs) -> AgentResponse:
        """List files in a repository.
        
        Args:
            project_id: Project ID or path
            path: Path within the repository (default: '')
            recursive: Whether to include subdirectories (default: True)
            
        Returns:
            AgentResponse: List of files and directories
        """
        url = f"{self.base_url}/api/v4/projects/{project_id}/repository/tree"
        params = {
            'path': path,
            'recursive': 'true' if recursive else 'false',
            'per_page': 100
        }

        try:
            all_items = []
            page = 1

            while True:
                params['page'] = page
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        items = await response.json()
                        if not items:
                            break

                        all_items.extend(items)

                        # Check if there are more pages
                        if 'x-next-page' not in response.headers:
                            break

                        page += 1
                    else:
                        return AgentResponse(
                            id=str(id(self)),
                            type=AgentType.GITLAB,
                            name=self.name,
                            description=self.description,
                            status=AgentStatus.ERROR,
                            enabled=True,
                            config=self.config,
                            capabilities=await self.get_capabilities(),
                            workspace_id=kwargs.get('workspace_id', ''),
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow(),
                            last_active_at=datetime.utcnow(),
                            error=f"Failed to list files: {response.status}",
                            data={"status_code": response.status}
                        )

            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITLAB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ACTIVE,
                enabled=True,
                config=self.config,
                capabilities=await self.get_capabilities(),
                workspace_id=kwargs.get('workspace_id', ''),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                data={"items": all_items}
            )

        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITLAB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ERROR,
                enabled=True,
                config=self.config,
                capabilities=await self.get_capabilities(),
                workspace_id=kwargs.get('workspace_id', ''),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=f"Error listing files: {str(e)}",
                data={"action": "list_files", "project_id": project_id, "path": path}
            )

    async def _search_code(self, search: str, project_id: str = None, **kwargs) -> AgentResponse:
        """Search code across repositories.
        
        Args:
            search: Search query
            project_id: Project ID or path (optional)
            
        Returns:
            AgentResponse: Search results
        """
        if project_id:
            url = f"{self.base_url}/api/v4/projects/{project_id}/search"
        else:
            url = f"{self.base_url}/api/v4/search"

        params = {
            'scope': 'blobs',  # Search in code
            'search': search,
            'per_page': 50
        }

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    results = await response.json()
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.GITLAB,
                        name=self.name,
                        description=self.description,
                        status=AgentStatus.ACTIVE,
                        enabled=True,
                        config=self.config,
                        capabilities=await self.get_capabilities(),
                        workspace_id=kwargs.get('workspace_id', ''),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        last_active_at=datetime.utcnow(),
                        data={"results": results}
                    )
                else:
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.GITLAB,
                        name=self.name,
                        description=self.description,
                        status=AgentStatus.ERROR,
                        enabled=True,
                        config=self.config,
                        capabilities=await self.get_capabilities(),
                        workspace_id=kwargs.get('workspace_id', ''),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        last_active_at=datetime.utcnow(),
                        error=f"Search failed with status {response.status}",
                        data={"status_code": response.status}
                    )
        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITLAB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ERROR,
                enabled=True,
                config=self.config,
                capabilities=await self.get_capabilities(),
                workspace_id=kwargs.get('workspace_id', ''),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=f"Error during search: {str(e)}",
                data={"action": "search_code", "search": search, "project_id": project_id}
            )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
            self.session = None
        self._initialized = False
