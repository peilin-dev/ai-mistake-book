from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.analytics.router import router as analytics_router
from app.assignments.router import close_arq_pool
from app.assignments.router import router as assignments_router
from app.auth.router import router as auth_router
from app.classes.router import router as classes_router, students_router
from app.review.router import router as review_router
from app.storage.router import router as storage_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_arq_pool(app)


def create_app() -> FastAPI:
    app = FastAPI(title="AI Mistake Book", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(auth_router, prefix="/api")
    app.include_router(classes_router, prefix="/api")
    app.include_router(students_router, prefix="/api")
    app.include_router(assignments_router, prefix="/api")
    app.include_router(review_router, prefix="/api")
    app.include_router(analytics_router, prefix="/api")
    app.include_router(storage_router, prefix="/api")
    return app


app = create_app()
