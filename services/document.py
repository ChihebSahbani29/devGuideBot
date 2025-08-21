"""Service for document management operations with embedding support."""
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from tqdm import tqdm

from connectors.ai_agents.embedding_agent import EmbeddingAgent
from db.redis import RedisDatabase
from repositories.document import DocumentRepository
from schemas.document import (
    Document,
    DocumentCreate,
    DocumentUpdate,
    DocumentList,
    DocumentSearchQuery,
    DocumentSourceType,
    IngestedDocument
)

logger = logging.getLogger(__name__)


class DocumentService:
    """Service for document management operations."""

    def __init__(
            self,
            repo: DocumentRepository,
            redis_db: RedisDatabase,
            embedding_agent: Optional[EmbeddingAgent] = None
    ):
        """Initialize with document repository, Redis database, and embedding agent.
        
        Args:
            repo: Document repository instance
            redis_db: Redis database instance
            embedding_agent: Optional embedding agent instance. If not provided,
                           embeddings will not be generated for documents.
        """
        self.repo = repo
        self.redis = redis_db
        self.embedding_agent = embedding_agent

    def get_embedding_dimension(self) -> int:
        """Get the embedding dimension size.
        
        Returns:
            int: The dimension size of embeddings, or 0 if embedding agent is not available.
        """
        if self.embedding_agent:
            return self.embedding_agent.embedding_dim
        return 0

    async def create_document(self, document: DocumentCreate, workspace_id: str) -> Document | None:
        """Create a new document with optional embeddings.
        
        Args:
            document: Document data
            workspace_id: ID of the workspace
            
        Returns:
            The created document with embeddings if embedding_agent is configured
            
        Note:
            If embedding_agent is provided, the document content will be embedded
            and the embedding will be stored both in the document metadata and Redis.
        """
        embedding = None

        # Generate embeddings if embedding agent is available
        if self.embedding_agent and document.content:
            try:
                # Get embedding for the document content
                embeddings = await self.embedding_agent.get_embeddings(document.content)
                if embeddings and len(embeddings) > 0:
                    # Convert numpy array to list for JSON serialization (only for Redis)
                    embedding = embeddings[0].tolist()
            except Exception as e:
                logger.error(f"Error generating document embedding: {str(e)}")

        # Prepare document data
        document_dict = document.model_dump()

        # Convert HttpUrl to string if present
        if 'source_url' in document_dict and document_dict['source_url'] is not None:
            document_dict['source_url'] = str(document_dict['source_url'])

        document_dict["workspace_id"] = workspace_id
        document_dict["created_at"] = datetime.utcnow()
        document_dict["updated_at"] = document_dict["created_at"]

        # Create document in the database
        document_id = await self.repo.create_document(document_dict)

        # Index document in Redis with embedding if available
        if self.embedding_agent and embedding:
            try:
                index_name = f"documents:{workspace_id}"

                # Create index if it doesn't exist
                await self.redis.create_vector_index(
                    index_name=index_name,
                    vector_dim=self.embedding_agent.get_embedding_dimension()
                )

                # Index the document
                await self.redis.index_document(
                    index_name=index_name,
                    document_id=str(document_id),
                    workspace_id=workspace_id,
                    content=document.content,
                    embedding=embedding,
                    source_id=document.source_id,
                    source_type=document.source_type,
                    metadata=document.metadata,
                    title=document.title
                )
                logger.info(f"Indexed document {document_id} in Redis with embeddings")

            except Exception as e:
                logger.error(f"Error indexing document in Redis: {str(e)}")
                # Continue even if Redis indexing fails

        # Fetch and return the created document
        created_doc = await self.repo.get_document(document_id, workspace_id)
        if not created_doc:
            raise ValueError(f"Failed to create document with ID: {document_id}")

        # Convert ObjectId to string for Pydantic model
        if '_id' in created_doc:
            created_doc['_id'] = str(created_doc['_id'])

            return Document(**created_doc)

    async def get_document(self, document_id: str, workspace_id: str) -> Optional[Document]:
        """Get a document by ID."""
        doc = await self.repo.get_document(document_id, workspace_id)
        if doc and '_id' in doc:
            doc['_id'] = str(doc['_id'])
        return Document(**doc) if doc else None

    async def update_document(
            self,
            document_id: str,
            update_data: DocumentUpdate,
            workspace_id: str
    ) -> Optional[dict]:
        """Update a document.

        Args:
            document_id: ID of the document to update
            update_data: Updated document data
            workspace_id: ID of the workspace

        Returns:
            The updated document or None if not found

        Note:
            If the document content is updated, this will regenerate the embedding
            and update it in Redis only (not in MongoDB).
        """
        # Get the current document
        current_doc = await self.repo.get_document(document_id, workspace_id)
        if not current_doc:
            return None

        # Check if we need to update embeddings
        content_changed = (update_data.content is not None and
                           update_data.content != current_doc.get('content'))

        # Check if source information changed
        source_changed = False
        if hasattr(update_data, 'source_type') and hasattr(update_data, 'source_id'):
            source_changed = (update_data.source_type is not None and update_data.source_type != current_doc.get(
                'source_type')) or \
                             (update_data.source_id is not None and update_data.source_id != current_doc.get(
                                 'source_id'))

        # Ensure metadata is a dictionary and clean it up if needed
        if update_data.metadata is None:
            update_data.metadata = {}
        elif not isinstance(update_data.metadata, dict):
            logger.warning(f"Unexpected metadata type: {type(update_data.metadata)}. Resetting to empty dict.")
            update_data.metadata = {}

        try:
            # Prepare update data and ensure we don't include None values
            update_dict = update_data.model_dump(exclude_unset=True)

            # Update the document in the database
            updated_doc = await self.repo.update_document(
                document_id=document_id,
                workspace_id=workspace_id,
                update_data=update_dict
            )

            if not updated_doc:
                return None

            # Convert ObjectId to string for the response
            if '_id' in updated_doc:
                updated_doc['_id'] = str(updated_doc['_id'])

            # If source changed, update the source index
            if source_changed:
                await self.repo.update_source_index(
                    source_type=update_data.source_type or current_doc.get('source_type'),
                    source_id=update_data.source_id or current_doc.get('source_id'),
                    workspace_id=workspace_id
                )

            # If content changed and we have an embedding agent, update the embedding in Redis
            if content_changed and self.embedding_agent and update_data.content:
                # Create a copy of the updated doc and ensure all fields are present
                doc_for_indexing = {**current_doc, **updated_doc}
                doc_for_indexing['_id'] = document_id  # Ensure _id is set
                doc_for_indexing['workspace_id'] = workspace_id  # Ensure workspace_id is set
                # Create the Document model with proper type conversion
                document_model = Document(**{
                    k: str(v) if k == '_id' else v
                    for k, v in doc_for_indexing.items()
                })
                await self._index_document(document_model)

            return updated_doc

        except Exception as e:
            logger.error(f"Error updating document: {str(e)}")
            raise

    async def delete_document(self, document_id: str, workspace_id: str) -> bool:
        """Delete a document by ID.
        
        Args:
            document_id: ID of the document to delete
            workspace_id: ID of the workspace
            
        Returns:
            bool: True if the document was deleted successfully
            
        Note:
            This will also remove the document from the Redis vector index.
        """
        # First delete from Redis if it exists
        try:
            index_name = f"documents:{workspace_id}"
            await self.redis.delete_document(index_name, document_id)
            logger.info(f"Deleted document {document_id} from Redis index {index_name}")
        except Exception as e:
            logger.error(f"Error deleting document from Redis: {str(e)}")
            # Continue with deletion from main database even if Redis fails

        # Delete from the main database
        return await self.repo.delete_document(document_id, workspace_id)

    async def list_documents(
            self,
            workspace_id: str,
            skip: int = 0,
            limit: int = 100,
            source_type: Optional[DocumentSourceType] = None,
            source_id: Optional[str] = None
    ) -> DocumentList:
        """List documents with optional filtering."""
        # Get paginated results
        docs = await self.repo.list_documents(
            workspace_id=workspace_id,
            skip=skip,
            limit=limit,
            source_type=source_type,
            source_id=source_id
        )

        # Get total count for pagination
        total = len(docs)

        # Convert MongoDB documents to Pydantic models
        items = [Document(**doc) for doc in docs]

        return DocumentList(
            total=total,
            skip=skip,
            limit=limit,
            items=items
        )

    async def vector_search(
            self,
            workspace_id: str,
            query: str,
            source_types: Optional[List[DocumentSourceType]] = None,
            source_ids: Optional[List[str]] = None,
            limit: int = 10,
            score_threshold: float = 0.7
    ) -> List[Document]:
        """Search documents using vector similarity search.
        
        Args:
            workspace_id: ID of the workspace
            query: Search query text
            source_types: Optional filter by source types
            source_ids: Optional filter by source IDs
            limit: Maximum number of results to return
            score_threshold: Minimum similarity score (0-1)
            
        Returns:
            List of matching documents with similarity scores
        """
        if not self.embedding_agent:
            raise ValueError("Embedding agent is not configured for vector search")

        # Generate embedding for the query
        query_embedding = await self.embedding_agent.get_embeddings(query)
        if not query_embedding or not query_embedding[0].any():
            return []

        # Prepare filter expression for Redis search
        filter_parts = [f"@workspace_id:{workspace_id}"]


        # Perform vector search in Redis
        index_name = f"documents:{workspace_id}"
        filter_expression = " ".join(filter_parts) if filter_parts else ""

        search_results = await self.redis.vector_search(
            index_name=index_name,
            query_vector=query_embedding[0].tolist(),
            k=limit,
            return_fields=["workspace_id","document_id", "title", "content", "source_type", "source_id", "metadata"],
            score_threshold=score_threshold,
            filter_expression=filter_expression
        )
        if not search_results:
            return []

        # Get document details from MongoDB
        document_ids = [result['document_id'] for result in search_results]
        documents = []
        if document_ids:
            documents = await self.repo.get_documents_by_ids(workspace_id, document_ids)

        # Create result documents with similarity scores
        results = []
        for doc in documents:
            # Find the corresponding search result for this document
            result = next(
                (r for r in search_results
                 if r.get('document_id') == str(doc.get('_id', ''))),
                None
            )
            if result:
                doc_dict = dict(doc)
                doc_dict['_id'] = str(doc_dict['_id'])
                doc_dict['similarity_score'] = 1.0 - float(result.get('vector_score', 1.0))
                results.append(Document(**doc_dict))

        # Sort by similarity score (highest first)
        results.sort(key=lambda x: getattr(x, 'similarity_score', 0.0), reverse=True)
        return results

    async def search_documents(
            self, workspace_id: str, query: DocumentSearchQuery
    ) -> DocumentList:
        """Search documents with the given query using vector similarity search.

        Args:
            workspace_id: ID of the workspace
            query: Search query with filters and pagination

        Returns:
            DocumentList containing matching documents with pagination metadata

        Raises:
            ValueError: If embedding agent is not available or search fails
        """
        if not self.embedding_agent:
            raise ValueError("Vector search is not available - embedding agent not configured")
            
        try:
            results = await self.vector_search(
                workspace_id=workspace_id,
                query=query.query,
                source_types=query.source_types,
                source_ids=query.source_ids,
                limit=query.limit + query.skip,  # Get enough results for pagination
                score_threshold=0.7
            )

            # Apply pagination
            paginated_results = results[query.skip:query.skip + query.limit]

            return DocumentList(
                items=paginated_results,
                total=len(results),
                skip=query.skip,
                limit=query.limit
            )
        except Exception as e:
            logger.error(f"Vector search failed: {str(e)}")
            raise ValueError("Failed to perform vector search") from e

    async def ingest_documents(
            self,
            documents: List[IngestedDocument],
            workspace_id: str,
            source_type: DocumentSourceType,
            source_id: str,
            batch_size: int = 10
    ) -> Dict[str, int]:
        """Ingest multiple documents from a data source with optional embeddings.

        Args:
            documents: List of documents to ingest
            workspace_id: ID of the workspace
            source_type: Type of the source
            source_id: ID of the source
            batch_size: Number of documents to process in each batch for embedding generation

        Returns:
            Dictionary with ingestion results containing:
            - total: Total number of documents processed
            - created: Number of new documents created
            - updated: Number of existing documents updated
            - skipped: Number of documents skipped (no changes)
            - errors: Number of documents that failed to process

        Note:
            If embedding_agent is configured, this will generate embeddings for all documents
            in batches to optimize API calls to the embedding service.
        """

        results = {
            "total": len(documents),
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0
        }

        # Create a progress bar for the entire ingestion process
        with tqdm(total=len(documents), desc="Ingesting documents", unit="doc") as pbar:
            # Process documents in batches for embedding generation
            for i in range(0, len(documents), batch_size):
                batch = documents[i:i + batch_size]

                # Generate embeddings for the batch if embedding agent is available
                if self.embedding_agent:
                    try:
                        texts = [doc.content for doc in batch if doc.content]
                        if texts:
                            embeddings = await self.embedding_agent.get_embeddings(texts)

                            # Assign embeddings back to documents
                            for j, doc in enumerate(batch):
                                if j < len(embeddings) and doc.content:
                                    doc.metadata = doc.metadata or {}
                                    doc.metadata["embedding"] = embeddings[j].tolist()
                    except Exception as e:
                        logger.error(f"Error generating embeddings for batch {i // batch_size}: {str(e)}")

                # Process each document in the batch
                for doc in batch:
                    try:
                        object_id_str = doc.id[:24]
                        # Check if document already exists
                        existing_doc = await self._find_existing_document(
                            workspace_id=workspace_id,
                            source_type=source_type,
                            source_id=source_id,
                            document_id=object_id_str
                        )

                        if existing_doc:
                            # Update existing document
                            updated = await self.update_document(
                                document_id=str(existing_doc['_id']),
                                update_data=DocumentUpdate(
                                    content=doc.content,
                                    metadata=doc.metadata
                                ),
                                workspace_id=workspace_id
                            )
                            if updated:
                                results["updated"] += 1
                                pbar.set_postfix_str(
                                    f"Updated: {results['updated']}, Created: {results['created']}, Errors: {results['errors']}",
                                    refresh=False)
                            else:
                                results["skipped"] += 1
                            pbar.update(1)
                        else:
                            # Create new document
                            created = await self.create_document(
                                document=DocumentCreate(
                                    title=doc.title or "Untitled Document",
                                    content=doc.content,
                                    source_type=source_type,
                                    source_id=source_id,
                                    source_url=doc.url,
                                    metadata=doc.metadata or {}
                                ),
                                workspace_id=workspace_id
                            )
                            if created:
                                results["created"] += 1
                                pbar.set_postfix_str(
                                    f"Updated: {results['updated']}, Created: {results['created']}, Errors: {results['errors']}",
                                    refresh=False)
                            else:
                                results["errors"] += 1
                            pbar.update(1)

                    except Exception as e:
                        logger.error(f"Error ingesting document {doc.id}: {str(e)}")
                        results["errors"] += 1
                        pbar.update(1)
                        pbar.set_postfix_str(
                            f"Updated: {results['updated']}, Created: {results['created']}, Errors: {results['errors']}",
                            refresh=False)

        return results

    async def _find_existing_document(
            self,
            workspace_id: str,
            source_type: DocumentSourceType,
            source_id: str,
            document_id: str
    ) -> Optional[dict]:
        """Find an existing document by its source information."""
        return await self.repo.find_document_by_source(
            workspace_id=workspace_id,
            source_type=source_type,
            source_id=source_id,
            document_id=document_id
        )

    async def _index_document(self, document: Document) -> None:
        """Index a document's embedding in Redis.

        Args:
            document: Document to index
        """
        if not self.embedding_agent or not document.content:
            raise
        try:
            # Generate embedding for the document
            embeddings = await self.embedding_agent.get_embeddings(document.content)
            if not embeddings:
                logger.warning(f"Failed to generate embeddings for document {document.id}")
                return

            embedding = embeddings[0].tolist()

            # Index in Redis
            index_name = f"documents:{document.workspace_id}"

            # Create index if it doesn't exist
            await self.redis.create_vector_index(
                index_name=index_name,
                vector_dim=self.embedding_agent.get_embedding_dimension()
            )

            # Get existing metadata without embedding
            metadata = document.metadata or {}
            if 'embedding' in metadata:
                del metadata['embedding']

            # Index the document in Redis with the embedding
            await self.redis.index_document(
                index_name=index_name,
                document_id=str(document.id),
                workspace_id=document.workspace_id,
                content=document.content,
                embedding=embedding,
                source_id=document.source_id,
                source_type=document.source_type,
                metadata=metadata,
                title=document.title
            )

            logger.debug(f"Indexed document {document.id} in Redis with embeddings")

        except Exception as e:
            logger.error(f"Error indexing document {document.id}: {str(e)}")

    async def _remove_from_index(
            self, document_id: str, workspace_id: str, source_type: Optional[str] = None,
            source_id: Optional[str] = None
    ) -> None:
        """Remove a document from the Redis index.

        Args:
            document_id: ID of the document to remove
            workspace_id: ID of the workspace
            source_type: Optional source type (for backward compatibility)
            source_id: Optional source ID (for backward compatibility)
        """
        try:
            index_name = f"documents:{workspace_id}"
            await self.redis.delete_document(index_name, document_id)
            logger.info(f"Removed document {document_id} from Redis index {index_name}")
            content_key = f"content:{document_id}"
            source_key = f"source:{source_type}:{source_id}"

            # Remove from source index
            await self.redis.get_client().srem(source_key, f"doc:{document_id}")

            # Delete document data and content
            await self.redis.get_client().delete(f"doc:{document_id}", content_key)

        except Exception as e:
            logger.error(f"Error removing document {document_id} from index: {str(e)}")

    async def list_indexed_documents(self, workspace_id: str, count: int = 10) -> list[Dict[str, Any]]:
        """List documents in the Redis index for a workspace.
        
        Args:
            workspace_id: ID of the workspace
            count: Maximum number of documents to return
            
        Returns:
            List of document metadata from the index
        """
        index_name = f"documents:{workspace_id}"
        try:
            documents = await self.redis.list_documents(index_name, count)
            logger.info(f"Found {len(documents)} documents in index {index_name}")
            return documents
        except Exception as e:
            logger.error(f"Error listing documents in index {index_name}: {str(e)}")
            return []

    async def delete_all_documents(self, workspace_id: str) -> dict:
        """Delete all documents for a workspace from both MongoDB and Redis.

        This method first removes all documents from Redis to maintain consistency,
        then uses the repository layer to delete documents from MongoDB.
        
        Args:
            workspace_id: ID of the workspace

        Returns:
            Dictionary with deletion results

        Raises:
            Exception: If there's an error during the deletion process
        """
        try:
            # First, delete from Redis
            index_name = f"documents:{workspace_id}"
            try:
                # Get all document keys for this workspace
                cursor = '0'
                deleted_count = 0
                while cursor != 0:
                    cursor, keys = await self.redis.client.scan(
                        cursor=cursor,
                        match=f"doc:*:{workspace_id}:*"
                    )
                    if keys:
                        await self.redis.client.delete(*keys)
                        deleted_count += len(keys)
                logger.info(f"Deleted {deleted_count} documents from Redis for workspace {workspace_id}")
            except Exception as e:
                logger.error(f"Error deleting documents from Redis for workspace {workspace_id}: {str(e)}")
                raise

            # Delete from MongoDB using repository layer
            mongo_deleted = await self.repo.delete_all_documents(workspace_id)

            return {
                "mongo_deleted": mongo_deleted,
                "redis_deleted": deleted_count,
                "message": f"Successfully deleted {mongo_deleted} documents from MongoDB and {deleted_count} documents from Redis"
            }

        except Exception as e:
            logger.error(f"Error deleting documents for workspace {workspace_id}: {str(e)}")
            raise
