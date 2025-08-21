from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenAISettings(BaseSettings):
    """OpenAI API configuration settings."""
    api_key: str = Field(..., description="OpenAI API key")
    embedding_model: str = Field(
        default="text-embedding-3-large",
        description="Model to use for embeddings"
    )
    chat_model: str = Field(
        default="gpt-4-turbo-preview",
        description="Model to use for chat completions"
    )
    embedding_batch_size: int = Field(
        default=32,
        ge=1,
        le=2048,
        description="Number of texts to embed in each batch"
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for chat completions"
    )
    max_tokens: int = Field(
        default=1000,
        ge=1,
        le=4096,
        description="Maximum number of tokens to generate in chat completions"
    )


class Settings(BaseSettings):
    # MongoDB settings
    MONGO_URI: str = Field(default="mongodb://localhost:27017", description="MongoDB connection string")
    MONGO_DB: str = Field(default="devguide", description="Default MongoDB database name")

    # Redis settings
    REDIS_URL: str = Field(default="redis://localhost:6379", description="Redis connection URL")
    REDIS_INDEX_NAME: str = Field(default="devguide_idx", description="Redis index name")

    # OpenAI settings
    openai: OpenAISettings = Field(default_factory=OpenAISettings)

    # Search settings
    search_similarity_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score for semantic search results"
    )
    max_search_results: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Maximum number of search results to return"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore"
    )


settings = Settings()
