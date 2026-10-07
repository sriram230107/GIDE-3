from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("gide")

from app.ai.router import router as tutor_router
from app.assessment.router import router as assessment_router
from app.auth.router import router as auth_router
from app.core.config import settings
from app.core.database import init_db
from app.core.storage import get_storage_path
from app.evaluation_api.router import router as system_router
from app.knowledge.router import router as knowledge_router
from app.learner.router import router as learner_router
from app.sources.router import router as sources_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup: storage + db init (env=%s)", settings.ENVIRONMENT)
    get_storage_path()
    await init_db()
    log.info("startup: ready")
    yield


app = FastAPI(title=settings.PROJECT_NAME, version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

# Raw uploads, slide renders and keyframes (needed by the in-browser SourceViewer; ids are unguessable UUIDs).
app.mount("/storage", StaticFiles(directory=str(get_storage_path())), name="storage")

for r in (auth_router, sources_router, knowledge_router, tutor_router, assessment_router, learner_router, system_router):
    app.include_router(r)


@app.get("/health")
async def health():
    from app.ai import llm
    return {"status": "ok", "app": settings.PROJECT_NAME, "environment": settings.ENVIRONMENT, "llm_status": llm.get_status()}
