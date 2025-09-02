"""Service for document management operations with embedding support."""
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from tqdm import tqdm

from chunkers.base_chunker import BaseChunker
from connectors.ai_agents.embedding_agent import EmbeddingAgent
from db.redis import RedisDatabase
from parsers.base_parser import BaseParser
from repositories.chunk import ChunkRepository
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
            chunk_repo: ChunkRepository,
            redis_db: RedisDatabase,
            embedding_agent: Optional[EmbeddingAgent] = None,
            parsers: Optional[Dict[str, Any]] = None,
            chunkers: Optional[Dict[str, Any]] = None,
            default_chunk_size: int = 1000,
            chunk_overlap: int = 100
    ):
        """Initialize with document repository, chunk repository, Redis database, and embedding agent.
        
        Args:
            repo: Document repository instance
            chunk_repo: Chunk repository instance
            redis_db: Redis database instance
            embedding_agent: Optional embedding agent instance. If not provided,
                embeddings will not be generated for chunks.
            parsers: Dictionary of available parsers by name
            chunkers: Dictionary of available chunkers by name
            default_chunk_size: Default chunk size in characters
            chunk_overlap: Default overlap between chunks in characters
        """
        if not parsers:
            raise ValueError("Parsers dictionary must be provided via dependency injection")
        if not chunkers:
            raise ValueError("Chunkers dictionary must be provided via dependency injection")

        self.repo = repo
        self.chunk_repo = chunk_repo
        self.redis = redis_db
        self.embedding_agent = embedding_agent
        self.parsers = parsers
        self.chunkers = chunkers
        self.default_chunk_size = default_chunk_size
        self.chunk_overlap = chunk_overlap

        logger.info(f"Initialized DocumentService with {len(parsers)} parsers and {len(chunkers)} chunkers")

    def get_embedding_dimension(self) -> int:
        """Get the embedding dimension size.
        
        Returns:
            int: The dimension size of embeddings, or 0 if embedding agent is not available.
        """
        if self.embedding_agent:
            return self.embedding_agent.embedding_dim
        return 0

    def _get_parser_for_document(self, document: IngestedDocument) -> Optional[BaseParser]:
        """Get the appropriate parser for the given document.
        
        Args:
            document: The document to parse
            
        Returns:
            An instance of the appropriate parser, or None if no suitable parser is found
        """
        # First check if we have a direct parser for the source type
        if document.source_type.value in self.parsers:
            return self.parsers[document.source_type.value]

        # Try to determine parser from document metadata or content type
        file_extension = None
        if hasattr(document, 'metadata') and 'file_extension' in document.metadata:
            file_extension = document.metadata['file_extension']
        elif hasattr(document, 'content_type') and document.content_type:
            # Try to extract file extension from content type
            if 'python' in document.content_type:
                file_extension = 'py'
            elif 'javascript' in document.content_type:
                file_extension = 'js'
            # Add other content type mappings as needed

        # If we have a file extension, find a parser that supports it
        if file_extension:
            # Normalize file extension (remove leading dot and convert to lowercase)
            file_extension = file_extension.lstrip('.').lower()
            
            # First try to find a parser that explicitly supports this extension
            for parser in self.parsers.values():
                if hasattr(parser, 'supported_formats') and file_extension in parser.supported_formats():
                    return parser
            
            # If no explicit match, try to find a parser that can handle the file
            for parser in self.parsers.values():
                if hasattr(parser, 'get_parser_for_file'):
                    parser_instance = parser.get_parser_for_file(f'file.{file_extension}')
                    if parser_instance:
                        return parser_instance

        # Check content type for text or markdown
        content_type = getattr(document, 'content_type', '').lower()
        if 'text/' in content_type or 'markdown' in content_type:
            return self.parsers.get('markdown')
            
        # If we have a code parser and no other parser was found, default to it
        if 'code' in self.parsers:
            return self.parsers['code']

        return None

    def _get_chunker_for_document(
            self,
            document: IngestedDocument,
            content_type: Optional[str] = None
    ) -> Optional[BaseChunker]:
        """Get the appropriate chunker for the given document or content type.
        
        Args:
            document: The document to chunk
            content_type: Optional content type to use for chunker selection
            
        Returns:
            An instance of the appropriate chunker, or None if no suitable chunker is found
        """
        # Use provided content type if available
        if content_type and content_type in self.chunkers:
            return self.chunkers[content_type]

        # Try to determine chunker from document source type
        if document.source_type.value in self.chunkers:
            return self.chunkers[document.source_type.value]

        # Default to markdown chunker for text content
        if 'text/' in getattr(document, 'content_type', '') or 'markdown' in getattr(document, 'content_type', ''):
            return self.chunkers.get('markdown')

        # If no specific chunker found, use the first available one
        if self.chunkers:
            return next(iter(self.chunkers.values()))

        return None

    async def _process_document_content(
            self,
            document: IngestedDocument,
            workspace_id: str,
            source_type: DocumentSourceType,
            source_id: str,
            force_update: bool = False
    ) -> Optional[Document]:
        """Process document content through parsers and chunkers.
        
        Args:
            document: The document to process
            workspace_id: ID of the workspace
            source_type: Type of the source
            source_id: ID of the source
            force_update: Whether to force update the document
            
        Returns:
            The processed document or None if processing failed
        """
        try:
            # Get the appropriate parser for this document
            parser = self._get_parser_for_document(document)
            if not parser:
                logger.warning(f"No suitable parser found for document: {document.title}")
                return None

            # Parse the document content
            parsed_content = await parser.parse(document.content)
            
            # Get the appropriate chunker for this document
            chunker = self._get_chunker_for_document(document)
            if not chunker:
                logger.warning(f"No suitable chunker found for document: {document.title}")
                return None

            # Handle different parser output formats
            if isinstance(parsed_content, list):
                # If parser returns a list of chunks, use them directly
                chunks = [
                    {
                        'content': chunk.get('content', ''),
                        'metadata': {**document.metadata, **chunk.get('metadata', {})}
                    }
                    for chunk in parsed_content
                    if chunk.get('content')
                ]
            else:
                # If parser returns a string, use the chunker to split it
                chunks = await chunker.chunk(
                    content=str(parsed_content),
                    metadata=document.metadata or {}
                )

            # Create or update the document in the database
            doc_data = {
                "title": document.title,
                "content": document.content,
                "source_type": source_type,
                "source_id": source_id,
                "source_url": str(document.url) if document.url else None,
                "metadata": {
                    **document.metadata,
                    "chunk_count": len(chunks),
                    "parsed_content": parsed_content
                },
                "workspace_id": workspace_id
            }

            # Check if document already exists
            existing_docs = await self.repo.list_documents(
                workspace_id=workspace_id,
                source_type=source_type,
                source_id=document.id
            )
            existing_doc = existing_docs[0] if existing_docs else None

            if existing_doc:
                # Delete existing chunks before creating new ones
                await self.chunk_repo.delete_chunks_by_document(str(existing_doc["_id"]))
                
                if not force_update:
                    logger.info(f"Document {document.title} already exists, skipping update")
                    return None
                
                # Update existing document
                doc_data["updated_at"] = str(datetime.utcnow())
                updated_doc = await self.repo.update_document(
                    document_id=existing_doc["_id"],
                    workspace_id=workspace_id,
                    update_data=doc_data
                )
                document_id = str(existing_doc["_id"])
            else:
                # Create new document
                document_id = await self.repo.create_document(doc_data)
                updated_doc = await self.repo.get_document(document_id, workspace_id)

            if not updated_doc:
                logger.error(f"Failed to create/update document: {document.title}")
                return None

            # Prepare chunks for batch insertion
            chunks_to_insert = []
            for i, chunk_content in enumerate(chunks):
                chunk_data = {
                    "document_id": document_id,
                    "workspace_id": workspace_id,
                    "content": chunk_content,
                    "metadata": {
                        "chunk_index": i,
                        "source": source_type.value,
                        "source_id": source_id,
                        "document_title": document.title,
                        **document.metadata
                    }
                }
                
                # Generate embedding if embedding agent is available
                if self.embedding_agent:
                    try:
                        # Get embeddings for the chunk content
                        embeddings = await self.embedding_agent.get_embeddings([chunk_content])
                        if embeddings and len(embeddings) > 0:
                            chunk_data["vector_embedding"] = embeddings[0].tolist()  # Convert numpy array to list
                            chunk_data["metadata"]["has_embedding"] = True
                        else:
                            logger.warning(f"No embeddings returned for chunk {i}")
                            chunk_data["metadata"]["has_embedding"] = False
                    except Exception as e:
                        logger.error(f"Error generating embedding for chunk {i}: {str(e)}")
                        chunk_data["metadata"]["has_embedding"] = False

                chunks_to_insert.append(chunk_data)
            
            # Insert all chunks in a single batch
            if chunks_to_insert:
                await self.chunk_repo.create_chunks_batch(chunks_to_insert)

            return Document(**updated_doc)

        except Exception as e:
            logger.error(f"Error processing document {document.title}: {str(e)}", exc_info=True)
            return None

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
            return_fields=["workspace_id", "document_id", "title", "content", "source_type", "source_id", "metadata"],
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
                score_threshold=0.0
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
            batch_size: int = 10,
            force_update: bool = False
    ) -> Dict[str, int] | None:
        """Ingest multiple documents from a data source with optional embeddings.

        Args:
            documents: List of documents to ingest
            workspace_id: ID of the workspace
            source_type: Type of the source
            source_id: ID of the source
            batch_size: Number of documents to process in each batch for embedding generation
            force_update: If True, update documents even if they haven't changed

        Returns:
            Dict with counts of created and updated documents
        """
        results = {
            "processed": 0,
            "created": 0,
            "updated": 0,
            "errors": 0,
            "skipped": 0,
            "chunks_created": 0,
            "chunks_updated": 0
        }

        if not documents:
            logger.warning("No documents provided for ingestion")
            return results

        logger.info(f"Starting ingestion of {len(documents)} documents from {source_type} source {source_id}")

        with tqdm(total=len(documents), desc="Processing documents") as pbar:
            # Process documents one by one to handle chunking properly
            for doc in documents:
                try:
                    # Process document content into chunks
                    document_chunks = await self._process_document_content(
                        document=doc,
                        workspace_id=workspace_id,
                        source_type=source_type,
                        source_id=source_id
                    )

                    if not document_chunks:
                        logger.warning(f"No valid chunks extracted from document {doc.id}")
                        results["skipped"] += 1
                        pbar.update(1)
                        continue

                    # Process each chunk as a separate document
                    for chunk in document_chunks:
                        try:
                            # Ensure chunk is a dictionary and has required fields
                            if not isinstance(chunk, dict):
                                logger.warning(f"Skipping invalid chunk type: {type(chunk)}")
                                continue
                                
                            # Safely extract chunk data with defaults
                            chunk_title = chunk.get('title', '')
                            chunk_content = chunk.get('content', '')
                            chunk_metadata = chunk.get('metadata', {})
                            
                            # Safely get document title
                            doc_title = 'Document'
                            if hasattr(doc, 'get') and callable(doc.get):
                                doc_title = doc.get('title', 'Document')
                            
                            # Create document data with proper type handling
                            doc_data = DocumentCreate(
                                title=chunk_title or f"{doc_title} [Chunk]",
                                content=chunk_content,
                                source_type=source_type,
                                source_id=source_id,
                                source_url=doc.get('url') if hasattr(doc, 'get') and callable(doc.get) else None,
                                metadata={
                                    **(doc.get('metadata', {}) if hasattr(doc, 'get') and callable(doc.get) else {}),
                                    **chunk_metadata
                                }
                            )

                            # Create or update the document
                            created = await self.create_document(
                                document=doc_data,
                                workspace_id=workspace_id
                            )

                            if created:
                                results["created"] += 1
                                results["chunks_created"] += 1
                            else:
                                results["updated"] += 1
                                results["chunks_updated"] += 1

                        except Exception as chunk_error:
                            logger.error(f"Error processing chunk for document {doc.id}: {str(chunk_error)}")
                            results["errors"] += 1

                    results["processed"] += 1
                    pbar.set_postfix_str(
                        f"Processed: {results['processed']}, Created: {results['created']}, "
                        f"Updated: {results['updated']}, Errors: {results['errors']}",
                        refresh=False
                    )
                    pbar.update(1)

                except Exception as e:
                    logger.error(f"Error ingesting document {getattr(doc, 'id', 'unknown')}: {str(e)}")
                    results["errors"] += 1
                    results["skipped"] += 1
                    pbar.update(1)
                    pbar.set_postfix_str(
                        f"Processed: {results['processed']}, Created: {results['created']}, "
                        f"Updated: {results['updated']}, Errors: {results['errors']}",
                        refresh=False
                    )

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
                cursor = 0
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
