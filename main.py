from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.agent import router as agent_router
from api.chat import router as chat_router
from api.conversation import router as conversation_router
from api.documents import router as documents_router
from api.workspace import router as workspace_router

app = FastAPI(
    title="DevGuideBot API",
    description="""API for DevGuideBot - A smart assistant for developers.
    
    This API provides endpoints for:
    - Chatting with the AI assistant
    - Managing documents and their embeddings
    - Searching through documentation
    - Managing conversations and workspaces
    """,
    version="0.1.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(workspace_router)
app.include_router(conversation_router)
app.include_router(agent_router)
app.include_router(documents_router)
app.include_router(chat_router)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers and monitoring."""
    return {"status": "healthy"}
