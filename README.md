# DevGuideBot Backend

A smart assistant for developers with document search and chat capabilities powered by OpenAI's embeddings and chat models.

## Features

- **Document Management**: Store and manage documents with metadata
- **Semantic Search**: Find relevant documents using vector similarity search
- **Chat Interface**: Natural language interaction with your documents
- **Multi-workspace Support**: Organize documents and conversations by workspace
- **API-First**: RESTful API for easy integration with any frontend

## Prerequisites

- Python 3.8+
- MongoDB (for document storage)
- Redis (for vector search)
- OpenAI API key

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/DevGuideBot.git
   cd DevGuideBot/DevGuideBot-backend
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Update the following environment variables in your `.env` file:

```env
# Required
OPENAI__API_KEY=your_openai_api_key_here
MONGO_URI=mongodb://localhost:27017/devguidebot
REDIS_URL=redis://localhost:6379/0

# Optional (with defaults shown)
# OPENAI__EMBEDDING_MODEL=text-embedding-3-small
# OPENAI__CHAT_MODEL=gpt-4-turbo-preview
# OPENAI__TEMPERATURE=0.7
# OPENAI__MAX_TOKENS=1000
# SEARCH_SIMILARITY_THRESHOLD=0.7
# MAX_SEARCH_RESULTS=5
```

## Running the Application

1. Start the FastAPI server:
   ```bash
   uvicorn main:app --reload
   ```

2. The API will be available at `http://localhost:8000`

3. Access the interactive API documentation at `http://localhost:8000/docs`

## API Endpoints

### Chat

- `POST /chat/` - Send a message and get a response
### Documents

- `POST /workspaces/{workspace_id}/documents` - Upload a document
- `GET /workspaces/{workspace_id}/documents` - List documents
- `GET /workspaces/{workspace_id}/documents/{document_id}` - Get a document
- `DELETE /workspaces/{workspace_id}/documents/{document_id}` - Delete a document
- `POST /workspaces/{workspace_id}/documents/search` - Search documents

### Workspaces

- `POST /workspaces` - Create a workspace
- `GET /workspaces` - List workspaces
- `GET /workspaces/{workspace_id}` - Get workspace details

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black .
isort .
```

### Linting

```bash
flake8
mypy .
```

## Deployment

### Docker

```bash
docker-compose up --build
```

## License

MIT
