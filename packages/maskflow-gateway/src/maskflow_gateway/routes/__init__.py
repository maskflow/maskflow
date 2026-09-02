from .chat import router as chat_router
from .embeddings import router as embeddings_router
from .mask import router as mask_router
from .messages import router as messages_router
from .meta import router as meta_router

ROUTERS = [chat_router, messages_router, embeddings_router, mask_router, meta_router]

__all__ = ["ROUTERS"]
