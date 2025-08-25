from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException

from config.dependencies import get_workspace_service
from schemas.workspace import (
    WorkspaceCreateRequest, WorkspaceResponse, WorkspaceListResponse,
    JiraConfig, ConfluenceConfig, SharePointConfig, GitConfig, WorkspaceUpdateInfoRequest
)
from services.workspace import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


def format_workspace_response(ws: Dict[str, Any]) -> Dict[str, Any]:
    """Format workspace data for consistent response format."""
    if not ws:
        return None
    return {
        "id": str(ws.get("id") or ws.get("_id")),
        "name": ws["name"],
        "description": ws.get("description"),
        "jira": ws.get("jira"),
        "confluence": ws.get("confluence"),
        "sharepoint": ws.get("sharepoint"),
        "github": ws.get("github"),
        "gitlab": ws.get("gitlab")
    }


@router.post("/", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
        req: WorkspaceCreateRequest,
        svc: WorkspaceService = Depends(get_workspace_service)
):
    """Create a new workspace with optional data source configurations."""
    try:
        # Convert request data to dict and remove None values
        workspace_data = req.model_dump(exclude_unset=True)

        # Create workspace with the raw data (service will handle the conversion)
        workspace_id = await svc.create_workspace(
            name=workspace_data["name"],
            description=workspace_data.get("description"),
            jira=JiraConfig(**workspace_data["jira"]) if "jira" in workspace_data else None,
            confluence=ConfluenceConfig(**workspace_data["confluence"]) if "confluence" in workspace_data else None,
            sharepoint=SharePointConfig(**workspace_data["sharepoint"]) if "sharepoint" in workspace_data else None,
            github=GitConfig(**workspace_data["github"]) if "github" in workspace_data else None,
            gitlab=GitConfig(**workspace_data["gitlab"]) if "gitlab" in workspace_data else None
        )

        workspace = await svc.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=500, detail="Failed to retrieve created workspace")
        return format_workspace_response(workspace)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_model=WorkspaceListResponse)
async def list_workspaces(svc: WorkspaceService = Depends(get_workspace_service)):
    """List all workspaces with their configurations."""
    workspaces = await svc.list_workspaces()
    return {"workspaces": [format_workspace_response(ws) for ws in workspaces]}


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
        workspace_id: str,
        svc: WorkspaceService = Depends(get_workspace_service)
):
    """Get a workspace by ID with its configurations."""
    workspace = await svc.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return format_workspace_response(workspace)


@router.patch("/{workspace_id}/info", response_model=WorkspaceResponse)
async def update_workspace_info(
        workspace_id: str,
        req: WorkspaceUpdateInfoRequest,
        svc: WorkspaceService = Depends(get_workspace_service)
):
    """Update workspace name and description."""
    try:
        update_data = {}
        req_dict = req.model_dump(exclude_unset=True)
        print("req_dict___ ", req_dict)

        # Only allow updating name and description
        for field in ["name", "description"]:
            if field in req_dict:
                update_data[field] = req_dict[field]

        if not update_data:
            raise HTTPException(status_code=400, detail="No valid fields to update")

        success = await svc.update_workspace(workspace_id, update_data)
        if not success:
            raise HTTPException(status_code=404, detail="Workspace not found or no changes made")

        updated_workspace = await svc.get_workspace(workspace_id)
        return format_workspace_response(updated_workspace)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
        workspace_id: str,
        svc: WorkspaceService = Depends(get_workspace_service)
):
    # Check if workspace exists first
    ws = await svc.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Delete workspace
    deleted = await svc.delete_workspace(workspace_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete workspace")

    return None  # 204 No Content
