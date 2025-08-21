"""Configuration settings for MCP (Multi-Agent Collaboration Protocol) agents.

This module provides configuration management for all MCP agents, including API keys,
authentication details, and other agent-specific settings. It supports loading
configuration from environment variables and .env files.
"""
import os
from typing import Optional, Dict, Any
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class SharePointSettings(BaseSettings):
    """Configuration for SharePoint agent."""
    ENABLED: bool = False
    TENANT_ID: Optional[str] = Field(None, description="Azure AD tenant ID for SharePoint authentication")
    CLIENT_ID: Optional[str] = Field(None, description="Application (client) ID for SharePoint")
    CLIENT_SECRET: Optional[str] = Field(None, description="Client secret for SharePoint application")
    SITE_NAME: Optional[str] = Field(None, description="Name of the SharePoint site")
    SITE_ID: Optional[str] = Field(None, description="ID of the SharePoint site")
    
    class Config:
        env_prefix = "SHAREPOINT_"
        env_file = ".env"
        extra = "ignore"


class GitHubSettings(BaseSettings):
    """Configuration for GitHub agent."""
    ENABLED: bool = False
    ACCESS_TOKEN: Optional[str] = Field(None, description="GitHub personal access token")
    DEFAULT_OWNER: Optional[str] = Field(None, description="Default repository owner (username or org)")
    DEFAULT_REPO: Optional[str] = Field(None, description="Default repository name")
    API_URL: str = "https://api.github.com"
    
    class Config:
        env_prefix = "GITHUB_"
        env_file = ".env"
        extra = "ignore"


class GitLabSettings(BaseSettings):
    """Configuration for GitLab agent."""
    ENABLED: bool = False
    ACCESS_TOKEN: Optional[str] = Field(None, description="GitLab personal access token")
    DEFAULT_OWNER: Optional[str] = Field(None, description="Default repository owner (username or group)")
    DEFAULT_REPO: Optional[str] = Field(None, description="Default repository name")
    PROJECT_ID: Optional[str] = Field(None, description="Default project ID or path")
    API_URL: str = "https://gitlab.com/api/v4"
    
    class Config:
        env_prefix = "GITLAB_"
        env_file = ".env"
        extra = "ignore"


class MCPSettings(BaseSettings):
    """Main configuration for MCP agents."""
    # Agent settings
    mcp_log_level: str = "INFO"
    mcp_debug: bool = False
    
    # Individual agent configurations
    sharepoint: SharePointSettings = Field(default_factory=SharePointSettings)
    github: GitHubSettings = Field(default_factory=GitHubSettings)
    gitlab: GitLabSettings = Field(default_factory=GitLabSettings)
    
    # Agent registry - maps agent names to their configuration
    agent_registry: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Registry of available agents and their configurations"
    )
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
        env_file_encoding="utf-8",
        env_prefix="mcp_"
    )
    
    @model_validator(mode='before')
    @classmethod
    def build_from_env(cls, values):
        # Handle nested settings
        if 'sharepoint' not in values:
            values['sharepoint'] = SharePointSettings()
        if 'github' not in values:
            values['github'] = GitHubSettings()
        if 'gitlab' not in values:
            values['gitlab'] = GitLabSettings()
        return values
    
    @model_validator(mode='after')
    def build_agent_registry(self) -> 'MCPSettings':
        """Build the agent registry for all available agents."""
        self.agent_registry = {
            "sharepoint": {
                "module": "connectors.sharepoint_agent",
                "class": "SharePointAgent"
            },
            "github": {
                "module": "connectors.github_agent",
                "class": "GitHubAgent"
            },
            "gitlab": {
                "module": "connectors.gitlab_agent",
                "class": "GitLabAgent"
            }
        }
        return self


