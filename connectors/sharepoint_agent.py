import os
from datetime import datetime
from typing import Dict, Any, List, Optional
import aiohttp
import logging
from urllib.parse import urlparse

from config.dependencies import get_mcp_settings
from connectors.base_agent import BaseAgent
from schemas.agent import AgentType, AgentResponse, AgentStatus
from schemas.document import DocumentSourceType, IngestedDocument

logger = logging.getLogger(__name__)


class SharePointAgent(BaseAgent):
    """Agent for interacting with Microsoft SharePoint"""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the SharePoint agent with configuration

        Args:
            config: Configuration dictionary containing:
                - tenant_id: Azure AD tenant ID
                - client_id: Application (client) ID
                - client_secret: Client secret for the application
                - site_url: Full URL of the SharePoint site
                - site_id: ID of the SharePoint site
                - site_name: Name of the SharePoint site
        """
        # Ensure required fields are present
        required_fields = ['tenant_id', 'client_id', 'client_secret', 'site_url']
        for field in required_fields:
            if not config.get(field):
                raise ValueError(f"SharePoint {field.replace('_', ' ')} is required in the configuration")

        super().__init__(
            name="sharepoint_agent",
            description="Agent for fetching and processing data from SharePoint",
            config=config
        )
        self._initialized = False

        self.tenant_id = config['tenant_id']
        self.client_id = config['client_id']
        self.client_secret = config['client_secret']
        self.site_url = config['site_url'].rstrip('/')
        self.site_id = config.get('site_id')
        self.site_name = config.get('site_name') or self._extract_site_name()
        self.source_type = AgentType.SHAREPOINT

        # Get base URL from settings or use defaults
        self.settings = config.get('settings') or get_mcp_settings()
        self.graph_url = "https://graph.microsoft.com/v1.0"
        self.session = None
        self.access_token = None

    def _extract_site_name(self) -> str:
        """Extract site name from site URL if not provided"""
        try:
            # Example: https://contoso.sharepoint.com/sites/mysite
            parsed = urlparse(self.site_url)
            # Get the last part of the path
            return parsed.path.split('/')[-1]
        except Exception as e:
            logger.warning(f"Could not extract site name from URL: {e}")
            return "sharepoint_site"

    async def health_check(self) -> AgentResponse:
        """Check the health of the SharePoint agent and its connection.
        
        Returns:
            AgentResponse: The health status of the agent
        """
        try:
            # Verify connection first
            connection = await self.verify_connection()
            if not connection.success:
                return connection
                
            # Try to make a simple API call to verify everything is working
            async with self.session.get(f"{self.graph_url}/sites/{self.site_id or self.site_name}") as response:
                if response.status == 200:
                    return AgentResponse(
                        success=True,
                        status=AgentStatus.ACTIVE,
                        data={"status": "healthy"}
                    )
                else:
                    return AgentResponse(
                        success=False,
                        status=AgentStatus.ERROR,
                        error=f"Health check failed with status {response.status}",
                        data={"status": "unhealthy"}
                    )
        except Exception as e:
            return AgentResponse(
                success=False,
                status=AgentStatus.ERROR,
                error=f"Health check failed: {str(e)}",
                data={"status": "error"}
            )

    async def ingest_data(self, **kwargs) -> AgentResponse:
        """Ingest data from SharePoint.
        
        Args:
            **kwargs: Additional parameters for ingestion
                - path: Optional path within the SharePoint site to ingest from
                - recursive: Whether to ingest recursively (default: True)
                
        Returns:
            AgentResponse: Contains list of IngestedDocument in the data field
        """
        try:
            # Verify connection first
            connection = await self.verify_connection()
            if not connection.success:
                return connection
                
            path = kwargs.get('path', '/')
            recursive = kwargs.get('recursive', True)
            
            # Get all files from the specified path
            files = await self._list_files(path, recursive=recursive)
            
            # Convert to IngestedDocument format
            documents = []
            for file in files:
                try:
                    content = await self._get_file_content(file['id'])
                    file_name = os.path.basename(file.get('name', 'document'))
                    last_modified = file.get('lastModifiedDateTime', datetime.utcnow().isoformat())
                    
                    documents.append(IngestedDocument(
                        id=file['id'],
                        source_id=file.get('parentReference', {}).get('siteId', 'sharepoint'),
                        source_type=DocumentSourceType.SHAREPOINT,
                        title=file_name,
                        content=content,
                        created_at=datetime.fromisoformat(last_modified.rstrip('Z')) if last_modified else datetime.utcnow(),
                        updated_at=datetime.fromisoformat(last_modified.rstrip('Z')) if last_modified else datetime.utcnow(),
                        metadata={
                            'name': file.get('name'),
                            'path': file.get('path'),
                            'size': file.get('size'),
                            'last_modified': file.get('lastModifiedDateTime')
                        }
                    ))
                except Exception as e:
                    logger.error(f"Failed to process file {file.get('id')}: {str(e)}")
            
            return AgentResponse(
                success=True,
                status=AgentStatus.ACTIVE,
                data={"documents": documents}
            )
            
        except Exception as e:
            return AgentResponse(
                success=False,
                status=AgentStatus.ERROR,
                error=f"Failed to ingest data: {str(e)}",
                data={"documents": []}
            )

    async def verify_connection(self) -> AgentResponse:
        """Verify the connection to SharePoint API.

        Returns:
            AgentResponse: Contains the verification result
        """
        if not self.session:
            try:
                self.access_token = await self._get_access_token()
                headers = {
                    "Authorization": f"Bearer {self.access_token}",
                    "Accept": "application/json"
                }
                self.session = aiohttp.ClientSession(headers=headers)
            except Exception as e:
                return AgentResponse(
                    id=str(id(self)),
                    type=AgentType.SHAREPOINT,
                    name=self.name,
                    description=self.description,
                    status=AgentStatus.ERROR,
                    enabled=True,
                    config={k: '***' if k in ['client_secret', 'access_token'] else v
                            for k, v in self.config.items()},
                    capabilities=[],
                    workspace_id="",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                    last_active_at=datetime.utcnow(),
                    error=f"Failed to create session: {str(e)}",
                    data={"status": "connection_failed"}
                )

        try:
            # Test connection by getting site information
            site_id = self.site_id or await self._get_site_id()
            if not site_id:
                raise ValueError("Could not determine site ID")

            url = f"{self.graph_url}/sites/{site_id}"
            async with self.session.get(url) as response:
                if response.status != 200:
                    error = await response.text()
                    raise Exception(f"Failed to verify connection: {error}")

                return AgentResponse(
                    id=str(id(self)),
                    type=AgentType.SHAREPOINT,
                    name=self.name,
                    description=self.description,
                    status=AgentStatus.ACTIVE,
                    enabled=True,
                    config={k: '***' if k in ['client_secret', 'access_token'] else v
                            for k, v in self.config.items()},
                    capabilities=[],
                    workspace_id="",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                    last_active_at=datetime.utcnow(),
                    error=None,
                    data={"status": "connection_success"}
                )
        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.SHAREPOINT,
                name=self.name,
                description=self.description,
                status=AgentStatus.ERROR,
                enabled=True,
                config={k: '***' if k in ['client_secret', 'access_token'] else v
                        for k, v in self.config.items()},
                capabilities=[],
                workspace_id="",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=f"Connection verification failed: {str(e)}",
                data={"status": "connection_failed"}
            )

    async def _get_access_token(self) -> str:
        """Get access token for Microsoft Graph API"""
        if not self.session:
            self.session = aiohttp.ClientSession()

        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"

        data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': 'https://graph.microsoft.com/.default'
        }

        async with self.session.post(token_url, data=data) as response:
            if response.status == 200:
                token_data = await response.json()
                return token_data.get('access_token')
            else:
                error = await response.text()
                raise Exception(f"Failed to get access token: {error}")

    async def _get_site_id(self) -> str:
        """Get the site ID using the site URL"""
        if not self.site_url:
            raise ValueError("Site URL is required to get site ID")

        # URL encode the site URL
        from urllib.parse import quote
        encoded_site_url = quote(self.site_url, safe='')

        url = f"{self.graph_url}/sites/{encoded_site_url}"

        async with self.session.get(
                url,
                headers={"Authorization": f"Bearer {self.access_token}"}
        ) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('id')
            else:
                error = await response.text()
                raise Exception(f"Failed to get site ID: {error}")

    async def initialize(self) -> AgentResponse:
        """Initialize the SharePoint agent"""
        try:
            if not self._initialized:
                verify_result = await self.verify_connection()
                if verify_result.status != AgentStatus.ACTIVE:
                    return verify_result

                self._initialized = True

            return AgentResponse(
                id=str(id(self)),
                type=AgentType.SHAREPOINT,
                name=self.name,
                description=self.description,
                status=AgentStatus.ACTIVE,
                enabled=True,
                config={k: '***' if k in ['client_secret', 'access_token'] else v
                        for k, v in self.config.items()},
                capabilities=[],
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
                type=AgentType.SHAREPOINT,
                name=self.name,
                description=self.description,
                status=AgentStatus.ERROR,
                enabled=True,
                config={k: '***' if k in ['client_secret', 'access_token'] else v
                        for k, v in self.config.items()},
                capabilities=[],
                workspace_id="",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=f"Failed to initialize SharePoint agent: {str(e)}",
                data={"status": "initialization_failed"}
            )

    async def execute(self, query: str, **kwargs) -> AgentResponse:
        """Execute a query against SharePoint"""
        if not self._initialized:
            init_result = await self.initialize()
            if init_result.status != AgentStatus.ACTIVE:
                return init_result

        try:
            if "list documents" in query.lower():
                return await self._list_documents(
                    site_id=self.site_id or await self._get_site_id(),
                    list_id=kwargs.get('list_id', 'documents')  # Default to documents library
                )
            elif "search" in query.lower():
                return await self._search_sharepoint(
                    search_text=kwargs.get('search_text', ''),
                    **kwargs
                )
            else:
                return AgentResponse(
                    id=str(id(self)),
                    type=AgentType.SHAREPOINT,
                    name=self.name,
                    description=self.description,
                    status=AgentStatus.ERROR,
                    enabled=True,
                    config={k: '***' if k in ['client_secret', 'access_token'] else v
                            for k, v in self.config.items()},
                    capabilities=[],
                    workspace_id="",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                    last_active_at=datetime.utcnow(),
                    error=f"Unsupported query: {query}",
                    data={"status": "unsupported_query"}
                )
        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.SHAREPOINT,
                name=self.name,
                description=self.description,
                status=AgentStatus.ERROR,
                enabled=True,
                config={k: '***' if k in ['client_secret', 'access_token'] else v
                        for k, v in self.config.items()},
                capabilities=[],
                workspace_id="",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=f"Error executing SharePoint query: {str(e)}",
                data={"status": "execution_failed"}
            )

    async def _list_documents(self, site_id: str, list_id: str) -> AgentResponse:
        """List documents in a SharePoint list"""
        url = f"{self.graph_url}/sites/{site_id}/lists/{list_id}/items?expand=fields"

        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.SHAREPOINT,
                        name=self.name,
                        description=self.description,
                        status=AgentStatus.ACTIVE,
                        enabled=True,
                        config={k: '***' if k in ['client_secret', 'access_token'] else v
                                for k, v in self.config.items()},
                        capabilities=[],
                        workspace_id="",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        last_active_at=datetime.utcnow(),
                        error=None,
                        data=data
                    )
                else:
                    error = await response.text()
                    raise Exception(f"Failed to list documents: {error}")
        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.SHAREPOINT,
                name=self.name,
                description=self.description,
                status=AgentStatus.ERROR,
                enabled=True,
                config={k: '***' if k in ['client_secret', 'access_token'] else v
                        for k, v in self.config.items()},
                capabilities=[],
                workspace_id="",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=f"Error listing documents: {str(e)}",
                data={"status": "list_documents_failed"}
            )

    async def _search_sharepoint(self, search_text: str, **kwargs) -> AgentResponse:
        """Search for content in SharePoint"""
        url = f"{self.graph_url}/search/query"

        request_body = {
            "requests": [
                {
                    "entityTypes": ["listItem"],
                    "query": {
                        "queryString": search_text
                    },
                    "fields": ["title", "webUrl", "lastModifiedDateTime", "createdBy"]
                }
            ]
        }

        try:
            async with self.session.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json"
                    },
                    json=request_body
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return AgentResponse(
                        id=str(id(self)),
                        type=AgentType.SHAREPOINT,
                        name=self.name,
                        description=self.description,
                        status=AgentStatus.ACTIVE,
                        enabled=True,
                        config={k: '***' if k in ['client_secret', 'access_token'] else v
                                for k, v in self.config.items()},
                        capabilities=[],
                        workspace_id="",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        last_active_at=datetime.utcnow(),
                        error=None,
                        data=data
                    )
                else:
                    error = await response.text()
                    raise Exception(f"Search failed: {error}")
        except Exception as e:
            return AgentResponse(
                id=str(id(self)),
                type=AgentType.SHAREPOINT,
                name=self.name,
                description=self.description,
                status=AgentStatus.ERROR,
                enabled=True,
                config={k: '***' if k in ['client_secret', 'access_token'] else v
                        for k, v in self.config.items()},
                capabilities=[],
                workspace_id="",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                error=f"Error searching SharePoint: {str(e)}",
                data={"status": "search_failed"}
            )

    async def get_capabilities(self) -> AgentResponse:
        """Get the capabilities of the SharePoint agent"""
        return AgentResponse(
            id=str(id(self)),
            type=AgentType.SHAREPOINT,
            name=self.name,
            description=self.description,
            status=AgentStatus.ACTIVE,
            enabled=True,
            config={k: '***' if k in ['client_secret', 'access_token'] else v
                    for k, v in self.config.items()},
            capabilities=[],
            workspace_id="",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            last_active_at=datetime.utcnow(),
            error=None,
            data={
                "name": self.name,
                "description": self.description,
                "capabilities": [
                    "list_documents: List documents in a SharePoint list",
                    "search: Search for content across SharePoint",
                    "get_file: Download a file from SharePoint"
                ]
            }
        )

    async def close(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()
            self.session = None

    def __del__(self):
        """Ensure session is closed when the agent is destroyed"""
        if hasattr(self, 'session') and self.session and not self.session.closed:
            import asyncio
            asyncio.create_task(self.close())