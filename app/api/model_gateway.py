from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.ai.gateway import ModelGateway, ModelGatewayConfig
from app.api.dependencies import verify_business_api_key
from app.config import Settings, get_settings


router = APIRouter(prefix="/model", tags=["model"], dependencies=[Depends(verify_business_api_key)])


class ModelStatusResponse(BaseModel):
    configured: bool
    model: str | None


class ModelCompleteRequest(BaseModel):
    system_prompt: str = Field(min_length=1, max_length=12000)
    user_prompt: str = Field(min_length=1, max_length=30000)
    temperature: float = Field(default=0.2, ge=0, le=2)


class ModelCompleteResponse(BaseModel):
    content: str


def get_model_gateway(
    settings: Settings = Depends(get_settings),
) -> ModelGateway:
    return ModelGateway(ModelGatewayConfig.from_settings(settings))


@router.get("/status", response_model=ModelStatusResponse)
def get_model_status(
    settings: Settings = Depends(get_settings),
) -> ModelStatusResponse:
    config = ModelGatewayConfig.from_settings(settings)
    return ModelStatusResponse(
        configured=config.is_configured,
        model=config.model or None,
    )


@router.post("/complete", response_model=ModelCompleteResponse)
def complete_with_model(
    request: ModelCompleteRequest,
    gateway: ModelGateway = Depends(get_model_gateway),
) -> ModelCompleteResponse:
    return ModelCompleteResponse(
        content=gateway.complete(
            system_prompt=request.system_prompt,
            user_prompt=request.user_prompt,
            temperature=request.temperature,
        )
    )
