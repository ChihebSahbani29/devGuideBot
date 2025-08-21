import base64
import hashlib
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

import aiohttp

from config.dependencies import get_mcp_settings
from connectors.base_agent import BaseAgent
from schemas.agent import AgentType, AgentResponse, AgentStatus
from schemas.document import DocumentSourceType, IngestedDocument

logger = logging.getLogger(__name__)

# File extensions to include in ingestion
SUPPORTED_EXTENSIONS = {
    '.md', '.txt', '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp',
    '.h', '.hpp', '.go', '.rb', '.php', '.rs', '.swift', '.kt', '.dart', '.sh',
    '.yaml', '.yml', '.json', '.xml', '.html', '.css', '.scss', '.less'
}

# File patterns to exclude
EXCLUDE_PATTERNS = {
    'node_modules/', 'vendor/', 'dist/', 'build/', '__pycache__/', '.git/',
    '*.min.js', '*.min.css', '*.bundle.js', 'package-lock.json', 'yarn.lock',
    '*.log', '*.tmp', '*.swp', '*.swo', '.DS_Store', 'Thumbs.db'
}


class GitHubAgent(BaseAgent):
    """Agent for interacting with GitHub repositories"""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the GitHub agent with configuration
        
        Args:
            config: Configuration dictionary containing:
                - access_token: GitHub personal access token
                - default_owner: Default repository owner (optional)
                - default_repo: Default repository name (optional)
                - repositories: List of repositories in 'owner/repo' format (optional)
        """
        # Initialize with provided configuration
        # Ensure required fields are present
        if not config.get('access_token'):
            raise ValueError("GitHub access token is required in the configuration")
        
        super().__init__(
            name="github_agent",
            description="Agent for fetching and processing data from GitHub repositories",
            config=config
        )
        self._initialized = False

        self.access_token = config.get('access_token')
        self.default_owner = config.get('default_owner')
        self.default_repo = config.get('default_repo')
        self.repositories = config.get('repositories', [])
        self.source_type = AgentType.GITHUB

        # Get base URL from settings or use default
        self.settings = config.get('settings') or get_mcp_settings()
        self.base_url = self.settings.github.API_URL.rstrip('/')
        self.session = None

    async def verify_connection(self) -> AgentResponse:
        """Verify the connection to GitHub API.
        
        Returns:
            AgentResponse: Contains the verification result
        """
        if not self.session:
            try:
                headers = {
                    "Authorization": f"token {self.access_token}",
                    "Accept": "application/vnd.github.v3+json"
                }
                self.session = aiohttp.ClientSession(headers=headers)
            except Exception as e:
                return AgentResponse(
                    id=str(id(self)),
                    type=AgentType.GITHUB,
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
            url = f"{self.base_url}/user"
            async with self.session.get(url) as response:
                if response.status != 200:
                    error = await response.text()
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.GITHUB,
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
                        error=f"GitHub API error: {error}",
                        data={"status": "connection_failed"}
                    )
                
                return AgentResponse(
                    id=str(id(self)),
                    type=AgentType.GITHUB,
                    name=self.name,
                    description=self.description,
                    status=AgentStatus.ACTIVE,
                    enabled=True,
                    config=self.config,
                    capabilities=[],
                    workspace_id="",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                    last_active_at=datetime.utcnow(),
                    error=None,
                    data={"status": "connected"}
                )
                
        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITHUB,
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
                error=f"Connection verification failed: {str(e)}",
                data={"status": "connection_failed"}
            )

    async def initialize(self) -> AgentResponse:
        """Initialize the GitHub agent"""
        if self._initialized:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITHUB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ACTIVE,
                enabled=True,
                config=self.config,
                capabilities=[],
                workspace_id="",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=None,
                data={"status": "already_initialized"}
            )

        try:
            self.session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"token {self.access_token}",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            
            # Use verify_connection to test the connection
            verify_result = await self.verify_connection()
            if not verify_result.status == AgentStatus.ACTIVE:
                return verify_result
                
            self._initialized = True
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITHUB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ACTIVE,
                enabled=True,
                config=self.config,
                capabilities=await self._get_agent_capabilities(),
                workspace_id="",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=None,
                data={"status": "initialized"}
            )
        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITHUB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ERROR,
                enabled=False,
                config=self.config,
                capabilities=[],
                workspace_id="",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=f"Failed to initialize GitHub agent: {str(e)}",
                data={"status": "error"}
            )

    async def execute(self, action: str, **kwargs) -> AgentResponse:
        """Execute an action with the agent
        
        Args:
            action: The action to execute (e.g., 'ingest_data', 'search')
            **kwargs: Action-specific parameters
            
        Returns:
            AgentResponse: The result of the action
        """
        if not self._initialized:
            await self.initialize()
            

        try:
            if action == 'ingest_data':
                return await self.ingest_data(**kwargs)
            elif action == 'get_file':
                return await self.get_file_content(
                    path=kwargs.get('path'),
                    owner=kwargs.get('owner'),
                    repo=kwargs.get('repo'),
                    ref=kwargs.get('ref', 'main')
                )
            elif action == 'list_repositories':
                return await self.list_repositories(
                    owner=kwargs.get('owner')
                )
            elif action == 'search_code':
                return await self.search_code(
                    query=kwargs.get('query', ''),
                    owner=kwargs.get('owner'),
                    repo=kwargs.get('repo')
                )
            else:
                return AgentResponse(
                    id=str(id(self)),
                    type=AgentType.GITHUB,
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
                    error=f"Unknown action: {action}",
                    data={"action": action}
                )

        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITHUB,
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
                error=f"Error executing action {action}: {str(e)}",
                data={"action": action}
            )

    async def ingest_data(self, **kwargs) -> AgentResponse:
        """Ingest data from GitHub repositories"""
        try:
            documents = await self._ingest_data_impl(**kwargs)
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITHUB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ACTIVE,
                enabled=True,
                config=self.config,
                capabilities=[],
                workspace_id="",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=None,
                data={"documents": documents}
            )
        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITHUB,
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
                error=f"Error ingesting data: {str(e)}",
                data={"documents": []}
            )

    async def _ingest_data_impl(self, **kwargs) -> List[IngestedDocument]:
        """Implementation of data ingestion for GitHub repositories.
        
        Returns:
            List of IngestedDocument objects
        """
        if not self._initialized:
            init_result = await self.initialize()
            if init_result.status == AgentStatus.ERROR:
                raise Exception(f"Failed to initialize GitHub agent: {init_result.error}")
            self._initialized = True  # Mark as initialized after successful initialization

        owner = kwargs.get('owner', self.default_owner)
        repo = kwargs.get('repo', self.default_repo)
        ref = kwargs.get('ref', 'main')

        # If specific repositories are provided, use those
        repos_to_ingest = []
        if self.repositories:
            for repo_spec in self.repositories:
                if '/' in repo_spec:
                    repo_owner, repo_name = repo_spec.split('/', 1)
                    repos_to_ingest.append((repo_owner, repo_name))
        elif owner and repo:
            repos_to_ingest = [(owner, repo)]
        else:
            # If no specific repos, get all repos for the user/org
            repos = await self._get_all_repos(owner)
            repos_to_ingest = [(r['owner']['login'], r['name']) for r in repos]

        documents = []
        for repo_owner, repo_name in repos_to_ingest:
            try:
                # Get all files in the repository
                files = await self._get_repo_files(repo_owner, repo_name, ref)

                # Process each file
                for file_path, file_info in files.items():
                    try:
                        # Get file content
                        content = await self._get_file_content(
                            repo_owner,
                            repo_name,
                            file_path,
                            ref
                        )

                        if content:
                            # Create a document ID based on repo and file path
                            doc_id = hashlib.sha256(
                                f"{repo_owner}/{repo_name}/{file_path}".encode()
                            ).hexdigest()

                            # Create an IngestedDocument
                            doc = IngestedDocument(
                                id=doc_id,
                                source_id=f"{repo_owner}/{repo_name}",
                                source_type=DocumentSourceType.GITHUB,
                                title=file_path.split('/')[-1],
                                content=content,
                                url=f"https://github.com/{repo_owner}/{repo_name}/blob/{ref}/{file_path}",
                                metadata={
                                    'path': file_path,
                                    'repo': repo_name,
                                    'owner': repo_owner,
                                    'ref': ref,
                                    'size': file_info.get('size', 0),
                                    'sha': file_info.get('sha', '')
                                },
                                created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow()
                            )
                            documents.append(doc)

                    except Exception as e:
                        logger.error(f"Error processing file {file_path}: {str(e)}")
                        continue

            except Exception as e:
                logger.error(f"Error processing repo {repo_owner}/{repo_name}: {str(e)}")
                continue

        return documents

    async def _get_all_repos(self, owner: str) -> List[Dict]:
        """Get all repositories for a user or organization"""
        url = f"{self.base_url}/users/{owner}/repos" if '/' not in owner else f"{self.base_url}/orgs/{owner}/repos"
        all_repos = []
        page = 1
        per_page = 100

        while True:
            async with self.session.get(
                    url,
                    params={"per_page": per_page, "page": page, "type": "all"}
            ) as response:
                if response.status == 200:
                    repos = await response.json()
                    if not repos:
                        break
                    all_repos.extend(repos)
                    if len(repos) < per_page:
                        break
                    page += 1
                else:
                    response.raise_for_status()

        return all_repos

    async def _get_repo_files(self, owner: str, repo: str, ref: str) -> Dict[str, Dict]:
        """Get all files in a repository recursively"""
        files = {}
        queue = [""]  # Start with root directory

        while queue:
            current_path = queue.pop(0)
            url = f"{self.base_url}/repos/{owner}/{repo}/contents/{current_path}"

            async with self.session.get(url, params={"ref": ref}) as response:
                if response.status == 200:
                    items = await response.json()

                    for item in items:
                        item_path = item['path']

                        # Skip excluded patterns
                        if any(item_path.startswith(p) for p in EXCLUDE_PATTERNS):
                            continue

                        if item['type'] == 'file':
                            # Check file extension
                            if any(item_path.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
                                files[item_path] = {
                                    'sha': item['sha'],
                                    'size': item['size'],
                                    'url': item['html_url']
                                }
                        elif item['type'] == 'dir':
                            queue.append(item_path)

        return files

    async def _get_file_content(self, owner: str, repo: str, path: str, ref: str) -> Optional[str]:
        """Get the content of a file"""
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"

        async with self.session.get(url, params={"ref": ref}) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('type') == 'file' and data.get('content'):
                    # Decode base64 content
                    return base64.b64decode(data['content']).decode('utf-8', errors='ignore')
        return None

    async def get_file_content(self, path: str, owner: str, repo: str, ref: str = 'main') -> AgentResponse:
        """Get the content of a file from a GitHub repository"""
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"
        params = {"ref": ref} if ref else {}

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    file_data = await response.json()
                    if "content" in file_data:
                        # Decode base64 content
                        content = base64.b64decode(file_data["content"]).decode('utf-8')
                        return AgentResponse(
                            id=str(id(self)),
                            type=AgentType.GITHUB,
                            name=self.name,
                            description=self.description,
                            status=AgentStatus.ACTIVE,
                            enabled=True,
                            config=self.config,
                            capabilities=[],
                            workspace_id="",
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow(),
                            last_active_at=datetime.utcnow(),
                            error=None,
                            data={
                                "content": content,
                                "path": file_data["path"],
                                "sha": file_data["sha"],
                                "size": file_data["size"],
                                "html_url": file_data["html_url"]
                            }
                        )
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.GITHUB,
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
                        error="File content not found in response",
                        data={"content": "", "path": path}
                    )
                else:
                    error = await response.text()
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.GITHUB,
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
                        error=f"Failed to get file content: {error}",
                        data={"content": "", "path": path}
                    )
        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITHUB,
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
                error=f"Error getting file content: {str(e)}",
                data={"content": "", "path": path}
            )

    async def list_repositories(self, owner: str) -> AgentResponse:
        """List repositories for a user or organization"""
        url = f"{self.base_url}/users/{owner}/repos" if owner else f"{self.base_url}/user/repos"

        try:
            async with self.session.get(url, params={"per_page": 100}) as response:
                if response.status == 200:
                    repos = await response.json()
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.GITHUB,
                        name=self.name,
                        description=self.description,
                        status=AgentStatus.ACTIVE,
                        enabled=True,
                        config=self.config,
                        capabilities=[],
                        workspace_id="",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        last_active_at=datetime.utcnow(),
                        error=None,
                        data={
                            "repositories": [{
                                "name": repo["name"],
                                "full_name": repo["full_name"],
                                "description": repo["description"],
                                "html_url": repo["html_url"],
                                "language": repo["language"],
                                "stargazers_count": repo["stargazers_count"]
                            } for repo in repos]
                        }
                    )
                else:
                    error = await response.text()
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.GITHUB,
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
                        error=f"Failed to list repositories: {error}",
                        data={"repositories": []}
                    )
        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITHUB,
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
                error=f"Error listing repositories: {str(e)}",
                data={"repositories": []}
            )

    async def search_code(self, query: str, owner: str | None = None, repo: str | None = None) -> AgentResponse:
        """Search code in GitHub repositories"""
        search_query = []
        if owner:
            search_query.append(f"user:{owner}")
        if repo:
            search_query.append(f"repo:{owner}/{repo}" if owner else f"repo:{repo}")
        search_query.append(query)

        url = f"{self.base_url}/search/code"
        params = {"q": " ".join(search_query)}

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    results = await response.json()
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.GITHUB,
                        name=self.name,
                        description=self.description,
                        status=AgentStatus.ACTIVE,
                        enabled=True,
                        config=self.config,
                        capabilities=[],
                        workspace_id="",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        last_active_at=datetime.utcnow(),
                        error=None,
                        data={
                            "total_count": results["total_count"],
                            "items": [{
                                "name": item["name"],
                                "path": item["path"],
                                "html_url": item["html_url"],
                                "repository": item["repository"]["full_name"],
                                "score": item["score"]
                            } for item in results["items"]]
                        }
                    )
                else:
                    error = await response.text()
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.GITHUB,
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
                        error=f"Code search failed: {error}",
                        data={"total_count": 0, "items": []}
                    )
        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITHUB,
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
                error=f"Error performing code search: {str(e)}",
                data={"total_count": 0, "items": []}
            )

    async def health_check(self) -> AgentResponse:
        """Check the health of the agent"""
        if self.initialized:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.GITHUB,
                name=self.name,
                description=self.description,
                status=AgentStatus.ACTIVE if self.initialized else AgentStatus.INACTIVE,
                enabled=True,
                config=self.config,
                capabilities=[],
                workspace_id="",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=None,
                data={"status": "healthy" if self.initialized else "unhealthy"}
            )
        return AgentResponse(
            id=str(id(self)),
            type=AgentType.GITHUB,
            name=self.name,
            description=self.description,
            status=AgentStatus.ERROR,
            enabled=False,
            config={},
            capabilities=[],
            workspace_id="",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            last_active_at=datetime.utcnow(),
            error="Agent not initialized",
            data={"status": "uninitialized"}
        )

    async def get_capabilities(self) -> AgentResponse:
        """Return the capabilities of this agent"""
        capabilities = [
            {"name": "get_file", "description": "Get the content of a file from a repository"},
            {"name": "list_repositories", "description": "List repositories for a user or organization"},
            {"name": "search_code", "description": "Search code across repositories"}
        ]
        return AgentResponse(
            id=str(id(self)),
            type=AgentType.GITHUB,
            name=self.name,
            description=self.description,
            status=AgentStatus.ACTIVE if self.initialized else AgentStatus.INACTIVE,
            enabled=True,
            config=self.config,
            capabilities=capabilities,
            workspace_id="",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            last_active_at=datetime.utcnow(),
            error=None,
            data={"capabilities": capabilities}
        )

    async def close(self):
        """Clean up resources"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def __del__(self):
        """Ensure session is closed when the agent is destroyed"""
        if hasattr(self, 'session') and self.session and not self.session.closed:
            import asyncio
            asyncio.create_task(self.close())
