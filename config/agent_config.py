"""Agent configuration utilities for MCP agents.

This module provides utilities for loading and managing agent configurations,
including dynamic agent class loading and initialization.
"""
import asyncio
import importlib
import logging
from typing import Any, Dict, Type, Optional, TypeVar, Awaitable

from config.connectors_settings import MCPSettings

logger = logging.getLogger(__name__)

T = TypeVar('T')


class AgentConfigError(Exception):
    """Base exception for agent configuration errors."""
    pass


def import_agent_class(module_path: str, class_name: str) -> Type:
    """Dynamically import an agent class.
    
    Args:
        module_path: The full module path (e.g., 'connectors.github_agent')
        class_name: The name of the class to import (e.g., 'GitHubAgent')
        
    Returns:
        The imported class
        
    Raises:
        AgentConfigError: If the module or class cannot be imported
    """
    try:
        module = importlib.import_module(module_path)
        agent_class = getattr(module, class_name, None)
        if agent_class is None:
            raise AttributeError(f"Class {class_name} not found in module {module_path}")
        return agent_class
    except (ImportError, AttributeError) as e:
        logger.error(f"Failed to import agent class {class_name} from {module_path}: {e}")
        raise AgentConfigError(f"Could not import agent class {class_name} from {module_path}") from e


def create_agent(agent_name: str, config_override: Optional[Dict[str, Any]] = None) -> Any:
    """Create and initialize an agent instance.
    
    Args:
        agent_name: Name of the agent to create (must be in the registry for class lookup)
        config_override: Configuration that will be used exclusively (no environment fallback)
        
    Returns:
        An initialized agent instance
        
    Raises:
        AgentConfigError: If the agent is not found or initialization fails
    """
    # Initialize MCPSettings just for agent registry (class lookup)
    mcp_settings = MCPSettings()

    if agent_name not in mcp_settings.agent_registry:
        available_agents = ", ".join(mcp_settings.agent_registry.keys()) or "none"
        raise AgentConfigError(
            f"Agent '{agent_name}' not found in registry. "
            f"Available agents: {available_agents}"
        )

    agent_info = mcp_settings.agent_registry[agent_name]

    try:
        # Import the agent class
        agent_class = import_agent_class(agent_info["module"], agent_info["class"])
        
        # Use only the provided config_override, don't merge with any defaults
        if config_override is None:
            raise AgentConfigError(f"Configuration is required for agent '{agent_name}'. None provided.")
            
        # Create and initialize the agent with only the provided config
        agent = agent_class(config=config_override)
        return agent

    except Exception as e:
        logger.error(f"Failed to create agent '{agent_name}': {e}", exc_info=True)
        raise AgentConfigError(f"Failed to create agent '{agent_name}': {e}") from e


async def initialize_agent(agent_name: str, config_override: Optional[Dict[str, Any]] = None) -> Any:
    """Create and initialize an agent, ensuring it's properly set up.
    
    Args:
        agent_name: Name of the agent to create and initialize
        config_override: Optional configuration overrides
        
    Returns:
        An initialized and ready-to-use agent instance
        
    Raises:
        AgentConfigError: If initialization fails
    """
    try:
        agent = create_agent(agent_name, config_override)
        # Initialize the agent if it has an initialize method
        if hasattr(agent, 'initialize') and callable(agent.initialize):
            result = agent.initialize()

            # Handle both sync and async initialize methods
            if asyncio.iscoroutine(result) or isinstance(result, Awaitable):
                result = await result

            if hasattr(result, 'success') and not result.success:
                error_msg = getattr(result, 'error', 'Unknown error')
                raise AgentConfigError(f"Agent initialization failed: {error_msg}")

        return agent

    except AgentConfigError:
        raise  # Re-raise AgentConfigError as is

    except Exception as e:
        logger.error(f"Failed to initialize agent '{agent_name}': {e}", exc_info=True)
        # Clean up if possible
        if 'agent' in locals() and hasattr(agent, 'close') and callable(agent.close):
            try:
                close_result = agent.close()
                if asyncio.iscoroutine(close_result) or isinstance(close_result, Awaitable):
                    await close_result
            except Exception as close_error:
                logger.error(f"Error cleaning up failed agent '{agent_name}': {close_error}")
        raise AgentConfigError(f"Failed to initialize agent '{agent_name}': {e}") from e


def get_agent_config(agent_name: str) -> Dict[str, Any]:
    """Get the configuration for a specific agent.
    
    Args:
        agent_name: Name of the agent
        
    Returns:
        The agent's configuration dictionary
        
    Raises:
        AgentConfigError: If the agent is not found in the registry
    """
    mcp_settings = MCPSettings()
    if agent_name not in mcp_settings.agent_registry:
        raise AgentConfigError(f"Agent '{agent_name}' not found in registry")
    return mcp_settings.agent_registry[agent_name].get("config", {}).copy()


def list_available_agents() -> Dict[str, Dict[str, str]]:
    """List all available agents in the registry.
    
    Returns:
        A dictionary mapping agent names to their module and class names
    """
    mcp_settings = MCPSettings()
    return {
        name: {
            "module": info["module"],
            "class": info["class"],
            "enabled": mcp_settings.agent_registry.get(name, {}).get("enabled", False)
        }
        for name, info in mcp_settings.agent_registry.items()
    }
