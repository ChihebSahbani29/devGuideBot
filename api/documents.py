"""API endpoints for document management."""
import logging
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path

from config.dependencies import get_document_service
from schemas.document import (
    Document,
    DocumentCreate,
    DocumentUpdate,
    DocumentList,
    DocumentSearchQuery,
    DocumentSourceType
)
from services.document import DocumentService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents/{workspace_id}/documents", tags=["documents"])


@router.get("/", response_model=DocumentList, status_code=status.HTTP_200_OK)
async def list_documents(
        workspace_id: str,
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        source_type: Optional[DocumentSourceType] = None,
        source_id: Optional[str] = None,
        document_service: DocumentService = Depends(get_document_service)
):
    """List documents in a workspace with optional filtering."""

    return await document_service.list_documents(
        workspace_id=workspace_id,
        skip=skip,
        limit=limit,
        source_type=source_type,
        source_id=source_id
    )


@router.post("/search", response_model=DocumentList, status_code=status.HTTP_200_OK)
async def search_documents(
        search_query: DocumentSearchQuery,
        document_service: DocumentService = Depends(get_document_service)
):
    """Search documents with the given query."""

    return await document_service.search_documents(
        workspace_id=search_query.workspace_id,
        query=search_query
    )


@router.post("/", response_model=Document, status_code=status.HTTP_201_CREATED)
async def create_document(
        document: DocumentCreate,
        workspace_id: str,
        document_service: DocumentService = Depends(get_document_service)
):
    """Create a new document."""
    # Verify user has access to the workspace
    return await document_service.create_document(
        document=document,
        workspace_id=workspace_id
    )


@router.get("/{document_id}", response_model=Document, status_code=status.HTTP_200_OK)
async def get_document(
        document_id: str,
        workspace_id: str,
        document_service: DocumentService = Depends(get_document_service)
):
    """Get a document by ID."""

    document = await document_service.get_document(document_id, workspace_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    return document


@router.put("/{document_id}", response_model=Document, status_code=status.HTTP_200_OK)
async def update_document(
        document_id: str,
        document_update: DocumentUpdate,
        workspace_id: str,
        document_service: DocumentService = Depends(get_document_service)
):
    """Update a document."""
    updated = await document_service.update_document(
        document_id=document_id,
        update_data=document_update,
        workspace_id=workspace_id
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    return updated


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
        document_id: str,
        workspace_id: str,
        document_service: DocumentService = Depends(get_document_service)
):
    """Delete a document."""
    deleted = await document_service.delete_document(document_id, workspace_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )


@router.get("/indexed/list", response_model=list[dict[str, Any]], status_code=status.HTTP_200_OK)
async def list_indexed_documents(
    workspace_id: str = Path(..., description="ID of the workspace"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of documents to return"),
    document_service: DocumentService = Depends(get_document_service)
):
    """List documents in the Redis index for a workspace.
    
    This endpoint is for debugging purposes to check what documents are currently
    indexed in Redis for a workspace.
    """
    try:
        documents = await document_service.list_indexed_documents(workspace_id, limit)
        return documents
    except Exception as e:
        logger.error(f"Error listing indexed documents: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing indexed documents: {str(e)}"
        )


@router.delete("/", status_code=status.HTTP_200_OK, response_model=dict)
async def delete_all_documents(
        workspace_id: str,
        document_service: DocumentService = Depends(get_document_service)
):
    """
    Delete all documents for a workspace from both MongoDB and Redis.
    
    WARNING: This operation is irreversible and will remove all documents
    and their associated data from the system.
    """
    try:
        result = await document_service.delete_all_documents(workspace_id)
        return result
    except Exception as e:
        logger.error(f"Error deleting documents for workspace {workspace_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete documents: {str(e)}"
        )