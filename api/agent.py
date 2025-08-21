"""API endpoints for agent management and execution."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Path

from config.dependencies import (
    get_agent_service
)
from schemas.agent import (
    AgentType,
    AgentCreateRequest,
    AgentUpdateRequest,
    AgentResponse,
    AgentListResponse,
    AgentExecutionRequest,
    AgentExecutionResponse,
)
from services.agent import AgentService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents/{workspace_id}/agents", tags=["agents"])


@router.post(
    "/",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new agent",
    description="Create a new agent in the specified workspace.",
)
async def create_agent(
        agent_data: AgentCreateRequest,
        workspace_id: str = Path(..., description="Workspace ID"),
        agent_service: AgentService = Depends(get_agent_service),
):
    """Create a new agent."""
    try:
        agent = await agent_service.create_agent(agent_data, workspace_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create agent",
            )
        return agent
    except Exception as e:
        logger.error(f"Error creating agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while creating agent",
        )


@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Get agent by ID",
    description="Retrieve an agent by its ID.",
)
async def get_agent(
        workspace_id: str,
        agent_id: str,
        agent_service: AgentService = Depends(get_agent_service),
):
    """Get an agent by ID."""
    agent = await agent_service.get_agent(agent_id, workspace_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found in workspace {workspace_id}",
        )
    return agent


@router.get(
    "/",
    response_model=AgentListResponse,
    summary="List agents",
    description="List all agents in the workspace with optional filtering.",
)
async def list_agents(
        workspace_id: str,
        skip: int = 0,
        limit: int = 100,
        agent_type: Optional[AgentType] = None,
        enabled: Optional[bool] = None,
        agent_service: AgentService = Depends(get_agent_service),
):
    """List agents with optional filtering."""
    agents = await agent_service.list_agents(
        workspace_id=workspace_id,
        skip=skip,
        limit=limit,
        agent_type=agent_type,
        enabled=enabled,
    )
    return {"agents": agents}


@router.put(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Update an agent",
    description="Update an existing agent's configuration.",
)
async def update_agent(
        workspace_id: str,
        agent_id: str,
        agent_data: AgentUpdateRequest,
        agent_service: AgentService = Depends(get_agent_service),
):
    """Update an agent."""
    try:
        agent = await agent_service.update_agent(agent_id, workspace_id, agent_data)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found in workspace {workspace_id}",
            )
        return agent
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an agent",
    description="Delete an agent by its ID.",
)
async def delete_agent(
        workspace_id: str,
        agent_id: str,
        agent_service: AgentService = Depends(get_agent_service),
):
    """Delete an agent."""
    success = await agent_service.delete_agent(agent_id, workspace_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found in workspace {workspace_id}",
        )
    return None


@router.post(
    "/{agent_id}/verify-connection",
    status_code=status.HTTP_200_OK,
    summary="Verify agent connection",
    description="Verify the connection to the agent's data source.",
    responses={
        200: {"description": "Connection verified successfully"},
        400: {"description": "Agent not found or connection failed"},
        500: {"description": "Internal server error"}
    }
)
async def verify_connection(
        workspace_id: str = Path(..., description="Workspace ID"),
        agent_id: str = Path(..., description="Agent ID"),
        agent_service: AgentService = Depends(get_agent_service),
):
    """Verify the connection to an agent's data source."""
    try:
        success = await agent_service.verify_connection(agent_id, workspace_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to verify agent connection",
            )
        return {"status": "success", "message": "Connection verified successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error verifying connection for agent {agent_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while verifying agent connection",
        )


@router.post(
    "/{agent_id}/execute",
    response_model=AgentExecutionResponse,
    summary="Execute an agent action",
    description="Execute a specific action with the agent.",
)
async def execute_agent(
        workspace_id: str,
        agent_id: str,
        execution_request: AgentExecutionRequest,
        agent_service: AgentService = Depends(get_agent_service),
):
    """Execute an agent action."""
    return await agent_service.execute_agent(
        agent_id=agent_id,
        workspace_id=workspace_id,
        execution_request=execution_request,
    )
