import json
import logging
import re
from typing import List, Dict, Any, Optional

import numpy as np
import redis.asyncio as redis
from redis.commands.search.field import (
    VectorField,
    TextField, TagField
)
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query

logger = logging.getLogger(__name__)

# Constants for vector search
VECTOR_DIM = 1536  # Default dimension for text-embedding-3-small
DISTANCE_METRIC = "COSINE"  # Distance metric for vector search


def normalize_source_id(source_id: str) -> str:
    """Normalize source ID to be compatible with Redis TagField.
    
    Replaces problematic characters with hyphens and ensures the ID is in a consistent format.
    For example: "github/github-mcp-server" becomes "github-mcp-server"
    
    Args:
        source_id: The original source ID
        
    Returns:
        Normalized source ID
    """
    if not source_id:
        return source_id
        
    # Extract the last part after any separator (/, \, ., etc.)
    parts = re.split(r'[/\\:.]', str(source_id).strip())
    # Take the last non-empty part
    normalized = parts[-1] if parts else source_id
    
    # Remove any remaining problematic characters
    normalized = re.sub(r'[^\w-]', '-', normalized)
    
    # Remove any leading/trailing hyphens
    normalized = normalized.strip('-')
    
    return normalized if normalized else source_id


class RedisDatabase:
    def __init__(self, client: redis.Redis):
        """Initialize Redis database with a Redis client.
        
        Args:
            client: Redis client instance
        """
        self.client = client

    def get_client(self) -> redis.Redis:
        return self.client

    async def close(self):
        await self.client.close()

    async def list_documents(self, index_name: str, count: int = 10) -> List[Dict[str, Any]]:
        """List documents in an index.
        
        Args:
            index_name: Name of the index
            count: Maximum number of documents to return
            
        Returns:
            List of document metadata
        """
        try:
            # Use SCAN to get document keys with the pattern
            cursor = 0
            keys = []
            while True:
                cursor, partial_keys = await self.client.scan(
                    cursor=cursor,
                    match=f"doc:*",
                    count=100
                )
                keys.extend(partial_keys)
                if cursor == 0 or len(keys) >= count:
                    break

            # Get document details
            documents = []
            for key in keys[:count]:
                doc = await self.client.hgetall(key)
                if doc:
                    # Convert bytes to strings for JSON serialization
                    doc_data = {}
                    for k, v in doc.items():
                        if k == b'embedding':
                            continue  # Skip binary embedding data
                        if isinstance(k, bytes):
                            k = k.decode('utf-8')
                        if isinstance(v, bytes):
                            try:
                                v = v.decode('utf-8')
                            except UnicodeDecodeError:
                                v = str(v)  # Fallback to string representation
                        doc_data[k] = v
                    documents.append(doc_data)

            return documents

        except Exception as e:
            logger.error(f"Error listing documents in index {index_name}: {str(e)}", exc_info=True)
            return []

    async def create_vector_index(
            self,
            index_name: str,
            vector_dim: int = VECTOR_DIM,
            distance_metric: str = DISTANCE_METRIC,
            prefix: str = "doc:"
    ) -> bool:
        """Create a Redis search index for vector search.
        
        Args:
            index_name: Name of the index to create
            vector_dim: Dimension of the vectors
            distance_metric: Distance metric (COSINE, L2, IP)
            prefix: Key prefix for documents in this index
            
        Returns:
            bool: True if index was created successfully
        """
        if not index_name:
            logger.error("Index name cannot be empty")
            return False

        try:
            # Check if index already exists and is valid
            try:
                info = await self.client.ft(index_name).info()
                # Verify the index has documents or is accessible
                if info.get('num_docs', 0) >= 0:  # Simple verification
                    logger.info(f"Index {index_name} already exists with {info.get('num_docs', 0)} documents")
                    return True
                else:
                    logger.warning(f"Index {index_name} exists but has invalid state, recreating...")
                    await self.client.ft(index_name).dropindex(delete_documents=False)
            except Exception as e:
                logger.info(f"Index {index_name} does not exist or is invalid, creating new index")

            # Define schema for the index
            schema = [
                VectorField(
                    "embedding",
                    "FLAT",
                    {
                        "TYPE": "FLOAT32",
                        "DIM": vector_dim,
                        "DISTANCE_METRIC": distance_metric,
                        "INITIAL_CAP": 1000,
                        "BLOCK_SIZE": 1000
                    }
                ),
                TagField("document_id"),
                TagField("workspace_id"),
                TextField("title"),
                TextField("content"),
                TagField("source_id"),
                TagField("source_type"),
                TextField("$", as_name="metadata")
            ]

            # Create the index with retry logic
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    await self.client.ft(index_name).create_index(
                        fields=schema,
                        definition=IndexDefinition(
                            prefix=[prefix],
                            index_type=IndexType.HASH
                        )
                    )

                    # Verify the index was created
                    try:
                        info = await self.client.ft(index_name).info()
                        if info.get('num_docs', -1) >= 0:  # Verification
                            logger.info(f"Successfully created index {index_name} with vector dimension {vector_dim}")
                            return True
                    except Exception as verify_error:
                        logger.error(f"Failed to verify index {index_name}: {str(verify_error)}")
                        if attempt == max_retries - 1:  # Last attempt
                            raise

                except Exception as create_error:
                    if "Index already exists" in str(create_error):
                        logger.warning(f"Index {index_name} was created by another process")
                        return True

                    logger.error(
                        f"Error creating index {index_name} (attempt {attempt + 1}/{max_retries}): {str(create_error)}")
                    if attempt == max_retries - 1:  # Last attempt
                        raise

            return False

        except Exception as e:
            logger.error(f"Failed to create or verify index {index_name}: {str(e)}", exc_info=True)
            try:
                # Try to clean up if possible
                await self.client.ft(index_name).dropindex(delete_documents=False)
            except:
                pass
            return False

    async def index_document(
            self,
            index_name: str,
            document_id: str,
            workspace_id: str,
            content: str,
            embedding: List[float],
            source_id: Optional[str] = None,
            source_type: Optional[str] = None,
            metadata: Optional[Dict[str, Any]] = None,
            title: Optional[str] = None
    ) -> bool:
        """Index a document with its vector embedding.

        Args:
            index_name: Name of the index
            document_id: Unique ID of the document
            workspace_id: ID of the workspace
            content: Document content
            embedding: Vector embedding of the document
            source_id: Optional source ID
            source_type: Optional source type
            metadata: Additional metadata
            title: Document title

        Returns:
            bool: True if indexing was successful
        """
        if not document_id or not workspace_id or not content or not embedding:
            logger.error("Missing required fields for document indexing")
            return False

        try:
            # Convert and validate embedding
            try:
                embedding_array = np.array(embedding, dtype=np.float32)
                if len(embedding_array.shape) != 1:
                    logger.error(f"Invalid embedding shape: {embedding_array.shape}")
                    return False
            except Exception as e:
                logger.error(f"Invalid embedding format: {str(e)}")
                return False

            # Normalize source_id for Redis TagField compatibility
            normalized_source_id = normalize_source_id(source_id)

            # Prepare document data
            doc_data = {
                "document_id": document_id,
                "workspace_id": workspace_id,
                "title": title or "",
                "content": content,
                "embedding": embedding_array.tobytes(),
                "metadata": json.dumps(metadata or {}),
                "source_id": normalized_source_id,  # Use normalized source_id
                "source_type": source_type,
            }


            # Store document in Redis
            key = f"doc:{document_id}"
            try:
                # Store the document
                result = await self.client.hset(key, mapping=doc_data)
                if not result:
                    logger.error(f"Failed to store document {document_id} in Redis")
                    return False

                # Verify the document was stored
                stored = await self.client.hgetall(key)
                if not stored:
                    logger.error(f"Failed to verify document {document_id} in Redis")
                    return False

                logger.info(f"Successfully indexed document {document_id} in index {index_name}")
                return True

            except Exception as store_error:
                logger.error(f"Error storing document {document_id}: {str(store_error)}", exc_info=True)
                # Try to clean up if possible
                try:
                    await self.client.delete(key)
                except:
                    pass
                return False

        except Exception as e:
            logger.error(f"Unexpected error indexing document {document_id}: {str(e)}", exc_info=True)
            return False

    async def vector_search(
            self,
            index_name: str,
            query_vector: List[float],
            vector_field: str = "embedding",
            return_fields: Optional[List[str]] = None,
            k: int = 10,
            score_threshold: float = 0.0,
            filter_expression: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform a vector similarity search on Redis, returning only documents
        that match the optional filters.
        """

        if not query_vector or not index_name:
            return []

        try:
            # Convert query vector
            query_array = np.array(query_vector, dtype=np.float32)
            if query_array.ndim != 1:
                return []

            # Default return fields
            if not return_fields:
                return_fields = [
                    "workspace_id", "document_id", "title", "content",
                    "source_type", "source_id", "metadata"
                ]

            # Ensure index exists
            try:
                await self.client.ft(index_name).info()
            except Exception as e:
                error_msg = f"Index {index_name} does not exist or is not accessible: {str(e)}"
                logger.error(error_msg)
                raise RuntimeError(error_msg) from e

            # Build KNN query with proper syntax
            query_base = f"*=>[KNN {k} @{vector_field} $vec AS vector_score]"
            if filter_expression and filter_expression.strip():
                # Split filters et normaliser
                parts = []
                for expr in filter_expression.split():
                    if ":" in expr:
                        field, value = expr.split(":", 1)
                        value = value.strip()

                        # Si la valeur est alphanumérique simple -> wrap avec {}
                        if not (value.startswith("{") or value.startswith("(") or value.startswith('"')):
                            value = f"{{{value}}}"

                        parts.append(f"{field}:{value}")

                # Joindre avec &&
                normalized_filter = " && ".join(parts)
                query_base = f"({normalized_filter})=>[KNN {k} @{vector_field} $vec AS vector_score]"
            query = (
                Query(query_base)
                .return_fields(*return_fields, "vector_score")
                .sort_by("vector_score")
                .paging(0, k)
                .dialect(2)
            )

            # Run query
            results = await self.client.ft(index_name).search(
                query,
                query_params={"vec": query_array.tobytes()}
            )

            matches = []
            for doc in results.docs:
                doc_dict = {}
                for k, v in doc.__dict__.items():
                    if k.startswith('__'):
                        continue
                    if isinstance(v, bytes):
                        v = v.decode('utf-8', errors='replace')
                    doc_dict[k] = v

                # Convert distance -> similarity
                distance = float(doc_dict.pop('vector_score', 1.0))
                similarity = 1 / (1 + distance)

                if similarity >= score_threshold:
                    if 'metadata' in doc_dict and isinstance(doc_dict['metadata'], str):
                        try:
                            doc_dict['metadata'] = json.loads(doc_dict['metadata'])
                        except (json.JSONDecodeError, TypeError):
                            pass
                    doc_dict['score'] = similarity
                    matches.append(doc_dict)
            return matches

        except Exception as e:
            error_msg = f"Error performing vector search: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e

    async def delete_document(self, index_name: str, document_id: str) -> bool:
        """Delete a document from the index.
        
        Args:
            index_name: Name of the index
            document_id: ID of the document to delete
            
        Returns:
            bool: True if deletion was successful
        """
        try:
            return await self.client.delete(f"doc:{document_id}") > 0
        except Exception as e:
            return False

    async def get_document(self, index_name: str, document_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a document by ID.
        
        Args:
            index_name: Name of the index
            document_id: ID of the document to retrieve
            
        Returns:
            Document data or None if not found
        """
        try:
            doc = await self.client.hgetall(f"doc:{document_id}")
            if not doc:
                return None

            # Convert bytes to appropriate types
            result = {}
            for k, v in doc.items():
                if k == b'embedding':
                    # Convert binary embedding to list of floats
                    result['embedding'] = np.frombuffer(v, dtype=np.float32).tolist()
                elif k == b'metadata':
                    result['metadata'] = json.loads(v.decode())
                else:
                    result[k.decode()] = v.decode() if isinstance(v, bytes) else v

            return result

        except Exception as e:
            logger.error(f"Error getting document: {str(e)}", exc_info=True)
            return None
