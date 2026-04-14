from typing import Optional

from pydantic import BaseModel, Field


class VerifyRequest(BaseModel):
    query: str = Field(
        ..., min_length=1, description="The claim or statement to verify"
    )
    language: Optional[str] = Field(
        default="en", description="Language code for response"
    )
    use_cloud: Optional[bool] = Field(
        default=False, description="Force cloud model usage"
    )
