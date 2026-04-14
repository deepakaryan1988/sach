from fastapi import APIRouter

from app.models.requests import VerifyRequest
from app.models.responses import VerifyResponse
from app.pipeline.verify import VerificationPipeline

router = APIRouter()
pipeline = VerificationPipeline()


@router.post("/verify", response_model=VerifyResponse)
async def verify(request: VerifyRequest) -> VerifyResponse:
    return await pipeline.verify(request)


@router.get("/health")
async def health() -> dict:
    return {"status": "healthy"}
