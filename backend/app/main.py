from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="AI Mistake Book")

    @app.get("/healthz")
    async def healthz() -> dict[str, bool]:
        return {"ok": True}

    return app


app = create_app()
