import logging
from typing import Optional, Any, Dict

from chunkers.code_chunker import CodeChunker
from fastapi import Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis

from chunkers.config_chunker import ConfigChunker
from chunkers.markdown_chunker import MarkdownChunker
from config.connectors_settings import MCPSettings
from config.settings import settings
from connectors.ai_agents.chat_agent import ChatAgent
from connectors.ai_agents.embedding_agent import EmbeddingAgent
from db.mongo import MongoDatabase
from db.redis import RedisDatabase
from parsers.code_parser import CodeParser
from parsers.config_parser import ConfigParser
from parsers.issue_parser import IssueParser
from parsers.markdown_parser import MarkdownParser
from repositories.agent import AgentRepository
from repositories.conversation import ConversationRepository
from repositories.document import DocumentRepository
from repositories.workspace import WorkspaceRepository
from services.agent import AgentService
from services.conversation import ConversationService
from services.document import DocumentService
from services.parser import ParserService
from services.workspace import WorkspaceService

logger = logging.getLogger(__name__)

async def get_mongo_client() -> AsyncIOMotorClient:
    """Get MongoDB client instance."""
    return AsyncIOMotorClient(settings.MONGO_URI)


async def get_redis_client() -> Redis:
    """Get Redis client instance."""
    return Redis.from_url(settings.REDIS_URL)


def get_mongo_db(client: AsyncIOMotorClient = Depends(get_mongo_client)) -> MongoDatabase:
    """Get configured MongoDB instance."""
    return MongoDatabase(client)


def get_redis_db(client: Redis = Depends(get_redis_client)) -> RedisDatabase:
    """Get configured Redis instance."""
    return RedisDatabase(client)


def get_workspace_repository(
        db: MongoDatabase = Depends(get_mongo_db)
) -> WorkspaceRepository:
    """Get workspace repository instance."""
    return WorkspaceRepository(db.get_collection("workspaces"))


def get_conversation_repository(
        db: MongoDatabase = Depends(get_mongo_db)
) -> ConversationRepository:
    """Get conversation repository instance."""
    return ConversationRepository(db.get_collection("conversations"))


def get_conversation_service(
        repo: ConversationRepository = Depends(get_conversation_repository)
) -> ConversationService:
    """Get conversation service instance."""
    return ConversationService(repo, chat_agent=get_chat_agent())


def get_agent_repository(
        db: MongoDatabase = Depends(get_mongo_db)
) -> AgentRepository:
    """Get agent repository instance."""
    return AgentRepository(db.get_collection("agents"))


def get_document_repository(
        db: MongoDatabase = Depends(get_mongo_db)
) -> DocumentRepository:
    """Get document repository instance."""
    return DocumentRepository(db.get_collection("documents"))


def get_embedding_agent() -> Optional[EmbeddingAgent]:
    """Get EmbeddingAgent instance if OpenAI API key is configured."""
    if not settings.openai.api_key:
        
        logger.warning("OpenAI API key not configured. Embedding functionality will be disabled.")
        return None
    
    return EmbeddingAgent(
        api_key=settings.openai.api_key,
        model=getattr(settings.openai, 'OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small'),
        batch_size=getattr(settings.openai, 'OPENAI_EMBEDDING_BATCH_SIZE', 32)
    )


def get_chat_agent(
    embedding_agent: Optional[EmbeddingAgent] = Depends(get_embedding_agent)
) -> Optional[ChatAgent]:
    """Get ChatAgent instance if OpenAI API key is configured.
    
    Args:
        embedding_agent: Optional embedding agent for document retrieval
        
    Returns:
        Configured ChatAgent instance or None if not configured
    """
    if not settings.openai.api_key:
        
        logger.warning("OpenAI API key not configured. Chat functionality will be disabled.")
        return None
    
    try:
        return ChatAgent(
            api_key=settings.openai.api_key,
            model=getattr(settings.openai, 'OPENAI_CHAT_MODEL', 'gpt-4-turbo-preview'),
            temperature=float(getattr(settings.openai, 'OPENAI_TEMPERATURE', 0.7)),
            max_tokens=int(getattr(settings.openai, 'OPENAI_MAX_TOKENS', 0)) or None,
            system_message=getattr(settings.openai, 'OPENAI_SYSTEM_MESSAGE', None)
        )
    except Exception as e:
        
        logger.error(f"Failed to initialize ChatAgent: {str(e)}")
        return None


def get_code_parser() -> CodeParser:
    """Get CodeParser instance."""
    return CodeParser()


def get_config_parser() -> ConfigParser:
    """Get ConfigParser instance."""
    return ConfigParser()


def get_issue_parser() -> IssueParser:
    """Get IssueParser instance."""
    return IssueParser()


def get_markdown_parser() -> MarkdownParser:
    """Get MarkdownParser instance."""
    return MarkdownParser()


def get_parsers(
    code_parser: CodeParser = Depends(get_code_parser),
    config_parser: ConfigParser = Depends(get_config_parser),
    issue_parser: IssueParser = Depends(get_issue_parser),
    markdown_parser: MarkdownParser = Depends(get_markdown_parser)
) -> Dict[str, Any]:
    """Get all available parsers."""
    return {
        'code': code_parser,
        'config': config_parser,
        'issue': issue_parser,
        'markdown': markdown_parser
    }


def get_code_chunker() -> CodeChunker:
    """Get CodeChunker instance."""
    return CodeChunker()


def get_config_chunker() -> ConfigChunker:
    """Get ConfigChunker instance."""
    return ConfigChunker()


def get_markdown_chunker() -> MarkdownChunker:
    """Get MarkdownChunker instance."""
    return MarkdownChunker()


def get_chunkers(
    code_chunker: CodeChunker = Depends(get_code_chunker),
    config_chunker: ConfigChunker = Depends(get_config_chunker),
    markdown_chunker: MarkdownChunker = Depends(get_markdown_chunker)
) -> Dict[str, Any]:
    """Get all available chunkers."""
    return {
        'code': code_chunker,
        'config': config_chunker,
        'markdown': markdown_chunker
    }


def get_document_service(
    repo: DocumentRepository = Depends(get_document_repository),
    redis_db: RedisDatabase = Depends(get_redis_db),
    embedding_agent: Optional[EmbeddingAgent] = Depends(get_embedding_agent),
    parsers: Dict[str, Any] = Depends(get_parsers),
    chunkers: Dict[str, Any] = Depends(get_chunkers)
) -> DocumentService:
    """Get document service instance with optional embedding support, parsers, and chunkers."""
    return DocumentService(
        repo=repo,
        redis_db=redis_db,
        embedding_agent=embedding_agent,
        parsers=parsers,
        chunkers=chunkers
    )


def get_agent_service(
        repo: AgentRepository = Depends(get_agent_repository),
        document_service: DocumentService = Depends(get_document_service)
) -> AgentService:
    """Get agent service instance."""
    return AgentService(repo, document_service)


def get_parser_service(
    parsers: Dict[str, Any] = Depends(get_parsers),
    chunkers: Dict[str, Any] = Depends(get_chunkers)
) -> ParserService:
    """Get parser service instance for testing parsers and chunkers."""
    return ParserService(parsers=parsers, chunkers=chunkers)


def get_workspace_service(
        repo: WorkspaceRepository = Depends(get_workspace_repository),
        agent_service: AgentService = Depends(get_agent_service)
) -> WorkspaceService:
    """Get workspace service instance."""
    return WorkspaceService(repo=repo, agent_service=agent_service)


# Initialize settings instances
mcp_settings = MCPSettings()


def get_mcp_settings() -> MCPSettings:
    """
    Get MCP settings with proper error handling.
    This will be used as a dependency in FastAPI routes.
    
    Returns:
        MCPSettings: The initialized MCP settings instance
        
    Raises:
        HTTPException: If there's an error loading the settings
    """
    global mcp_settings
    if not mcp_settings:
        try:
            mcp_settings = MCPSettings()
        except Exception as e:
            
            logger.error(f"Error loading MCP settings: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to load MCP settings: {str(e)}"
            )
    return mcp_settings


def get_sharepoint_config(settings: MCPSettings = Depends(get_mcp_settings)):
    """Get SharePoint configuration."""
    return settings.sharepoint


def get_github_config(settings: MCPSettings = Depends(get_mcp_settings)):
    """Get GitHub configuration."""
    return settings.github
