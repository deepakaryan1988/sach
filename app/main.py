from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="TruthLens",
    description="AI-powered misinformation detection platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    config = get_config()
    uvicorn.run(
        "app.main:app",
        host=config.app_host,
        port=config.app_port,
        reload=True,
    )
