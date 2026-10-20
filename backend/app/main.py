from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.classes.router import router as classes_router


def create_app() -> FastAPI:
    app = FastAPI(title="AI Mistake Book")

    @app.get("/healthz")
    async def healthz() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(auth_router, prefix="/api")
    app.include_router(classes_router, prefix="/api")
    return app


app = create_app()
